"""沙箱后端抽象 —— `ExecutionResult` 数据模型与 `SandboxBackend` 协议。

本模块是 sandbox 层的公共契约：
  - `ExecutionResult`：代码执行结果的数据载体（由 docker_backend 迁入，
    并在原模块 re-export 以保持既有 import 兼容）。
  - `SandboxBackend`：结构化协议（typing.Protocol），`DockerSandboxBackend`
    与 `SubprocessSandboxBackend` 均结构化满足，无需显式继承。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExecutionResult:
    """代码在沙箱中执行后的结果。

    属性：
        exit_code: 进程退出码；0 表示成功，非零表示失败，-1 表示
                   在代码实际运行前就出现了异常（如容器/子进程创建失败或超时）。
        stdout: 标准输出内容。
        stderr: 标准错误内容。
        success: 是否成功执行，等价于 exit_code == 0。
    """

    exit_code: int
    stdout: str
    stderr: str
    success: bool


class SandboxBackend(Protocol):
    """沙箱后端结构化协议。

    工具层与 Agent 只依赖本协议，不关心底层是 Docker 容器还是本地子进程。
    协议只约束工具实际用到的方法；各后端可以额外提供管理接口
    （如 `ensure_image` / `warmup`），不属于协议范围。
    """

    async def ping(self) -> bool:
        """检查后端是否可用。"""
        ...

    async def execute_code(self, code: str, timeout: int | None = None) -> ExecutionResult:
        """在沙箱中执行 Python 代码并返回结果。"""
        ...

    async def put_file(self, container_path: str, content: bytes) -> bool:
        """把文件内容写入沙箱内指定路径。"""
        ...

    async def get_file(self, container_path: str) -> bytes | None:
        """读取沙箱内指定路径的文件内容，不存在时返回 None。"""
        ...

    def close(self) -> None:
        """释放后端持有的资源（容器、临时目录等），要求幂等。"""
        ...
