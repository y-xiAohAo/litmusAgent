"""Docker 沙箱后端连接、健康检查、容器创建与销毁的测试。"""

from __future__ import annotations

import io
import tarfile
from unittest.mock import MagicMock, patch

import pytest
from docker.models.containers import Container

from agent.sandbox.docker_backend import DockerSandboxBackend


@pytest.fixture
def mock_client():
    """提供一个已打桩的 Docker client，用于隔离真实 Docker 调用。"""
    client = MagicMock()
    with patch("agent.sandbox.docker_backend.docker.from_env", return_value=client):
        yield client


class TestDockerSandboxBackendInit:
    """DockerSandboxBackend 初始化的测试。"""

    def test_default_image(self, mock_client):
        """默认镜像应为 python:3.11-slim。"""
        backend = DockerSandboxBackend()
        assert backend.image == "python:3.11-slim"

    def test_custom_image(self, mock_client):
        """构造函数应接受自定义镜像。"""
        backend = DockerSandboxBackend(image="python:3.10-slim")
        assert backend.image == "python:3.10-slim"

    @pytest.mark.asyncio
    async def test_ping_returns_false_when_docker_init_fails(self):
        """docker.from_env() 失败时，ping 应返回 False 且不抛异常。"""
        with patch(
            "agent.sandbox.docker_backend.docker.from_env",
            side_effect=Exception("docker not available"),
        ):
            backend = DockerSandboxBackend()
            result = await backend.ping()

        assert result is False


class TestDockerSandboxBackendPing:
    """Docker daemon 健康检查的测试。"""

    @pytest.mark.asyncio
    async def test_ping_returns_true_when_docker_is_healthy(self, mock_client):
        """Docker daemon 可达时 ping 应返回 True。"""
        mock_client.ping.return_value = True
        backend = DockerSandboxBackend()

        result = await backend.ping()

        assert result is True
        mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_returns_false_on_exception(self, mock_client):
        """Docker daemon 不可达时 ping 应返回 False。"""
        mock_client.ping.side_effect = Exception("connection refused")
        backend = DockerSandboxBackend()

        result = await backend.ping()

        assert result is False


class TestDockerSandboxBackendEnsureImage:
    """镜像准备逻辑的测试。"""

    @pytest.mark.asyncio
    async def test_ensure_image_returns_true_when_image_exists(self, mock_client):
        """镜像已存在时不应重新拉取。"""
        mock_client.images.list.return_value = [MagicMock(tags=["python:3.11-slim"])]
        backend = DockerSandboxBackend()

        result = await backend.ensure_image()

        assert result is True
        mock_client.images.list.assert_called_once_with(name="python:3.11-slim")
        mock_client.images.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_image_pulls_when_image_missing(self, mock_client):
        """镜像不存在时应拉取镜像。"""
        mock_client.images.list.return_value = []
        mock_client.images.pull.return_value = MagicMock()
        backend = DockerSandboxBackend()

        result = await backend.ensure_image()

        assert result is True
        mock_client.images.list.assert_called_once_with(name="python:3.11-slim")
        mock_client.images.pull.assert_called_once_with("python:3.11-slim")

    @pytest.mark.asyncio
    async def test_ensure_image_returns_false_on_list_failure(self, mock_client):
        """images.list() 抛异常时应返回 False。"""
        mock_client.images.list.side_effect = Exception("list failed")
        backend = DockerSandboxBackend()

        result = await backend.ensure_image()

        assert result is False
        mock_client.images.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_image_returns_false_on_pull_failure(self, mock_client):
        """拉取失败时应返回 False。"""
        mock_client.images.list.return_value = []
        mock_client.images.pull.side_effect = Exception("pull failed")
        backend = DockerSandboxBackend()

        result = await backend.ensure_image()

        assert result is False


