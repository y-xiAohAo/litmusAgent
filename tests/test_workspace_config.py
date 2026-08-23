"""TD-015 单元 B：持久工作区配置与关闭链路测试。

覆盖范围：
  - SandboxConfig.volume_name / host_dir 校验（合法名、非法名、互斥、未交付报错）
  - create_sandbox_backend 工厂接线（docker 透传、subprocess + volume_name 报错）
  - Agent.close() 关闭自建沙箱 backend、不动外部注入 backend
  - CLI run 路径在结束时收口 agent.close()
"""

from __future__ import annotations

import pytest

from agent.cli.agent_cli import main
from agent.config import SandboxConfig
from agent.core.engine import Agent
from agent.llm import EchoClient
from agent.sandbox import create_sandbox_backend
from agent.sandbox.docker_backend import DockerSandboxBackend, ExecutionResult


class RaisingLLMClient(EchoClient):
    """chat 调用直接抛异常的 Mock LLM 客户端。"""

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """固定抛 RuntimeError，用于验证异常路径收口。"""
        raise RuntimeError("模拟 LLM 调用失败")


class CloseTrackingBackend(DockerSandboxBackend):
    """记录 close() 调用次数的 Mock 沙箱后端（不连接真实 Docker）。"""

    def __init__(self) -> None:
        self.image = "python:3.11-slim"
        self.timeout = 30
        self.close_count = 0

    async def execute_code(
        self, code: str, timeout: int | None = None
    ) -> ExecutionResult:
        """固定返回成功结果。"""
        return ExecutionResult(exit_code=0, stdout="", stderr="", success=True)

    def close(self) -> None:
        """仅计数，不触碰 Docker。"""
        self.close_count += 1


class TestVolumeNameValidation:
    """volume_name 字段校验。"""

    def test_valid_volume_names(self) -> None:
        """字母、数字、_、.、- 组合的卷名应通过校验。"""
        for name in ("my-proj", "proj_1", "a.b.c", "ABC123"):
            config = SandboxConfig(volume_name=name)
            assert config.volume_name == name

    def test_invalid_volume_name_raises(self) -> None:
        """含空格/斜杠等非法字符的卷名应报错。"""
        for name in ("my proj", "a/b", "卷名", ""):
            with pytest.raises(ValueError):
                SandboxConfig(volume_name=name)

    def test_default_fields_are_none(self) -> None:
        """默认配置下 volume_name 与 host_dir 均为 None（零行为变化）。"""
        config = SandboxConfig()
        assert config.volume_name is None
        assert config.host_dir is None


class TestHostDirConfig:
    """host_dir（bind 模式）配置校验（单元 C 起放开）。"""

    def test_host_dir_alone_accepted(self) -> None:
        """单独配置 host_dir 应通过校验（bind 模式随单元 C 交付）。"""
        config = SandboxConfig(host_dir="D:/proj")
        assert config.host_dir == "D:/proj"
        assert config.is_bind_mode() is True

    def test_host_dir_and_volume_name_mutually_exclusive(self) -> None:
        """host_dir 与 volume_name 同时配置应报错（互斥）。"""
        with pytest.raises(ValueError, match="互斥"):
            SandboxConfig(host_dir="D:/proj", volume_name="my-proj")

    def test_default_not_bind_mode(self) -> None:
        """默认配置不是 bind 模式。"""
        assert SandboxConfig().is_bind_mode() is False


