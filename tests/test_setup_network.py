"""TD-010：沙箱网络策略增强测试。

覆盖 Spec §7 全部验收点：
  1. 配置默认 network_mode="none"，池断言不受影响；
  2. network_mode="bridge" 配置后池容器按 bridge 创建；
  3. allow_setup_network=True 且代码含 pip install → 有网临时容器执行、
     用完销毁、不入池（计数断言）；
  4. 无 pip 意图的代码仍走禁网池；
  5. 配置关闭时 pip 代码也走禁网（现状）；
  6. subprocess 后端接受 allow_network 不报错；
  7. 默认零回归（工厂默认透传、Protocol 向后兼容）。

全部不连接真实 Docker daemon（docker.from_env 打桩）。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from docker.models.containers import Container

from agent.config import SandboxConfig
from agent.sandbox import create_sandbox_backend
from agent.sandbox.docker_backend import DockerSandboxBackend
from agent.sandbox.subprocess_backend import SubprocessSandboxBackend
from agent.tools.sandbox_exec import sandbox_exec


@pytest.fixture
def mock_client():
    """提供一个已打桩的 Docker client，用于隔离真实 Docker 调用。"""
    client = MagicMock()
    with patch("agent.sandbox.docker_backend.docker.from_env", return_value=client):
        yield client


def _make_exec_container(container_id: str) -> MagicMock:
    """构造一个可执行代码的桩容器。"""
    container = MagicMock(spec=Container)
    container.id = container_id
    container.exec_run.return_value = (0, (b"ok\n", b""))
    return container


class TestNetworkModeConfig:
    """§7-1/§7-2：network_mode 配置与池创建透传。"""

    def test_default_network_mode_is_none(self) -> None:
        """SandboxConfig 默认 network_mode='none' 且 allow_setup_network=False。"""
        config = SandboxConfig()
        assert config.network_mode == "none"
        assert config.allow_setup_network is False

    @pytest.mark.asyncio
    async def test_warmup_uses_default_none_network(self, mock_client):
        """默认配置下池容器按 network_mode='none' 创建（现状不变）。"""
        mock_client.containers.create.side_effect = [
            _make_exec_container("p0"),
            _make_exec_container("p1"),
        ]
        backend = DockerSandboxBackend()

        assert await backend.warmup(count=2) is True
        for call in mock_client.containers.create.call_args_list:
            assert call.kwargs["network_mode"] == "none"

    @pytest.mark.asyncio
    async def test_warmup_uses_configured_bridge_network(self, mock_client):
        """network_mode='bridge' 时预热池容器按 bridge 创建。"""
        mock_client.containers.create.side_effect = [
            _make_exec_container("p0"),
            _make_exec_container("p1"),
        ]
        backend = DockerSandboxBackend(network_mode="bridge")

        assert await backend.warmup(count=2) is True
        for call in mock_client.containers.create.call_args_list:
            assert call.kwargs["network_mode"] == "bridge"

    @pytest.mark.asyncio
    async def test_acquire_and_replenish_use_configured_network(self, mock_client):
        """池空新建与释放补充的容器同样按配置的 network_mode 创建。"""
        mock_client.containers.create.side_effect = [
            _make_exec_container("exec"),
            _make_exec_container("repl"),
        ]
        backend = DockerSandboxBackend(network_mode="bridge")

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        for call in mock_client.containers.create.call_args_list:
            assert call.kwargs["network_mode"] == "bridge"
        assert len(backend._pool) == 1


class TestAllowNetworkExecution:
    """§7-3/§7-4/§7-5：execute_code 的 allow_network 临时容器路径。"""

    @pytest.mark.asyncio
    async def test_allow_network_creates_ephemeral_bridge_container(self, mock_client):
        """allow_network=True：现场创建 bridge 临时容器，销毁且不入池。"""
        pooled = _make_exec_container("pooled")
        ephemeral = _make_exec_container("ephemeral")
        mock_client.containers.create.side_effect = [pooled, ephemeral]
        backend = DockerSandboxBackend()
        await backend.warmup(count=1)

        result = await backend.execute_code("pip install requests", allow_network=True)

        assert result.success is True
        # 临时容器按 bridge 创建，且挂载同一 workspace 卷
        create_call = mock_client.containers.create.call_args_list[-1]
        assert create_call.kwargs["network_mode"] == "bridge"
        assert create_call.kwargs["volumes"] == {
            backend.workspace_volume: {"bind": "/workspace", "mode": "rw"},
        }
        # 其余加固不变
        assert create_call.kwargs["user"] == "nobody"
        assert create_call.kwargs["read_only"] is True
        # 临时容器执行后即销毁
        ephemeral.exec_run.assert_called()
        ephemeral.stop.assert_called_once()
        ephemeral.remove.assert_called_once()
        # 池语义不受影响：预热池原样保留，无释放补充
        assert len(backend._pool) == 1
        assert backend._pool[0] is pooled
        # 池容器仅有 warmup 时的 chown 调用，未执行用户代码
        pooled_code_calls = [
            c for c in pooled.exec_run.call_args_list if "chown" not in str(c)
        ]
        assert pooled_code_calls == []
        assert mock_client.containers.create.call_count == 2

    @pytest.mark.asyncio
    async def test_allow_network_false_keeps_pool_semantics(self, mock_client):
        """allow_network=False（默认）：走禁网池，执行后释放并补充。"""
        pooled = _make_exec_container("pooled")
        replacement = _make_exec_container("replacement")
        mock_client.containers.create.side_effect = [pooled, replacement]
        backend = DockerSandboxBackend()
        await backend.warmup(count=1)

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        assert len(backend._pool) == 1
        assert backend._pool[0] is replacement
        for call in mock_client.containers.create.call_args_list:
            assert call.kwargs["network_mode"] == "none"

    @pytest.mark.asyncio
    async def test_allow_network_create_failure_returns_failure(self, mock_client):
        """有网临时容器创建失败时返回失败结果，不影响池。"""
        pooled = _make_exec_container("pooled")
        mock_client.containers.create.side_effect = [
            pooled,
            Exception("create failed"),
        ]
        backend = DockerSandboxBackend()
        await backend.warmup(count=1)

        result = await backend.execute_code("print('ok')", allow_network=True)

        assert result.success is False
        assert result.exit_code == -1
        assert len(backend._pool) == 1


class TestEphemeralCleanupHardening:
    """TD-010 评审加固：临时容器销毁与创建失败的兜底清理。"""

    @pytest.mark.asyncio
    async def test_ephemeral_destroyed_when_exec_raises(self, mock_client):
        """allow_network 执行时 exec_run 抛异常，临时容器仍被销毁。"""
        ephemeral = _make_exec_container("ephemeral")
        ephemeral.exec_run.side_effect = RuntimeError("exec boom")
        mock_client.containers.create.return_value = ephemeral
        backend = DockerSandboxBackend()

        result = await backend.execute_code("print('x')", allow_network=True)

        assert result.success is False
        assert "exec boom" in result.stderr
        ephemeral.stop.assert_called_once()
        ephemeral.remove.assert_called_once()
        assert len(backend._pool) == 0

    @pytest.mark.asyncio
    async def test_ephemeral_destroyed_on_timeout(self, mock_client):
        """allow_network 执行超时，临时容器仍被销毁。"""
        import time

        ephemeral = _make_exec_container("ephemeral")
        ephemeral.exec_run.side_effect = lambda *a, **k: time.sleep(5)
        mock_client.containers.create.return_value = ephemeral
        backend = DockerSandboxBackend()

        result = await backend.execute_code(
            "print('x')", timeout=0.1, allow_network=True
        )

        assert result.success is False
        assert "超时" in result.stderr
        ephemeral.stop.assert_called_once()
        ephemeral.remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_ephemeral_destroy_failure_degrades_with_warning(
        self, mock_client, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_destroy_ephemeral_container 自身失败：不抛出，仅 warning 降级。"""
        ephemeral = _make_exec_container("ephemeral")
        ephemeral.stop.side_effect = RuntimeError("stop boom")
        mock_client.containers.create.return_value = ephemeral
        backend = DockerSandboxBackend()

        with caplog.at_level(logging.WARNING):
            result = await backend.execute_code("print('x')", allow_network=True)

        # 执行结果不受销毁失败影响
        assert result.success is True
        assert any("临时容器销毁失败" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_create_container_start_failure_removes_container(
        self, mock_client
    ) -> None:
        """_do_create_container 中 start 失败：已创建容器被 force remove，返回 None。"""
        broken = _make_exec_container("broken")
        broken.start.side_effect = RuntimeError("start boom")
        mock_client.containers.create.return_value = broken
        backend = DockerSandboxBackend()

        result = await backend.execute_code("print('x')", allow_network=True)

        assert result.success is False
        assert result.stderr == "Failed to create container"
        broken.remove.assert_called_once_with(force=True)
        assert len(backend._pool) == 0


class TestSubprocessAllowNetwork:
    """§7-6：subprocess 后端接受并忽略 allow_network。"""

    @pytest.mark.asyncio
    async def test_execute_code_accepts_allow_network(self) -> None:
        """传 allow_network=True 不报错，正常执行。"""
        backend = SubprocessSandboxBackend()
        try:
            result = await backend.execute_code(
                "print('ok')", allow_network=True
            )
            assert result.success is True
            assert result.stdout.strip() == "ok"
        finally:
            backend.close()


class _RecordingBackend:
    """记录 execute_code 调用参数的最小桩后端。"""

    def __init__(self, setup_network_enabled: bool = False) -> None:
        self.setup_network_enabled = setup_network_enabled
        self.calls: list[dict[str, object]] = []

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
        *,
        allow_network: bool = False,
    ):
        from agent.sandbox.base import ExecutionResult

        self.calls.append({"code": code, "allow_network": allow_network})
        return ExecutionResult(exit_code=0, stdout="ok", stderr="", success=True)


