"""沙箱层 —— 提供代码执行的隔离环境后端。

包含两种实现：
  - `DockerSandboxBackend`：Docker 容器隔离（最安全，需要 Docker Engine）。
  - `SubprocessSandboxBackend`：本地子进程轻量 fallback（TD-002）。

`create_sandbox_backend()` 工厂根据 `SandboxConfig.backend` 选择默认后端（TD-003）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent.sandbox.base import ExecutionResult, SandboxBackend
from agent.sandbox.docker_backend import DockerSandboxBackend
from agent.sandbox.subprocess_backend import SubprocessSandboxBackend

if TYPE_CHECKING:
    from agent.config import SandboxConfig

logger = logging.getLogger(__name__)

__all__ = [
    "ExecutionResult",
    "SandboxBackend",
    "DockerSandboxBackend",
    "SubprocessSandboxBackend",
    "create_sandbox_backend",
]


def create_sandbox_backend(config: SandboxConfig | None = None) -> SandboxBackend:
    """根据配置创建沙箱后端实例（TD-003）。

    参数：
        config: 沙箱配置；为 None 时按默认 `backend="docker"` 处理。

    返回：
        对应的沙箱后端实例。未知 backend 值记录警告并回退到
        `SubprocessSandboxBackend`（保证无 Docker 环境也能运行）。
    """
    backend = config.backend if config is not None else "docker"
    timeout = config.timeout if config is not None else 30

    if backend == "docker":
        return DockerSandboxBackend(
            image=config.image if config is not None else "python:3.11-slim",
            timeout=timeout,
            image_registry=config.image_registry if config is not None else None,
        )
    if backend == "subprocess":
        return SubprocessSandboxBackend(timeout=timeout)

    logger.warning("未知的 sandbox.backend：%r，回退到 subprocess 后端", backend)
    return SubprocessSandboxBackend(timeout=timeout)