class TestDockerSandboxBackendContainerLifecycle:
    """容器创建与销毁的测试。"""

    @pytest.mark.asyncio
    async def test_create_container_starts_new_container(self, mock_client):
        """create_container 应创建并启动容器，返回 Container 对象。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "abc123"
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        container = await backend.create_container()

        assert container is mock_container
        assert backend.container_id == "abc123"
        mock_client.containers.create.assert_called_once_with(
            image="python:3.11-slim",
            command="tail -f /dev/null",
            detach=True,
            stdin_open=True,
            tty=False,
            network_mode="none",
            user="nobody",
            read_only=True,
            volumes={
                backend.workspace_volume: {"bind": "/workspace", "mode": "rw"},
            },
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
        )
        mock_container.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_container_returns_none_when_docker_unavailable(self, mock_client):
        """Docker client 不可用时 create_container 应返回 None。"""
        mock_client.containers.create.side_effect = Exception("docker unavailable")
        backend = DockerSandboxBackend()

        container = await backend.create_container()

        assert container is None
        assert backend.container_id is None

    @pytest.mark.asyncio
    async def test_create_container_removes_existing_container(self, mock_client):
        """创建新容器前应先移除已存在的旧容器。"""
        old_container = MagicMock(spec=Container)
        old_container.id = "old123"
        new_container = MagicMock(spec=Container)
        new_container.id = "new456"
        mock_client.containers.create.return_value = new_container
        backend = DockerSandboxBackend()

        await backend.create_container()
        backend._container = old_container
        await backend.create_container()

        old_container.stop.assert_called_once()
        old_container.remove.assert_called_once()
        assert backend.container_id == "new456"

    @pytest.mark.asyncio
    async def test_create_container_returns_none_when_remove_fails(self, mock_client):
        """旧容器移除失败时不应继续创建新容器。"""
        old_container = MagicMock(spec=Container)
        old_container.stop.side_effect = Exception("stop failed")
        new_container = MagicMock(spec=Container)
        mock_client.containers.create.return_value = new_container
        backend = DockerSandboxBackend()
        backend._container = old_container

        container = await backend.create_container()

        assert container is None
        old_container.stop.assert_called_once()
        mock_client.containers.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_container_stops_and_removes(self, mock_client):
        """remove_container 应停止并删除当前容器。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "abc123"
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.remove_container()

        assert result is True
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
        assert backend.container_id is None

    @pytest.mark.asyncio
    async def test_remove_container_is_idempotent(self, mock_client):
        """没有容器时 remove_container 应返回 True。"""
        backend = DockerSandboxBackend()

        result = await backend.remove_container()

        assert result is True

    @pytest.mark.asyncio
    async def test_remove_container_returns_false_on_failure(self, mock_client):
        """停止或删除失败时应返回 False，并清空内部引用。"""
        mock_container = MagicMock(spec=Container)
        mock_container.stop.side_effect = Exception("stop failed")
        backend = DockerSandboxBackend()
        backend._container = mock_container

        result = await backend.remove_container()

        assert result is False
        assert backend.container_id is None

    def test_container_id_is_none_without_container(self, mock_client):
        """未创建容器时 container_id 应为 None。"""
        backend = DockerSandboxBackend()

        assert backend.container_id is None

    @pytest.mark.asyncio
    async def test_close_removes_container_and_client(self, mock_client):
        """close 应同时移除容器和释放 client。"""
        mock_container = MagicMock(spec=Container)
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        backend.close()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
        mock_client.close.assert_called_once()
        assert backend.container_id is None

    def test_close_is_safe_when_client_is_none(self):
        """client 未初始化时 close 不应抛异常。"""
        with patch(
            "agent.sandbox.docker_backend.docker.from_env",
            side_effect=Exception("docker not available"),
        ):
            backend = DockerSandboxBackend()

        backend.close()  # 不应抛异常

    @pytest.mark.asyncio
    async def test_async_context_manager_closes_client(self, mock_client):
        """async with 退出时应自动关闭 client。"""
        async with DockerSandboxBackend() as backend:
            assert isinstance(backend, DockerSandboxBackend)

        mock_client.close.assert_called_once()


