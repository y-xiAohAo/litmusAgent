"""TD-016 MCP 工具接入测试（tests/test_mcp_tools.py）。

覆盖 Spec §5 验收条：
  - fake MCP server（stdio 真实链路 + 本地 SSE 服务）发现与调用；
  - 命名前缀 mcp__<server>__<tool>；
  - 未装 mcp 包 → 友好中文 ImportError；
  - 默认人工确认 / trust 豁免 / 策略 deny（mcp/<server> subject）；
  - server 僵死 → tool_timeout 超时返回 MCPError 失败结果，Agent 继续；
  - 单 server 连接失败跳过 + warning；全部失败不阻塞 Agent；
  - close 回收（stdio 子进程退出）；
  - tools.enabled 白名单（全名匹配）。

fake server 用 SDK 的 MCPServer 定义（mcp 2.x，FastMCP 已更名），
stdio 走真实子进程链路，SSE 走本地 uvicorn 服务实测。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from agent.config import AgentConfig
from agent.core.engine import Agent
from agent.core.types import ToolCall
from agent.llm.base import BaseLLMClient
from tests.test_tools import MockSandboxBackend

SERVER_PATH = Path(__file__).parent / "mcp_fake_server.py"


class ScriptClient(BaseLLMClient):
    """按脚本依次返回响应的 LLM 客户端（记录每次收到的 tools schema）。"""

    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self.steps = list(steps)
        self.tools_seen: list[Any] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.tools_seen.append(tools)
        return self.steps.pop(0)


def _tool_call_step(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": None,
        "tool_calls": [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def _text_step(text: str) -> dict[str, Any]:
    return {"content": text, "tool_calls": None}


def _stdio_server(name: str = "fake", **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "command": sys.executable,
        "args": [str(SERVER_PATH)],
        **extra,
    }


def _make_agent(
    servers: list[dict[str, Any]],
    client: BaseLLMClient | None = None,
    tool_timeout: int = 30,
    approval_callback: Any = None,
    **config_kwargs: Any,
) -> Agent:
    config = AgentConfig(
        mcp={"tool_timeout": tool_timeout, "servers": servers}, **config_kwargs
    )
    return Agent(
        llm_client=client or ScriptClient([_text_step("done")]),
        config=config,
        sandbox_backend=MockSandboxBackend(),
        approval_callback=approval_callback,
    )


def _pid_alive(pid: int) -> bool:
    """跨平台进程存活探测（无 psutil 依赖）。"""
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class TestStdioLink:
    """stdio 真实链路：发现、调用、命名前缀（验收 1）。"""

    async def test_discover_and_call_via_agent_run(self) -> None:
        """Agent run 惰性连接后应能调用 MCP 工具并正确回传结果。"""
        client = ScriptClient([
            _tool_call_step("mcp__fake__add", {"a": 2, "b": 3}),
            _tool_call_step("finish", {"result": "算完了"}),
        ])
        agent = _make_agent([_stdio_server()], client=client)
        try:
            result = await agent.run("算 2+3")
        finally:
            agent.close()

        assert result == "算完了"
        # 工具结果正确回传进对话历史
        tool_msgs = [m for m in agent.messages if m.role == "tool"]
        assert any("5" == m.content for m in tool_msgs)
        # 命名前缀 + schema 暴露给 LLM
        schemas = client.tools_seen[0] or []
        names = {s["function"]["name"] for s in schemas}
        assert {"mcp__fake__add", "mcp__fake__echo"} <= names

    async def test_lazy_connect_registers_prefixed_tools(self) -> None:
        """_ensure_mcp_connected 后注册 mcp__<server>__<tool> 全名。"""
        agent = _make_agent([_stdio_server()])
        try:
            await agent._ensure_mcp_connected()
            assert agent.tools.get("mcp__fake__add") is not None
            assert agent.tools.get("mcp__fake__echo") is not None
            assert agent._mcp_manager is not None
            assert agent._mcp_manager.connected_servers == ["fake"]
            # 幂等：第二次不再重复连接
            await agent._ensure_mcp_connected()
            assert agent._mcp_manager.connected_servers == ["fake"]
        finally:
            agent.close()

    async def test_mcp_iserror_maps_to_mcperror_prefix(self) -> None:
        """MCP isError 结果 → ToolResult(success=False) + MCPError: 前缀。"""
        agent = _make_agent([_stdio_server()])
        try:
            await agent._ensure_mcp_connected()
            result = await agent.tools.execute(
                ToolCall(id="t1", name="mcp__fake__fail", arguments={})
            )
            assert result.success is False
            assert result.content.startswith("MCPError:")
        finally:
            agent.close()


class TestApproval:
    """人工确认：默认全确认、trust 豁免（验收 3）。"""

    async def test_untrusted_server_tools_require_approval(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        def callback(name: str, args: dict[str, Any]) -> bool:
            calls.append((name, args))
            return True

        agent = _make_agent([_stdio_server()], approval_callback=callback)
        try:
            await agent._ensure_mcp_connected()
            result = await agent.tools.execute(
                ToolCall(id="t2", name="mcp__fake__echo", arguments={"text": "hi"})
            )
            assert result.success is True
            assert calls == [("mcp__fake__echo", {"text": "hi"})]
        finally:
            agent.close()

    async def test_trusted_server_exempt_from_approval(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        def callback(name: str, args: dict[str, Any]) -> bool:
            calls.append((name, args))
            return True

        agent = _make_agent(
            [_stdio_server(name="trusted", trust=True)],
            approval_callback=callback,
        )
        try:
            await agent._ensure_mcp_connected()
            result = await agent.tools.execute(
                ToolCall(id="t3", name="mcp__trusted__echo", arguments={"text": "hi"})
            )
            assert result.success is True
            assert result.content == "echo:hi"
            assert calls == []
        finally:
            agent.close()

    async def test_approval_reject_returns_failure(self) -> None:
        agent = _make_agent(
            [_stdio_server()], approval_callback=lambda name, args: False
        )
        try:
            await agent._ensure_mcp_connected()
            result = await agent.tools.execute(
                ToolCall(id="t4", name="mcp__fake__echo", arguments={"text": "hi"})
            )
            assert result.success is False
            assert "用户拒绝" in result.content
        finally:
            agent.close()


class TestPolicy:
    """策略层：mcp/<server> subject + operation call（验收 3）。"""

    async def test_policy_deny_blocks_mcp_tool(self) -> None:
        agent = _make_agent(
            [_stdio_server()],
            security={
                "enabled": True,
                "rules": [
                    {
                        "resource": "mcp/server",
                        "operation": "call",
                        "pattern": "^mcp/fake$",
                        "action": "deny",
                        "reason": "测试拒绝",
                    }
                ],
            },
        )
        try:
            await agent._ensure_mcp_connected()
            result = await agent.tools.execute(
                ToolCall(id="t5", name="mcp__fake__echo", arguments={"text": "hi"})
            )
            assert result.success is False
            assert "策略拒绝" in result.content
            assert "测试拒绝" in result.content
        finally:
            agent.close()


class TestTimeout:
    """server 僵死 → tool_timeout 超时返回 MCPError 失败结果，Agent 继续（验收 4）。"""

    async def test_hung_server_times_out_and_agent_continues(self) -> None:
        client = ScriptClient([
            _tool_call_step("mcp__fake__hang", {}),
            _tool_call_step("finish", {"result": "已放弃僵死工具"}),
        ])
        agent = _make_agent([_stdio_server()], client=client, tool_timeout=1)
        try:
            start = time.monotonic()
            result = await agent.run("调用会僵死的工具")
            elapsed = time.monotonic() - start
        finally:
            agent.close()

        assert result == "已放弃僵死工具"
        assert elapsed < 30  # 未被僵死工具拖死
        tool_msgs = [m for m in agent.messages if m.role == "tool"]
        assert any(
            "MCPError:" in m.content and "超时" in m.content for m in tool_msgs
        )


class TestFailureDegrade:
    """连接失败降级：单 server 失败跳过 + warning；全失败不阻塞（验收 5）。"""

    async def test_single_failure_skipped_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = _make_agent([
            {"name": "bad", "command": "definitely-not-exist-cmd-xyz-404"},
            _stdio_server(),
        ])
        try:
            with caplog.at_level("WARNING"):
                await agent._ensure_mcp_connected()
            assert agent._mcp_manager is not None
            assert agent._mcp_manager.failed_servers == ["bad"]
            assert agent._mcp_manager.connected_servers == ["fake"]
            assert any(
                "bad" in r.message and "跳过" in r.message for r in caplog.records
            )
            # 存活的 server 工具可用
            result = await agent.tools.execute(
                ToolCall(id="t6", name="mcp__fake__add", arguments={"a": 1, "b": 1})
            )
            assert result.success is True
            assert result.content == "2"
        finally:
            agent.close()

    async def test_all_failures_do_not_block_agent(self) -> None:
        agent = _make_agent([
            {"name": "bad1", "command": "definitely-not-exist-cmd-xyz-1"},
            {"name": "bad2", "url": "http://127.0.0.1:1/sse"},
        ])
        try:
            result = await agent.run("你好")
            assert result == "done"
        finally:
            agent.close()


class TestMissingPackage:
    """未装 mcp 包 + 配置 mcp 段 → 友好中文报错（验收 2）。"""

    async def test_import_error_with_friendly_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "mcp", None)
        agent = _make_agent([_stdio_server()])
        with pytest.raises(ImportError, match="pip install"):
            await agent.run("你好")


class TestClose:
    """close 收口：stdio 子进程退出、调用失败、幂等（验收 6）。"""

    async def test_close_reaps_stdio_subprocess(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "fake.pid"
        server = _stdio_server(env={
            **os.environ,
            "FAKE_MCP_PID_FILE": str(pid_file),
        })
        agent = _make_agent([server])
        await agent._ensure_mcp_connected()
        assert agent._mcp_manager is not None

        # 等待子进程写入 PID
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.05)
        pid = int(pid_file.read_text(encoding="utf-8"))
        assert _pid_alive(pid)

        agent.close()
        for _ in range(100):
            if not _pid_alive(pid):
                break
            await asyncio.sleep(0.1)
        assert not _pid_alive(pid), "close 后 MCP server 子进程仍在运行"

    async def test_close_idempotent_and_tool_fails_after_close(self) -> None:
        agent = _make_agent([_stdio_server()])
        await agent._ensure_mcp_connected()
        agent.close()
        agent.close()  # 不应抛异常
        await asyncio.sleep(0.2)
        result = await agent.tools.execute(
            ToolCall(id="t7", name="mcp__fake__echo", arguments={"text": "hi"})
        )
        assert result.success is False


class TestToolsEnabledWhitelist:
    """tools.enabled 白名单全名匹配（§6 自定细节）。"""

    async def test_enabled_whitelist_filters_mcp_tools(self) -> None:
        agent = _make_agent(
            [_stdio_server()], tools={"enabled": ["mcp__fake__add"]}
        )
        try:
            await agent._ensure_mcp_connected()
            assert agent.tools.get("mcp__fake__add") is not None
            assert agent.tools.get("mcp__fake__echo") is None
        finally:
            agent.close()


class TestSSELink:
    """本地 SSE 服务实测：发现与调用（验收 1 第二形态）。"""

    async def test_sse_discover_and_call(self) -> None:
        import socket

        import uvicorn

        from tests.mcp_fake_server import server as fake_server

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        app = fake_server.sse_app()
        uv_config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error"
        )
        uv_server = uvicorn.Server(uv_config)
        task = asyncio.create_task(uv_server.serve())
        try:
            for _ in range(100):
                if uv_server.started:
                    break
                await asyncio.sleep(0.05)
            assert uv_server.started

            agent = _make_agent([
                {"name": "fake-sse", "url": f"http://127.0.0.1:{port}/sse"}
            ])
            try:
                await agent._ensure_mcp_connected()
                assert agent.tools.get("mcp__fake-sse__add") is not None
                result = await agent.tools.execute(
                    ToolCall(
                        id="t8",
                        name="mcp__fake-sse__echo",
                        arguments={"text": "hello"},
                    )
                )
                assert result.success is True
                assert result.content == "echo:hello"
            finally:
                agent.close()
        finally:
            uv_server.should_exit = True
            await asyncio.wait_for(task, timeout=10)


def _free_port() -> int:
    """占用即释放方式取一个空闲端口。"""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _start_uvicorn(app: Any, port: int) -> tuple[Any, asyncio.Task[None]]:
    """启动本地 uvicorn 服务并等待就绪，返回 (server, task)。"""
    import uvicorn

    uv_server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    task = asyncio.create_task(uv_server.serve())
    for _ in range(100):
        if uv_server.started:
            break
        await asyncio.sleep(0.05)
    assert uv_server.started
    return uv_server, task


class TestAssemblyRace:
    """同行评审 O1：并发装配竞态与失败回滚。"""

    async def test_concurrent_ensure_connects_once(self) -> None:
        """并发 _ensure_mcp_connected 只装配一次，不重复连接。"""
        agent = _make_agent([_stdio_server()])
        try:
            await asyncio.gather(
                agent._ensure_mcp_connected(),
                agent._ensure_mcp_connected(),
            )
            assert agent._mcp_manager is not None
            assert agent._mcp_manager.connected_servers == ["fake"]
            assert len(agent._mcp_manager._handles) == 1
        finally:
            agent.close()

    async def test_connect_failure_rolls_back_and_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """connect() 抛异常 → 回滚标志 + 回收半成品；下次调用可重试。"""
        from agent.mcp_client import MCPManager

        agent = _make_agent([_stdio_server()])
        real_connect = MCPManager.connect
        calls = 0

        async def flaky_connect(
            self: MCPManager, registry: Any, enabled: Any = None
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            await real_connect(self, registry, enabled)

        monkeypatch.setattr(MCPManager, "connect", flaky_connect)
        try:
            with pytest.raises(RuntimeError, match="boom"):
                await agent._ensure_mcp_connected()
            # 标志回滚 + 半成品 manager 已摘除，可重试
            assert agent._mcp_connect_attempted is False
            assert agent._mcp_manager is None

            await agent._ensure_mcp_connected()
            assert agent._mcp_manager is not None
            assert agent.tools.get("mcp__fake__add") is not None
        finally:
            agent.close()


class TestDegrade:
    """同行评审 Y3：超时/失败后 server 降级，后续调用快速失败（不重连）。"""

    async def test_timed_out_server_degraded_and_fast_fails(self) -> None:
        agent = _make_agent([_stdio_server()], tool_timeout=1)
        try:
            await agent._ensure_mcp_connected()
            r1 = await agent.tools.execute(
                ToolCall(id="d1", name="mcp__fake__hang", arguments={})
            )
            assert r1.success is False
            assert "超时" in r1.content

            # 同一 server 的其他工具也立即快速失败，不再真实调用
            start = time.monotonic()
            r2 = await agent.tools.execute(
                ToolCall(id="d2", name="mcp__fake__echo", arguments={"text": "hi"})
            )
            elapsed = time.monotonic() - start
            assert r2.success is False
            assert "server 已降级" in r2.content
            assert "上次调用超时" in r2.content
            assert elapsed < 1  # 快速失败，未走 wait_for 超时
        finally:
            agent.close()


class TestTransportConfig:
    """同行评审 Y2：显式 transport 字段与一致性校验。"""

    def test_stdio_transport_requires_command(self) -> None:
        with pytest.raises(ValueError, match="command"):
            AgentConfig(mcp={"servers": [
                {"name": "x", "transport": "stdio", "url": "http://h/sse"},
            ]})

    def test_sse_transport_requires_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            AgentConfig(mcp={"servers": [
                {"name": "x", "transport": "sse", "command": "echo"},
            ]})

    def test_explicit_transport_constructs(self) -> None:
        """显式 sse/http 与 url 一致时构造通过；缺省走启发式。"""
        config = AgentConfig(mcp={"servers": [
            {"name": "a", "url": "http://h/api", "transport": "sse"},
            {"name": "b", "url": "http://h/sse", "transport": "http"},
            {"name": "c", "url": "http://h/mcp"},
        ]})
        assert config.mcp.servers[0].transport == "sse"
        assert config.mcp.servers[1].transport == "http"
        assert config.mcp.servers[2].transport is None


class TestStreamableHttpLink:
    """同行评审 O2：本地 Streamable HTTP 形态实测（自建 httpx client）。"""

    async def test_streamable_http_discover_and_call(self) -> None:
        from tests.mcp_fake_server import server as fake_server

        port = _free_port()
        app = fake_server.streamable_http_app()
        uv_server, task = await _start_uvicorn(app, port)
        try:
            agent = _make_agent([
                {
                    "name": "fake-http",
                    "url": f"http://127.0.0.1:{port}/mcp",
                    "transport": "http",
                    # 走自建 httpx client 的 headers 路径
                    "headers": {"Authorization": "Bearer test"},
                }
            ])
            try:
                await agent._ensure_mcp_connected()
                assert agent._mcp_manager is not None
                assert agent._mcp_manager.connected_servers == ["fake-http"]
                assert agent.tools.get("mcp__fake-http__add") is not None
                result = await agent.tools.execute(
                    ToolCall(
                        id="h1",
                        name="mcp__fake-http__echo",
                        arguments={"text": "hello"},
                    )
                )
                assert result.success is True
                assert result.content == "echo:hello"
            finally:
                agent.close()
        finally:
            uv_server.should_exit = True
            await asyncio.wait_for(task, timeout=10)


class TestWebAsyncClose:
    """同行评审 O3：web shutdown 钩子等待 MCP 回收完成。"""

    async def test_web_shutdown_awaits_mcp_reclaim(self, tmp_path: Path) -> None:
        from agent.web import app as web_app

        pid_file = tmp_path / "fake.pid"
        server = _stdio_server(env={
            **os.environ,
            "FAKE_MCP_PID_FILE": str(pid_file),
        })
        agent = _make_agent([server])
        web_app._sessions["test-session"] = agent
        try:
            await agent._ensure_mcp_connected()
            for _ in range(100):
                if pid_file.exists():
                    break
                await asyncio.sleep(0.05)
            pid = int(pid_file.read_text(encoding="utf-8"))
            assert _pid_alive(pid)

            await web_app._shutdown_close_sessions()
            assert web_app._sessions == {}
            # aclose 已等待回收完成：子进程退出、handles 清空
            assert agent._mcp_manager is not None
            assert agent._mcp_manager._handles == []
            for _ in range(100):
                if not _pid_alive(pid):
                    break
                await asyncio.sleep(0.1)
            assert not _pid_alive(pid), "web shutdown 后 MCP server 子进程仍在运行"
        finally:
            web_app._sessions.clear()
            agent.close()