class _LegacyBackend:
    """不支持 allow_network 参数的旧式桩后端（向后兼容场景）。"""

    def __init__(self, setup_network_enabled: bool = True) -> None:
        self.setup_network_enabled = setup_network_enabled
        self.calls: list[str] = []

    async def execute_code(self, code: str, timeout: int | None = None):
        from agent.sandbox.base import ExecutionResult

        self.calls.append(code)
        return ExecutionResult(exit_code=0, stdout="ok", stderr="", success=True)


class TestSandboxExecSetupNetwork:
    """§7-3/§7-4/§7-5：sandbox_exec 工具层的 pip 意图 → allow_network 路由。"""

    @pytest.mark.asyncio
    async def test_pip_intent_uses_allow_network_when_enabled(self) -> None:
        """配置开启 + pip 意图 → 以 allow_network=True 执行。"""
        backend = _RecordingBackend(setup_network_enabled=True)

        result = await sandbox_exec("pip install requests", backend)  # type: ignore[arg-type]

        assert result.success is True
        assert backend.calls == [
            {"code": "pip install requests", "allow_network": True}
        ]

    @pytest.mark.asyncio
    async def test_no_pip_intent_stays_on_pool(self) -> None:
        """配置开启但无 pip 意图 → 不传 allow_network（走禁网池）。"""
        backend = _RecordingBackend(setup_network_enabled=True)

        result = await sandbox_exec("print('ok')", backend)  # type: ignore[arg-type]

        assert result.success is True
        assert backend.calls == [{"code": "print('ok')", "allow_network": False}]

    @pytest.mark.asyncio
    async def test_pip_intent_disabled_config_stays_offline(self) -> None:
        """配置关闭时 pip 代码也走禁网（现状不变）。"""
        backend = _RecordingBackend(setup_network_enabled=False)

        result = await sandbox_exec("pip install requests", backend)  # type: ignore[arg-type]

        assert result.success is True
        assert backend.calls == [
            {"code": "pip install requests", "allow_network": False}
        ]

    @pytest.mark.asyncio
    async def test_pip_intent_without_flag_attr_stays_offline(self) -> None:
        """后端无 setup_network_enabled 属性时按关闭处理。"""
        backend = _RecordingBackend()
        del backend.setup_network_enabled

        result = await sandbox_exec("pip install requests", backend)  # type: ignore[arg-type]

        assert result.success is True
        assert backend.calls == [
            {"code": "pip install requests", "allow_network": False}
        ]

    @pytest.mark.asyncio
    async def test_legacy_backend_without_allow_network_param(self) -> None:
        """旧式后端（不支持 allow_network 参数）不传该参数，调用不报错。"""
        backend = _LegacyBackend()

        result = await sandbox_exec("pip install requests", backend)  # type: ignore[arg-type]

        assert result.success is True
        assert backend.calls == ["pip install requests"]