class TestFactoryWiring:
    """create_sandbox_backend 的工作区接线。"""

    def test_docker_persistent_volume(self) -> None:
        """docker + volume_name → 固定卷 litmus-ws-<name> 且关闭时保留。"""
        config = SandboxConfig(backend="docker", volume_name="my-proj")
        backend = create_sandbox_backend(config)

        assert isinstance(backend, DockerSandboxBackend)
        assert backend.workspace_volume == "litmus-ws-my-proj"
        assert backend.cleanup_workspace is False

    def test_docker_default_random_volume_cleanup(self) -> None:
        """默认模式 → 随机卷名且关闭时清理（现状语义）。"""
        backend = create_sandbox_backend(SandboxConfig(backend="docker"))

        assert isinstance(backend, DockerSandboxBackend)
        assert backend.workspace_volume.startswith("hermes-workspace-")
        assert backend.cleanup_workspace is True

    def test_subprocess_with_volume_name_raises(self) -> None:
        """subprocess + volume_name 应明确报错。"""
        config = SandboxConfig(backend="subprocess", volume_name="my-proj")
        with pytest.raises(ValueError, match="subprocess 后端不支持命名卷"):
            create_sandbox_backend(config)

    def test_subprocess_without_volume_name_ok(self) -> None:
        """subprocess 不配 volume_name 时正常创建。"""
        backend = create_sandbox_backend(SandboxConfig(backend="subprocess"))
        assert backend is not None
        backend.close()


class TestAgentCloseChain:
    """Agent.close() 与 CLI 的沙箱收口链路。"""

    def test_close_owned_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """工厂自建的 backend 应在 Agent.close() 时被关闭。"""
        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )
        agent = Agent(llm_client=EchoClient())

        agent.close()

        assert backend.close_count == 1

    def test_close_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Agent.close() 可重复调用，backend.close() 幂等被调用。"""
        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )
        agent = Agent(llm_client=EchoClient())

        agent.close()
        agent.close()

        assert backend.close_count == 2  # backend 自身负责幂等

    def test_injected_backend_not_closed(self) -> None:
        """外部注入的 backend 不应被 Agent.close() 关闭。"""
        backend = CloseTrackingBackend()
        agent = Agent(llm_client=EchoClient(), sandbox_backend=backend)

        agent.close()

        assert backend.close_count == 0

    def test_cli_run_closes_agent_backend(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI run --echo 结束后应收口自建沙箱 backend（修孤儿卷泄漏）。"""
        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )

        assert main(["--plain", "run", "--echo", "hello"]) == 0
        capsys.readouterr()

        assert backend.close_count == 1


class FalsyBackend(CloseTrackingBackend):
    """__bool__ 返回 False 的 Mock 后端（验证注入的 falsy backend 不被替换）。"""

    def __bool__(self) -> bool:
        """固定返回 False，模拟实现了 __bool__ 的自定义后端。"""
        return False


class TestInjectedBackendFalsy:
    """Agent 构造的 falsy 陷阱回归测试（CR 🟠-2）。"""

    def test_falsy_injected_backend_not_replaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """注入的 backend 即使 __bool__ 为 False 也应被原样使用。"""
        backend = FalsyBackend()

        def _factory_should_not_be_called(config: object) -> object:
            raise AssertionError("注入 backend 时不应调用工厂")

        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", _factory_should_not_be_called
        )
        agent = Agent(llm_client=EchoClient(), sandbox_backend=backend)

        assert agent._sandbox_backend is backend
        assert agent._owns_sandbox_backend is False


