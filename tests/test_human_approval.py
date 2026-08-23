"""人工确认钩子测试（TD-008）。

覆盖：
  - ToolRegistry 确认钩子：批准执行 / 拒绝失败 / 未配置工具不受影响 / 无 callback 不拦截
  - Agent 装配：config 启用 + callback 注入后写工具被拦截；无 callback 不拦截
  - HumanApprovalConfig 默认值
"""

from __future__ import annotations

import pytest

from agent.config import AgentConfig
from agent.core.engine import Agent, ToolRegistry
from agent.core.types import ToolCall, ToolSpec
from agent.llm.base import EchoClient


def make_call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=arguments)


def make_write_registry(
    callback: object = None,
    approval_tools: set[str] | None = None,
) -> ToolRegistry:
    """构造带 file_write 假工具的 registry。"""
    registry = ToolRegistry(
        approval_callback=callback,  # type: ignore[arg-type]
        approval_tools=approval_tools,
    )
    registry.register(
        ToolSpec(
            name="file_write",
            description="write",
            parameters={"type": "object", "properties": {}},
            handler=lambda path, content: "written",
        )
    )
    registry.register(
        ToolSpec(
            name="file_read",
            description="read",
            parameters={"type": "object", "properties": {}},
            handler=lambda path: "content",
        )
    )
    return registry


class TestRegistryApprovalHook:
    """ToolRegistry 的人工确认钩子。"""

    @pytest.mark.asyncio
    async def test_approved_executes_tool(self) -> None:
        """callback 批准 → 工具正常执行。"""
        registry = make_write_registry(
            callback=lambda name, args: True,
            approval_tools={"file_write"},
        )
        result = await registry.execute(
            make_call("file_write", {"path": "/workspace/a.py", "content": "x"})
        )
        assert result.success is True
        assert result.content == "written"

    @pytest.mark.asyncio
    async def test_rejected_returns_failure(self) -> None:
        """callback 拒绝 → success=False 且标注用户拒绝，handler 未执行。"""
        registry = make_write_registry(
            callback=lambda name, args: False,
            approval_tools={"file_write"},
        )
        result = await registry.execute(
            make_call("file_write", {"path": "/workspace/a.py", "content": "x"})
        )
        assert result.success is False
        assert "用户拒绝" in result.content

    @pytest.mark.asyncio
    async def test_unconfigured_tool_not_intercepted(self) -> None:
        """不在 approval_tools 中的工具不触发 callback。"""
        calls: list[str] = []

        def spy(name: str, args: dict) -> bool:
            calls.append(name)
            return True

        registry = make_write_registry(callback=spy, approval_tools={"file_write"})
        result = await registry.execute(make_call("file_read", {"path": "/x"}))
        assert result.success is True
        assert calls == []

    @pytest.mark.asyncio
    async def test_no_callback_no_interception(self) -> None:
        """配置了 approval_tools 但无 callback 时不拦截。"""
        registry = make_write_registry(callback=None, approval_tools={"file_write"})
        result = await registry.execute(
            make_call("file_write", {"path": "/workspace/a.py", "content": "x"})
        )
        assert result.success is True


class TestHumanApprovalConfig:
    """HumanApprovalConfig 配置与 Agent 装配。"""

    def test_config_defaults(self) -> None:
        """默认未显式配置（None，普通模式按不启用），默认工具集 file_write/file_edit。"""
        config = AgentConfig()
        approval = config.agent.human_approval
        assert approval.enabled is None  # TD-015 单元 C 三态：None = 未显式配置
        assert approval.tools == ["file_write", "file_edit"]

    def test_agent_wires_approval_from_config(self) -> None:
        """config 启用 + 注入 callback → 写工具被拦截。"""
        config = AgentConfig()
        config.agent.human_approval.enabled = True
        agent = Agent(
            llm_client=EchoClient(),
            config=config,
            approval_callback=lambda name, args: False,
        )
        try:
            assert agent.tools._approval_callback is not None
            assert "file_write" in agent.tools._approval_tools
        finally:
            agent._sandbox_backend.close()

    def test_agent_no_callback_no_interception(self) -> None:
        """config 启用但未注入 callback → 不拦截。"""
        config = AgentConfig()
        config.agent.human_approval.enabled = True
        agent = Agent(llm_client=EchoClient(), config=config)
        try:
            assert agent.tools._approval_callback is None
        finally:
            agent._sandbox_backend.close()


class TestCliApprovalCallback:
    """CLI 交互确认 callback（y/n/a 语义，TD-008）。"""

    def test_y_approves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """输入 y → 批准。"""
        from agent.cli import chat as chat_module
        from agent.cli.chat import make_cli_approval_callback

        monkeypatch.setattr(chat_module.Prompt, "ask", lambda *a, **k: "y")
        callback = make_cli_approval_callback({"file_write"})
        assert callback("file_write", {"path": "/workspace/a.py"}) is True

    def test_n_rejects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """输入 n → 拒绝。"""
        from agent.cli import chat as chat_module
        from agent.cli.chat import make_cli_approval_callback

        monkeypatch.setattr(chat_module.Prompt, "ask", lambda *a, **k: "n")
        callback = make_cli_approval_callback({"file_write"})
        assert callback("file_write", {"path": "/workspace/a.py"}) is False

    def test_a_approves_and_skips_future_prompts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """输入 a → 批准且同工具后续调用免确认（不再提示）。"""
        from agent.cli import chat as chat_module
        from agent.cli.chat import make_cli_approval_callback

        prompts: list[str] = []

        def fake_ask(*args: object, **kwargs: object) -> str:
            prompts.append("asked")
            return "a"

        monkeypatch.setattr(chat_module.Prompt, "ask", fake_ask)
        callback = make_cli_approval_callback({"file_write"})
        assert callback("file_write", {"path": "/workspace/a.py"}) is True
        assert callback("file_write", {"path": "/workspace/b.py"}) is True
        assert len(prompts) == 1  # 第二次未再提示

    def test_a_does_not_leak_to_other_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """a 的免确认只作用于同一工具，其他工具仍会提示。"""
        from agent.cli import chat as chat_module
        from agent.cli.chat import make_cli_approval_callback

        answers = iter(["a", "n"])
        prompts: list[str] = []

        def fake_ask(*args: object, **kwargs: object) -> str:
            prompts.append("asked")
            return next(answers)

        monkeypatch.setattr(chat_module.Prompt, "ask", fake_ask)
        callback = make_cli_approval_callback({"file_write", "file_edit"})
        assert callback("file_write", {"path": "/a"}) is True
        assert callback("file_edit", {"path": "/a", "old_string": "1", "new_string": "2"}) is False
        assert len(prompts) == 2
