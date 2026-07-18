"""SubprocessSandboxBackend 单元测试（TD-002）。

覆盖轻量 subprocess 沙箱后端的核心行为：
  - ping / 生命周期 no-op 接口
  - execute_code 成功、失败、超时
  - put_file / get_file 闭环与 workspace 路径映射
  - 路径逃逸（../）防护
  - close 清理临时目录、实例间 workspace 隔离

全部使用真实子进程执行，不依赖 Docker daemon。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.sandbox.subprocess_backend import SubprocessSandboxBackend


class TestLifecycle:
    """生命周期与 no-op 对齐接口。"""

    @pytest.mark.asyncio
    async def test_ping_always_true(self) -> None:
        """ping 恒为 True，不依赖任何外部服务。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.ping() is True
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_noop_interfaces(self) -> None:
        """ensure_image / create_container / remove_container / warmup 降级为 no-op。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.ensure_image() is True
            assert await backend.create_container() is not None
            assert await backend.remove_container() is True
            assert await backend.warmup() is True
        finally:
            backend.close()

    def test_workspace_isolated_per_instance(self) -> None:
        """每个实例持有独立的临时 workspace 目录。"""
        b1 = SubprocessSandboxBackend()
        b2 = SubprocessSandboxBackend()
        try:
            assert b1.workspace != b2.workspace
            assert Path(b1.workspace).is_dir()
            assert Path(b2.workspace).is_dir()
        finally:
            b1.close()
            b2.close()

    def test_close_removes_workspace(self) -> None:
        """close 后实例自有临时目录被清理，且 close 幂等。"""
        backend = SubprocessSandboxBackend()
        workspace = Path(backend.workspace)
        assert workspace.is_dir()
        backend.close()
        assert not workspace.exists()
        backend.close()  # 幂等，不抛异常


class TestExecuteCode:
    """execute_code 代码执行。"""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """成功执行：stdout 捕获，exit_code 为 0。"""
        backend = SubprocessSandboxBackend()
        try:
            result = await backend.execute_code("print('hello hermes')")
            assert result.success is True
            assert result.exit_code == 0
            assert "hello hermes" in result.stdout
            assert result.stderr == ""
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_execute_failure(self) -> None:
        """执行失败：stderr 捕获，success 为 False。"""
        backend = SubprocessSandboxBackend()
        try:
            result = await backend.execute_code("raise ValueError('boom')")
            assert result.success is False
            assert result.exit_code != 0
            assert "ValueError" in result.stderr
            assert "boom" in result.stderr
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_execute_timeout(self) -> None:
        """超时：进程被终止，返回失败结果而非挂起。"""
        backend = SubprocessSandboxBackend()
        try:
            result = await backend.execute_code(
                "import time; time.sleep(60)", timeout=1
            )
            assert result.success is False
            assert result.exit_code == -1
            assert "超时" in result.stderr
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_execute_cwd_is_workspace(self) -> None:
        """子进程的工作目录是实例 workspace，保证文件相对路径可见。"""
        backend = SubprocessSandboxBackend()
        try:
            await backend.put_file("/workspace/data.txt", b"payload")
            result = await backend.execute_code(
                "print(open('workspace/data.txt').read())"
            )
            assert result.success is True
            assert "payload" in result.stdout
        finally:
            backend.close()


class TestFileOps:
    """put_file / get_file 文件操作与路径映射。"""

    @pytest.mark.asyncio
    async def test_put_and_get_roundtrip(self) -> None:
        """写入后能原样读回（bytes 闭环）。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.put_file("/workspace/main.py", b"x = 1\n") is True
            assert await backend.get_file("/workspace/main.py") == b"x = 1\n"
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_tmp_path_maps_inside_workspace(self) -> None:
        """/tmp 等 POSIX 路径同样映射进 workspace，不触碰宿主机真实 /tmp。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.put_file("/tmp/scratch.txt", b"tmp") is True
            assert await backend.get_file("/tmp/scratch.txt") == b"tmp"
            expected = Path(backend.workspace) / "tmp" / "scratch.txt"
            assert expected.is_file()
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_get_missing_file_returns_none(self) -> None:
        """读取不存在的文件返回 None。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.get_file("/workspace/nope.txt") is None
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_path_escape_rejected(self) -> None:
        """../ 路径逃逸被拒绝：put 返回 False，get 返回 None。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.put_file("/../evil.txt", b"evil") is False
            assert await backend.get_file("/../evil.txt") is None
            assert not (Path(backend.workspace).parent / "evil.txt").exists()
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_put_creates_parent_dirs(self) -> None:
        """写入深层路径时自动创建父目录。"""
        backend = SubprocessSandboxBackend()
        try:
            assert await backend.put_file("/workspace/a/b/c.txt", b"deep") is True
            assert await backend.get_file("/workspace/a/b/c.txt") == b"deep"
        finally:
            backend.close()


class TestCustomWorkspace:
    """自定义 workspace_root 行为。"""

    @pytest.mark.asyncio
    async def test_custom_workspace_not_removed_on_close(
        self, tmp_path: Path
    ) -> None:
        """外部传入的 workspace 在 close 后保留（非实例自有，不清理）。"""
        backend = SubprocessSandboxBackend(workspace_root=str(tmp_path))
        assert await backend.put_file("/keep.txt", b"k") is True
        backend.close()
        assert (tmp_path / "keep.txt").is_file()


class TestToolIntegration:
    """工具层在 subprocess 后端上的端到端闭环（TD-002 验收）。

    直接调用工具函数并注入 SubprocessSandboxBackend，
    验证「写 → 读 → 列 → 改 → 运行」最小闭环在无 Docker 环境下可用。
    """

    @pytest.mark.asyncio
    async def test_sandbox_exec_tool(self) -> None:
        """sandbox_exec 工具：成功返回 stdout，失败返回 stderr。"""
        from agent.tools import sandbox_exec

        backend = SubprocessSandboxBackend()
        try:
            ok = await sandbox_exec("print(2 + 3)", backend=backend)
            assert ok.success is True
            assert "5" in ok.content

            bad = await sandbox_exec("raise RuntimeError('x')", backend=backend)
            assert bad.success is False
            assert "RuntimeError" in bad.content
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_file_tools_roundtrip(self) -> None:
        """file_write → file_read → file_list → file_edit 完整闭环。"""
        from agent.tools import file_edit, file_list, file_read, file_write

        backend = SubprocessSandboxBackend()
        try:
            w = await file_write("/workspace/main.py", "x = 1\nprint(x)\n", backend=backend)
            assert w.success is True

            r = await file_read("/workspace/main.py", backend=backend)
            assert r.success is True
            assert "x = 1" in r.content

            ls = await file_list("/workspace", backend=backend)
            assert ls.success is True
            assert "main.py" in ls.content

            e = await file_edit(
                "/workspace/main.py", "x = 1", "x = 42", backend=backend
            )
            assert e.success is True

            r2 = await file_read("/workspace/main.py", backend=backend)
            assert "x = 42" in r2.content
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_file_list_missing_dir(self) -> None:
        """file_list 在 subprocess 后端上对缺失目录返回失败而非异常。"""
        from agent.tools import file_list

        backend = SubprocessSandboxBackend()
        try:
            result = await file_list("/workspace/no_such_dir", backend=backend)
            assert result.success is False
        finally:
            backend.close()

    @pytest.mark.asyncio
    async def test_write_then_execute_code_sees_file(self) -> None:
        """file_write 写入的文件能被 sandbox_exec 执行的代码读取（workspace 一致）。"""
        from agent.tools import file_write, sandbox_exec

        backend = SubprocessSandboxBackend()
        try:
            await file_write("/workspace/data.txt", "shared", backend=backend)
            result = await sandbox_exec(
                "print(open('workspace/data.txt').read())", backend=backend
            )
            assert result.success is True
            assert "shared" in result.content
        finally:
            backend.close()