class TestDockerSandboxBackendExecuteCode:
    """容器内代码执行与结果捕获的测试。"""

    @pytest.mark.asyncio
    async def test_execute_code_returns_success_result(self, mock_client):
        """代码执行成功时应返回 ExecutionResult。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "exec123"
        mock_container.exec_run.return_value = (0, (b"hello\n", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.execute_code("print('hello')")

        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        # EVAL-010：创建容器时会附带 chown 调用，断言时只看代码执行调用
        code_calls = [
            c for c in mock_container.exec_run.call_args_list
            if "chown" not in str(c)
        ]
        assert len(code_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_code_returns_failure_result(self, mock_client):
        """代码执行失败时应返回非零退出码和 stderr。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "exec123"
        mock_container.exec_run.return_value = (1, (b"", b"SyntaxError: invalid syntax"))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.execute_code("bad syntax")

        assert result.success is False
        assert result.exit_code == 1
        assert "SyntaxError" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_code_creates_container_if_missing(self, mock_client):
        """当前没有容器时应自动创建容器，执行后释放并补充。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "auto123"
        mock_container.exec_run.return_value = (0, (b"ok", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        mock_container.start.assert_called()
        # EVAL-010：创建容器时会附带 chown 调用，断言时只看代码执行调用
        code_calls = [
            c for c in mock_container.exec_run.call_args_list
            if "chown" not in str(c)
        ]
        assert len(code_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_code_returns_failure_when_container_creation_fails(self, mock_client):
        """自动创建容器失败时应返回失败结果。"""
        mock_client.containers.create.side_effect = Exception("create failed")
        backend = DockerSandboxBackend()

        result = await backend.execute_code("print('ok')")

        assert result.success is False
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_execute_code_returns_failure_when_docker_unavailable(self):
        """docker.from_env() 失败导致 _client 为 None 时，execute_code 应返回失败结果。"""
        with patch(
            "agent.sandbox.docker_backend.docker.from_env",
            side_effect=Exception("docker unavailable"),
        ):
            backend = DockerSandboxBackend()

        result = await backend.execute_code("print('ok')")

        assert result.success is False
        assert result.exit_code == -1
        assert "Docker client unavailable" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_code_timeout_not_passed_to_exec_run(self, mock_client):
        """timeout 不传给 exec_run（docker-py 7.x 不支持），由外层 asyncio 强制。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "timeout123"
        mock_container.exec_run.return_value = (0, (b"", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.execute_code("print('ok')", timeout=60)

        assert result.success is True
        _, kwargs = mock_container.exec_run.call_args
        assert "timeout" not in kwargs

    @pytest.mark.asyncio
    async def test_execute_code_timeout_enforced(self, mock_client):
        """执行超过 timeout 时返回超时失败，而不是无限等待。"""
        import time

        mock_container = MagicMock(spec=Container)
        mock_container.id = "slow123"
        mock_container.exec_run.side_effect = lambda *a, **k: (time.sleep(5), (0, (b"", b"")))[1]
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.execute_code("import time; time.sleep(60)", timeout=1)

        assert result.success is False
        assert result.exit_code == -1
        assert "超时" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_code_encodes_code_to_avoid_shell_escape(self, mock_client):
        """execute_code 应使用 base64 编码避免 shell 转义问题。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "encode123"
        mock_container.exec_run.return_value = (0, (b"", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        await backend.execute_code("print('a\"b')")

        # EVAL-010：跳过容器创建时的 chown 调用，取代码执行调用
        code_calls = [
            c for c in mock_container.exec_run.call_args_list
            if "chown" not in str(c)
        ]
        args, _ = code_calls[-1]
        command = args[0]
        assert "base64" in command
        assert "python" in command


class TestDockerSandboxBackendSecurity:
    """容器安全限制的测试。"""

    def test_default_timeout_is_30(self, mock_client):
        """backend 默认 timeout 应为 30 秒。"""
        backend = DockerSandboxBackend()
        assert backend.timeout == 30

    def test_default_timeout_from_config(self, mock_client):
        """backend 应接受自定义 timeout 并在 execute_code 中使用。"""
        backend = DockerSandboxBackend(timeout=60)
        assert backend.timeout == 60

    @pytest.mark.asyncio
    async def test_default_security_params(self, mock_client):
        """create_container 应默认应用安全限制参数。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "secure123"
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        await backend.create_container()

        _, kwargs = mock_client.containers.create.call_args
        assert kwargs.get("network_mode") == "none"
        assert kwargs.get("user") == "nobody"
        assert kwargs.get("read_only") is True
        assert kwargs.get("tmpfs") == {"/tmp": "rw,noexec,nosuid,size=64m"}

    @pytest.mark.asyncio
    async def test_custom_security_params(self, mock_client):
        """create_container 应允许覆盖安全限制参数。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "custom123"
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        await backend.create_container(
            memory_limit="512m",
            network_mode="bridge",
            user="root",
            read_only=False,
            tmpfs={"/tmp": "rw,size=128m"},
        )

        _, kwargs = mock_client.containers.create.call_args
        assert kwargs.get("mem_limit") == "512m"
        assert kwargs.get("network_mode") == "bridge"
        assert kwargs.get("user") == "root"
        assert kwargs.get("read_only") is False
        assert kwargs.get("tmpfs") == {"/tmp": "rw,size=128m"}

    @pytest.mark.asyncio
    async def test_execute_code_uses_default_timeout(self, mock_client):
        """execute_code 未传 timeout 时生效 backend 默认 timeout（不再传给 exec_run）。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "timeout123"
        mock_container.exec_run.return_value = (0, (b"", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(timeout=45)
        await backend.create_container()

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        assert backend.timeout == 45
        _, kwargs = mock_container.exec_run.call_args
        assert "timeout" not in kwargs

    @pytest.mark.asyncio
    async def test_execute_code_custom_timeout_overrides_default(self, mock_client):
        """execute_code 传入 timeout 时覆盖默认值（由外层 wait_for 生效，不进 exec_run）。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "override123"
        mock_container.exec_run.return_value = (0, (b"", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(timeout=45)
        await backend.create_container()

        result = await backend.execute_code("print('ok')", timeout=10)

        assert result.success is True
        _, kwargs = mock_container.exec_run.call_args
        assert "timeout" not in kwargs

    @pytest.mark.asyncio
    async def test_execute_code_auto_create_uses_security_defaults(self, mock_client):
        """execute_code 自动创建容器时应应用默认安全参数。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "auto123"
        mock_container.exec_run.return_value = (0, (b"ok", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(timeout=60)

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        _, kwargs = mock_client.containers.create.call_args
        assert kwargs.get("network_mode") == "none"
        assert kwargs.get("user") == "nobody"
        assert kwargs.get("read_only") is True

    @pytest.mark.asyncio
    async def test_create_container_passes_seccomp_profile(self, mock_client):
        """create_container 应支持传递 seccomp 配置文件。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "seccomp123"
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        await backend.create_container(seccomp_profile="/path/to/seccomp.json")

        _, kwargs = mock_client.containers.create.call_args
        assert "seccomp=/path/to/seccomp.json" in kwargs.get("security_opt", [])


class TestDockerSandboxBackendFileTransfer:
    """文件注入与提取的测试。"""

    @staticmethod
    def _make_tar_bytes(path: str, content: bytes) -> bytes:
        """构造一个包含单个文件的 tar 归档字节流。

        path 使用容器内相对路径或 basename，以贴近真实 Docker get_archive 行为。
        """
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            # 真实 Docker 返回的 tar 成员名通常是 basename 或相对路径
            name = path.lstrip("/")
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_put_file_writes_content_to_container(self, mock_client):
        """put_file 应把 bytes 写入容器内指定路径。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "put123"
        mock_container.put_archive.return_value = True
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.put_file("/tmp/data.txt", b"hello world")

        assert result is True
        mock_container.put_archive.assert_called_once()
        args, _ = mock_container.put_archive.call_args
        assert args[0] == "/tmp"

    @pytest.mark.asyncio
    async def test_put_file_returns_false_when_no_container_and_creation_fails(self, mock_client):
        """没有容器且创建失败时 put_file 应返回 False。"""
        mock_client.containers.create.side_effect = Exception("create failed")
        backend = DockerSandboxBackend()

        result = await backend.put_file("/tmp/data.txt", b"hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_put_file_returns_false_on_put_failure(self, mock_client):
        """put_archive 失败时 put_file 应返回 False。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "putfail123"
        mock_container.put_archive.return_value = False
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        result = await backend.put_file("/tmp/data.txt", b"hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_file_reads_content_from_container(self, mock_client):
        """get_file 应读取容器内文件内容。"""
        expected = b"file content"
        tar_bytes = self._make_tar_bytes("/tmp/read.txt", expected)
        mock_container = MagicMock(spec=Container)
        mock_container.id = "get123"
        mock_container.get_archive.return_value = (iter([tar_bytes]), {"size": len(expected)})
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        content = await backend.get_file("/tmp/read.txt")

        assert content == expected
        mock_container.get_archive.assert_called_once_with("/tmp/read.txt")

    @pytest.mark.asyncio
    async def test_get_file_returns_none_when_file_missing(self, mock_client):
        """文件不存在时 get_file 应返回 None。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "getmissing123"
        mock_container.get_archive.side_effect = Exception("404 Client Error")
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        content = await backend.get_file("/tmp/missing.txt")

        assert content is None

    @pytest.mark.asyncio
    async def test_get_file_returns_none_when_docker_unavailable(self, mock_client):
        """Docker 不可用时 get_file 应返回 None。"""
        mock_client.containers.create.side_effect = Exception("docker unavailable")
        backend = DockerSandboxBackend()

        content = await backend.get_file("/tmp/data.txt")

        assert content is None

    @pytest.mark.asyncio
    async def test_put_file_returns_false_when_docker_unavailable(self):
        """docker.from_env() 失败导致 _client 为 None 时，put_file 应返回 False。"""
        with patch(
            "agent.sandbox.docker_backend.docker.from_env",
            side_effect=Exception("docker unavailable"),
        ):
            backend = DockerSandboxBackend()

        result = await backend.put_file("/tmp/data.txt", b"hello")

        assert result is False

    @pytest.mark.asyncio
    async def test_put_file_auto_creates_container(self, mock_client):
        """put_file 在当前无容器时应自动创建容器，执行后释放并补充。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "auto_put123"
        mock_container.put_archive.return_value = True
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        result = await backend.put_file("/tmp/data.txt", b"hello")

        assert result is True
        mock_container.start.assert_called()


class TestDockerSandboxBackendPool:
    """轻量容器预热池的测试。"""

    @pytest.mark.asyncio
    async def test_warmup_creates_containers(self, mock_client):
        """warmup 应创建指定数量的容器放入池中。"""
        containers = [MagicMock(spec=Container) for _ in range(3)]
        for i, c in enumerate(containers):
            c.id = f"pool{i}"
        mock_client.containers.create.side_effect = containers
        backend = DockerSandboxBackend()

        result = await backend.warmup(count=3)

        assert result is True
        assert len(backend._pool) == 3
        assert mock_client.containers.create.call_count == 3

    @pytest.mark.asyncio
    async def test_warmup_returns_false_when_creation_fails(self, mock_client):
        """warmup 过程中创建失败应返回 False。"""
        mock_client.containers.create.side_effect = [
            MagicMock(spec=Container),
            Exception("create failed"),
        ]
        backend = DockerSandboxBackend()

        result = await backend.warmup(count=2)

        assert result is False

    @pytest.mark.asyncio
    async def test_execute_code_uses_pooled_container(self, mock_client):
        """execute_code 应优先使用池中的容器。"""
        pooled = MagicMock(spec=Container)
        pooled.id = "pooled123"
        pooled.exec_run.return_value = (0, (b"ok", b""))
        mock_client.containers.create.return_value = pooled
        backend = DockerSandboxBackend()
        await backend.warmup(count=1)

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        assert pooled.exec_run.called
        # warmup 创建 1 个，执行后释放并补充 1 个，共 2 次
        assert mock_client.containers.create.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_code_creates_new_when_pool_empty(self, mock_client):
        """池为空时 execute_code 应新建容器，执行后释放并补充。"""
        fresh = MagicMock(spec=Container)
        fresh.id = "fresh123"
        fresh.exec_run.return_value = (0, (b"ok", b""))
        mock_client.containers.create.return_value = fresh
        backend = DockerSandboxBackend()

        result = await backend.execute_code("print('ok')")

        assert result.success is True
        assert fresh.exec_run.called
        # 新建 1 个，执行后补充 1 个，共 2 次
        assert mock_client.containers.create.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_code_replenishes_pool_after_execution(self, mock_client):
        """execute_code 执行后应补充一个新容器到池中。"""
        pooled = MagicMock(spec=Container)
        pooled.id = "pooled123"
        pooled.exec_run.return_value = (0, (b"ok", b""))
        replacement = MagicMock(spec=Container)
        replacement.id = "replacement123"
        mock_client.containers.create.side_effect = [pooled, replacement]
        backend = DockerSandboxBackend()
        await backend.warmup(count=1)

        await backend.execute_code("print('ok')")

        assert len(backend._pool) == 1
        assert backend._pool[0] is replacement
        assert replacement.start.called

    @pytest.mark.asyncio
    async def test_put_file_uses_pooled_container(self, mock_client):
        """put_file 应优先使用池中的容器。"""
        pooled = MagicMock(spec=Container)
        pooled.id = "pool_put123"
        pooled.put_archive.return_value = True
        mock_client.containers.create.return_value = pooled
        backend = DockerSandboxBackend()
        await backend.warmup(count=1)

        result = await backend.put_file("/tmp/data.txt", b"hello")

        assert result is True
        assert pooled.put_archive.called

    def test_close_clears_pool(self, mock_client):
        """close() 应停止并移除预热池中的所有容器。"""
        backend = DockerSandboxBackend()
        pooled = [MagicMock(spec=Container) for _ in range(2)]
        backend._pool.extend(pooled)

        backend.close()

        for container in pooled:
            container.stop.assert_called_once()
            container.remove.assert_called_once()
        assert backend._pool == []
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_aexit_clears_pool(self, mock_client):
        """async with 退出时应清理预热池中的所有容器。"""
        backend = DockerSandboxBackend()
        pooled = [MagicMock(spec=Container) for _ in range(2)]
        backend._pool.extend(pooled)

        async with backend:
            pass

        for container in pooled:
            container.stop.assert_called_once()
            container.remove.assert_called_once()
        assert backend._pool == []

    def test_close_ignores_pool_cleanup_errors(self, mock_client):
        """close() 清理预热池时遇到异常不应抛出。"""
        backend = DockerSandboxBackend()
        pooled = MagicMock(spec=Container)
        pooled.stop.side_effect = Exception("stop failed")
        backend._pool.append(pooled)

        backend.close()

        pooled.stop.assert_called_once()
        assert backend._pool == []
        mock_client.close.assert_called_once()


class TestDockerSandboxBackendWorkspace:
    """Workspace volume 持久化测试。"""

    def test_backend_has_unique_workspace_volume(self, mock_client):
        """未指定 workspace_volume 时，每个 backend 实例应拥有唯一卷名。"""
        backend1 = DockerSandboxBackend()
        backend2 = DockerSandboxBackend()

        assert backend1.workspace_volume.startswith("hermes-workspace-")
        assert backend2.workspace_volume.startswith("hermes-workspace-")
        assert backend1.workspace_volume != backend2.workspace_volume

    def test_backend_uses_custom_workspace_volume(self, mock_client):
        """可通过构造函数传入自定义 workspace_volume 名称。"""
        backend = DockerSandboxBackend(workspace_volume="my-custom-volume")

        assert backend.workspace_volume == "my-custom-volume"

    @pytest.mark.asyncio
    async def test_create_container_mounts_workspace_volume(self, mock_client):
        """create_container 应挂载 workspace volume 到 /workspace。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "ws123"
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(workspace_volume="test-ws")

        await backend.create_container()

        _, kwargs = mock_client.containers.create.call_args
        assert kwargs.get("volumes") == {
            "test-ws": {"bind": "/workspace", "mode": "rw"},
        }

    @pytest.mark.asyncio
    async def test_execute_code_uses_workspace_volume(self, mock_client):
        """execute_code 自动创建的容器也应挂载 workspace volume。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "execws123"
        mock_container.exec_run.return_value = (0, (b"ok", b""))
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(workspace_volume="test-ws")

        await backend.execute_code("print('ok')")

        _, kwargs = mock_client.containers.create.call_args
        assert kwargs.get("volumes") == {
            "test-ws": {"bind": "/workspace", "mode": "rw"},
        }

    @pytest.mark.asyncio
    async def test_put_file_uses_workspace_volume(self, mock_client):
        """put_file 自动创建的容器也应挂载 workspace volume。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "putws123"
        mock_container.put_archive.return_value = True
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(workspace_volume="test-ws")

        await backend.put_file("/workspace/data.txt", b"hello")

        _, kwargs = mock_client.containers.create.call_args
        assert kwargs.get("volumes") == {
            "test-ws": {"bind": "/workspace", "mode": "rw"},
        }

    @pytest.mark.asyncio
    async def test_get_file_uses_workspace_volume(self, mock_client):
        """get_file 应通过挂载 workspace volume 的池化容器读取。"""
        expected = b"workspace content"
        tar_bytes = TestDockerSandboxBackendFileTransfer._make_tar_bytes(
            "/workspace/read.txt", expected
        )
        mock_container = MagicMock(spec=Container)
        mock_container.id = "getws123"
        mock_container.get_archive.return_value = (iter([tar_bytes]), {"size": len(expected)})
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend(workspace_volume="test-ws")

        content = await backend.get_file("/workspace/read.txt")

        assert content == expected
        mock_container.get_archive.assert_called_once_with("/workspace/read.txt")

    def test_close_removes_workspace_volume_when_cleanup_enabled(self, mock_client):
        """cleanup_workspace=True 时，close() 应删除 workspace volume。"""
        mock_volume = MagicMock()
        mock_client.volumes.get.return_value = mock_volume
        backend = DockerSandboxBackend(workspace_volume="test-ws")

        backend.close()

        mock_client.volumes.get.assert_called_once_with("test-ws")
        mock_volume.remove.assert_called_once()

    def test_close_keeps_workspace_volume_when_cleanup_disabled(self, mock_client):
        """cleanup_workspace=False 时，close() 不应删除 workspace volume。"""
        backend = DockerSandboxBackend(
            workspace_volume="test-ws", cleanup_workspace=False
        )

        backend.close()

        mock_client.volumes.get.assert_not_called()

    def test_close_ignores_volume_cleanup_errors(self, mock_client):
        """volume 删除失败时不应抛出异常。"""
        mock_client.volumes.get.side_effect = Exception("volume not found")
        backend = DockerSandboxBackend(workspace_volume="test-ws")

        backend.close()  # 不应抛异常

        mock_client.volumes.get.assert_called_once_with("test-ws")


class TestImageRegistry:
    """TD-007：镜像源配置与 ensure_image 拉取/打标行为。"""

    def test_resolve_pull_image_official_adds_library(self, mock_client):
        """官方镜像 + registry → {registry}/library/{image}。"""
        backend = DockerSandboxBackend(image_registry="docker.m.daocloud.io")
        assert (
            backend._resolve_pull_image()
            == "docker.m.daocloud.io/library/python:3.11-slim"
        )

    def test_resolve_pull_image_namespaced_no_library(self, mock_client):
        """含命名空间的镜像不再加 library/ 前缀。"""
        backend = DockerSandboxBackend(
            image="myorg/myimg:1.0", image_registry="docker.m.daocloud.io"
        )
        assert backend._resolve_pull_image() == "docker.m.daocloud.io/myorg/myimg:1.0"

    def test_resolve_pull_image_no_registry_returns_image(self, mock_client):
        """未配置 registry 时拉取名等于 image 原名。"""
        backend = DockerSandboxBackend()
        assert backend._resolve_pull_image() == "python:3.11-slim"

    def test_resolve_pull_image_strips_scheme_and_slash(self, mock_client):
        """registry 带 scheme/尾部斜杠时自动清理。"""
        backend = DockerSandboxBackend(
            image_registry="https://docker.m.daocloud.io/"
        )
        assert (
            backend._resolve_pull_image()
            == "docker.m.daocloud.io/library/python:3.11-slim"
        )

    @pytest.mark.asyncio
    async def test_ensure_image_pulls_from_registry_and_tags(self, mock_client):
        """本地无镜像时：从 registry 拉取并打标回原名。"""
        mock_client.images.list.return_value = []
        pulled = MagicMock()
        mock_client.images.pull.return_value = pulled
        backend = DockerSandboxBackend(image_registry="docker.m.daocloud.io")

        result = await backend.ensure_image()

        assert result is True
        mock_client.images.pull.assert_called_once_with(
            "docker.m.daocloud.io/library/python:3.11-slim"
        )
        pulled.tag.assert_called_once_with("python:3.11-slim")

    @pytest.mark.asyncio
    async def test_ensure_image_no_registry_no_tag(self, mock_client):
        """无 registry 时按原名拉取，不打标。"""
        mock_client.images.list.return_value = []
        mock_client.images.pull.return_value = MagicMock()
        backend = DockerSandboxBackend()

        result = await backend.ensure_image()

        assert result is True
        mock_client.images.pull.assert_called_once_with("python:3.11-slim")

    @pytest.mark.asyncio
    async def test_ensure_image_local_exists_skips_pull(self, mock_client):
        """本地已有镜像时跳过拉取（即使配置了 registry）。"""
        mock_client.images.list.return_value = [MagicMock(tags=["python:3.11-slim"])]
        backend = DockerSandboxBackend(image_registry="docker.m.daocloud.io")

        result = await backend.ensure_image()

        assert result is True
        mock_client.images.pull.assert_not_called()


class TestWorkspacePermissionFix:
    """EVAL-010：workspace volume 权限修复（nobody 可写）。"""

    @pytest.mark.asyncio
    async def test_create_container_chowns_workspace(self, mock_client):
        """容器创建后应以 root 执行 chown，把 /workspace 属主改为 nobody。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "chown123"
        mock_container.exec_run.return_value = (0, b"")
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        await backend.create_container()

        chown_calls = [
            c for c in mock_container.exec_run.call_args_list
            if "chown" in str(c)
        ]
        assert len(chown_calls) == 1
        args, kwargs = chown_calls[0]
        assert "65534:65534" in args[0]
        assert kwargs.get("user") == "root"

    @pytest.mark.asyncio
    async def test_chown_failure_does_not_block_creation(self, mock_client):
        """chown 失败时容器创建不失败（警告降级）。"""
        mock_container = MagicMock(spec=Container)
        mock_container.id = "chown-fail"
        mock_container.exec_run.return_value = (1, b"operation not permitted")
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()

        container = await backend.create_container()
        assert container is not None

    @pytest.mark.asyncio
    async def test_put_file_tar_uses_nobody_uid(self, mock_client):
        """put_file 注入的文件 tar 条目应使用 nobody uid/gid（65534）。"""
        import tarfile as tf

        mock_container = MagicMock(spec=Container)
        mock_container.id = "tar123"
        mock_container.put_archive.return_value = True
        mock_client.containers.create.return_value = mock_container
        backend = DockerSandboxBackend()
        await backend.create_container()

        await backend.put_file("/workspace/a.txt", b"data")

        args, _ = mock_container.put_archive.call_args
        tar_bytes = args[1]
        with tf.open(fileobj=__import__("io").BytesIO(tar_bytes), mode="r") as tar:
            member = tar.getmembers()[0]
            assert member.uid == 65534
            assert member.gid == 65534