class TestCliFriendlyErrors:
    """CLI 报错路径友好化（CR 🟠-1）：走 render_error，不裸 traceback。"""

    def test_cmd_run_missing_config_file(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_run 配置文件不存在时应友好报错并返回 1。"""
        exit_code = main(
            ["--plain", "run", "--config", "no_such_config.yaml", "--echo", "hi"]
        )
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "配置加载失败" in captured.err
        assert "Traceback" not in captured.out + captured.err

    def test_cmd_run_factory_value_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """工厂 ValueError（如 subprocess + volume_name）在 cmd_run 被友好捕获。"""

        def _raising_factory(config: object) -> object:
            raise ValueError("subprocess 后端不支持命名卷")

        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", _raising_factory
        )
        exit_code = main(["--plain", "run", "--echo", "hello"])
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "沙箱配置错误" in captured.err
        assert "Traceback" not in captured.out + captured.err

    def test_cmd_chat_factory_value_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """工厂 ValueError 在 cmd_chat 被友好捕获，不进入交互循环。"""

        def _raising_factory(config: object) -> object:
            raise ValueError("subprocess 后端不支持命名卷")

        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", _raising_factory
        )
        exit_code = main(["--plain", "chat", "--echo"])
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "沙箱配置错误" in captured.err
        assert "Traceback" not in captured.out + captured.err


class TestCloseSegmentIsolation:
    """Agent.close() 三段隔离：前段抛异常不阻塞后续段（CR 修复项 3）。"""

    def test_cache_cleanup_failure_still_closes_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """context_cache 清理抛异常时，自建沙箱 backend 仍应被关闭。"""
        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )
        agent = Agent(llm_client=EchoClient())

        class _RaisingCache:
            def cleanup(self) -> None:
                raise RuntimeError("模拟缓存清理失败")

        agent.context_cache = _RaisingCache()  # type: ignore[assignment]
        agent._cleanup_cache_on_exit = True

        agent.close()  # 不应抛出

        assert backend.close_count == 1

    def test_memory_cleanup_failure_still_closes_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """memory 收尾抛异常时，自建沙箱 backend 仍应被关闭。"""
        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )
        agent = Agent(llm_client=EchoClient())

        class _RaisingMemory:
            def cleanup(self) -> None:
                raise RuntimeError("模拟记忆清理失败")

        agent.memory_manager = _RaisingMemory()  # type: ignore[assignment]
        agent._cleanup_memory_on_exit = True

        agent.close()  # 不应抛出

        assert backend.close_count == 1


class TestWebShutdownHook:
    """web shutdown 钩子：进程退出时收口所有 session 的 backend。"""

    def test_shutdown_closes_all_session_backends(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """with TestClient(app) 退出时应关闭所有 session 的自建 backend。"""
        from fastapi.testclient import TestClient

        from agent.web import app as web_app

        backends = [CloseTrackingBackend(), CloseTrackingBackend()]
        backend_iter = iter(backends)
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: next(backend_iter)
        )
        web_app._sessions.clear()

        with TestClient(web_app.app) as client:
            assert client.post("/api/chat/s1", json={"message": "hi"}).status_code == 200
            assert client.post("/api/chat/s2", json={"message": "hi"}).status_code == 200

        assert [b.close_count for b in backends] == [1, 1]
        assert web_app._sessions == {}

    def test_shutdown_one_session_failure_not_blocking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """单个 session 的 close 抛异常不影响其余 session 被关闭。"""
        from fastapi.testclient import TestClient

        from agent.web import app as web_app

        class _RaisingAgent:
            def close(self) -> None:
                raise RuntimeError("模拟单个 session 关闭失败")

        normal_backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: normal_backend
        )
        web_app._sessions.clear()
        web_app._sessions["bad"] = _RaisingAgent()  # type: ignore[dict-item]

        with TestClient(web_app.app) as client:
            assert client.post("/api/chat/good", json={"message": "hi"}).status_code == 200

        assert normal_backend.close_count == 1
        assert web_app._sessions == {}


class TestRunFinallyClose:
    """run/chat 路径的 finally 收口（CR 测试缺口）。"""

    def test_run_exception_path_still_closes_backend(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """agent.run() 抛异常时，cmd_run 的 finally 仍执行 close。"""
        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )
        monkeypatch.setattr(
            "agent.cli.agent_cli.EchoClient", lambda: RaisingLLMClient()
        )

        exit_code = main(["--plain", "run", "--echo", "hello"])
        capsys.readouterr()

        assert exit_code == 1
        assert backend.close_count == 1

    def test_chat_loop_exit_closes_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_chat_loop 退出（/quit）后应关闭自建沙箱 backend。"""
        from agent.cli.chat import run_chat_loop

        backend = CloseTrackingBackend()
        monkeypatch.setattr(
            "agent.core.engine.create_sandbox_backend", lambda config: backend
        )
        monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda *a, **k: "/quit")

        agent = Agent(llm_client=EchoClient())
        exit_code = run_chat_loop(agent, plain=True)

        assert exit_code == 0
        assert backend.close_count == 1
