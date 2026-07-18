"""Subprocess 沙箱后端 —— Docker 不可用时的轻量 fallback（TD-002）。

设计定位：
  - 每个实例持有独立的临时目录作为 workspace 根，实例间天然隔离。
  - 沙箱内 POSIX 风格路径统一映射进 workspace：
    `/workspace/main.py` → `<workspace>/workspace/main.py`，
    `/tmp/a.txt` → `<workspace>/tmp/a.txt`。
    与 Docker 后端的 `/workspace`（持久）/ `/tmp`（临时）约定保持语义一致，
    且不会触碰宿主机真实文件系统。
  - 所有文件操作在 resolve 后强制校验位于 workspace 内，防止 `../` 逃逸。
  - 使用 `asyncio.create_subprocess_exec` 实现真正的 async 执行，
    接口与 `DockerSandboxBackend` 对齐，工具层零感知。

明确放弃（Non-Goals，见 technical-debt-spec TD-002）：
  - 不提供 Docker 级别的安全隔离（无 cgroup / seccomp / user namespace）。
  - 不真正禁用网络（仅通过环境变量 `HERMES_SANDBOX` 标记沙箱进程）。
  - 不实现容器预热池，`create_container` / `warmup` 等降级为 no-op。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from agent.sandbox.base import ExecutionResult

logger = logging.getLogger(__name__)


class SubprocessSandboxBackend:
    """基于本地子进程的轻量沙箱后端。

    参数：
        timeout: 默认执行超时（秒），可被 `execute_code` 的参数覆盖。
        workspace_root: 可选的外部 workspace 目录；不传时创建实例自有的
            临时目录，并在 `close()` 时清理。外部传入的目录不会被清理。
    """

    def __init__(self, timeout: int = 30, workspace_root: str | None = None) -> None:
        self._timeout = timeout
        self._owns_workspace = workspace_root is None
        self._workspace = (
            Path(tempfile.mkdtemp(prefix="hermes-subproc-"))
            if workspace_root is None
            else Path(workspace_root)
        )
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._closed = False

    @property
    def workspace(self) -> str:
        """实例 workspace 根目录的宿主机绝对路径。"""
        return str(self._workspace)

    def _resolve(self, container_path: str) -> Path:
        """把沙箱内 POSIX 路径映射为 workspace 内的宿主机路径。

        映射规则：去掉开头的 `/` 后直接拼到 workspace 根下。
        resolve 后必须仍在 workspace 内，否则视为路径逃逸并抛 `ValueError`。
        """
        rel = container_path.replace("\\", "/").lstrip("/")
        root = self._workspace.resolve()
        candidate = (root / rel).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"路径逃逸 workspace：{container_path!r}")
        return candidate

    async def ping(self) -> bool:
        """轻量后端无外部依赖，恒返回 True。"""
        return True

    async def ensure_image(self) -> bool:
        """接口对齐 no-op：无镜像概念，恒返回 True。"""
        return True

    async def create_container(self) -> str | None:
        """接口对齐 no-op：无容器概念，返回 workspace 路径作为标识。"""
        return str(self._workspace)

    async def remove_container(self) -> bool:
        """接口对齐 no-op：无容器概念，恒返回 True。"""
        return True

    async def warmup(self, count: int = 2) -> bool:
        """接口对齐 no-op：无预热池，恒返回 True。"""
        return True

    async def execute_code(self, code: str, timeout: int | None = None) -> ExecutionResult:
        """在子进程中执行 Python 代码并捕获结果。

        执行方式：把代码写入 workspace 内的临时脚本，以 workspace 为 cwd
        调起当前 Python 解释器运行，按 timeout 限时；超时则 kill 进程。

        返回：
            ExecutionResult。成功时 exit_code == 0；运行失败时保留真实
            退出码；超时或启动失败时 exit_code == -1。
        """
        effective_timeout = timeout if timeout is not None else self._timeout
        script = self._workspace / f"_exec_{uuid.uuid4().hex}.py"
        try:
            script.write_text(code, encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script),
                cwd=str(self._workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "HERMES_SANDBOX": "subprocess"},
            )
            try:
                out, err = await asyncio.wait_for(
                    proc.communicate(), timeout=effective_timeout
                )
            except (TimeoutError, asyncio.TimeoutError):
                proc.kill()
                await proc.wait()
                return ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"执行超时（>{effective_timeout}s），子进程已被终止。",
                    success=False,
                )
            stdout = out.decode("utf-8", errors="replace")
            stderr = err.decode("utf-8", errors="replace")
            exit_code = proc.returncode if proc.returncode is not None else -1
            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                success=exit_code == 0,
            )
        except Exception as exc:  # noqa: BLE001 —— 沙箱语义：错误不外抛，转为结果
            logger.warning("subprocess 后端执行失败：%s", exc)
            return ExecutionResult(exit_code=-1, stdout="", stderr=str(exc), success=False)
        finally:
            script.unlink(missing_ok=True)

    async def put_file(self, container_path: str, content: bytes) -> bool:
        """把内容写入沙箱内指定路径（自动创建父目录）。

        路径逃逸或 IO 错误时返回 False 而不是抛异常，与 Docker 后端语义一致。
        """
        try:
            target = self._resolve(container_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return True
        except (ValueError, OSError) as exc:
            logger.warning("put_file 失败：%s -> %s", container_path, exc)
            return False

    async def get_file(self, container_path: str) -> bytes | None:
        """读取沙箱内指定路径的文件内容。

        文件不存在、路径逃逸或 IO 错误时返回 None，与 Docker 后端语义一致。
        """
        try:
            target = self._resolve(container_path)
        except ValueError:
            return None
        if not target.is_file():
            return None
        try:
            return target.read_bytes()
        except OSError:
            return None

    async def list_dir(self, container_path: str) -> list[str] | None:
        """列出沙箱内指定目录下的文件和子目录（可选能力，非 Protocol 成员）。

        `file_list` 工具优先调用本方法；它直接走 `_resolve` 路径映射，
        避免经 `execute_code` 执行绝对路径 `os.listdir` 时绕过 workspace。

        返回：目录项名称列表；目录不存在、非目录或路径逃逸时返回 None。
        """
        try:
            target = self._resolve(container_path)
        except ValueError:
            return None
        if not target.is_dir():
            return None
        try:
            return sorted(p.name for p in target.iterdir())
        except OSError:
            return None

    def close(self) -> None:
        """释放资源：清理实例自有的临时 workspace（幂等）。

        外部传入的 `workspace_root` 不属于实例资产，不会被删除。
        """
        if self._closed:
            return
        self._closed = True
        if self._owns_workspace:
            shutil.rmtree(self._workspace, ignore_errors=True)

    async def __aenter__(self) -> SubprocessSandboxBackend:
        """异步上下文管理器入口，与 Docker 后端用法对齐。"""
        return self

    async def __aexit__(self, *args: object) -> None:
        """异步上下文管理器出口：调用 `close()` 释放资源。"""
        self.close()