class TestFactoryNetworkPassthrough:
    """§7-7：工厂透传 network_mode / allow_setup_network，默认零回归。"""

    def test_factory_default_passthrough(self) -> None:
        """默认配置：network_mode='none' 且 setup_network_enabled=False。"""
        backend = create_sandbox_backend(SandboxConfig(backend="docker"))
        try:
            assert isinstance(backend, DockerSandboxBackend)
            assert backend.network_mode == "none"
            assert backend.setup_network_enabled is False
        finally:
            backend.close()

    def test_factory_passes_network_fields(self) -> None:
        """配置 network_mode/allow_setup_network 时透传到 Docker 后端。"""
        config = SandboxConfig(
            backend="docker",
            network_mode="bridge",
            allow_setup_network=True,
        )
        backend = create_sandbox_backend(config)
        try:
            assert isinstance(backend, DockerSandboxBackend)
            assert backend.network_mode == "bridge"
            assert backend.setup_network_enabled is True
        finally:
            backend.close()

    def test_factory_bind_mode_with_setup_network_warns(
        self, caplog: pytest.LogCaptureFixture, tmp_path
    ) -> None:
        """bind 模式显式开启 allow_setup_network 时打 warning（§4.5）。"""
        config = SandboxConfig(
            backend="docker",
            host_dir=str(tmp_path),
            allow_setup_network=True,
        )
        with patch(
            "agent.sandbox._docker_available", return_value=True
        ), caplog.at_level(logging.WARNING):
            backend = create_sandbox_backend(config)
        try:
            assert isinstance(backend, DockerSandboxBackend)
            assert backend.setup_network_enabled is True
            assert any(
                "allow_setup_network" in r.message for r in caplog.records
            )
        finally:
            backend.close()
