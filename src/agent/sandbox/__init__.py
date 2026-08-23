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

    抛出：
        ValueError：subprocess 后端配置了 volume_name（TD-015）；
            docker 后端配置了 host_dir 但 Docker daemon 不可用（TD-015 单元 C，
            明确报错不降级——降级到 subprocess 等于在宿主机弱隔离裸跑，更危险）。
    """
    backend = config.backend if config is not None else "docker"
    timeout = config.timeout if config is not None else 30
    volume_name = config.volume_name if config is not None else None
    host_dir = config.host_dir if config is not None else None
    # TD-010：网络策略两个字段（默认 none + False，零行为回归）。
    network_mode = config.network_mode if config is not None else "none"
    allow_setup_network = (
        config.allow_setup_network if config is not None else False
    )

    if backend == "docker":
        # TD-015 单元 B：volume_name → 固定卷 litmus-ws-<name> 且关闭时保留；
        # 未配置 → 随机卷 + 关闭时清理（现状语义）。
        # TD-015 单元 C：host_dir → 宿主目录 bind 挂载替代命名卷。
        if host_dir is not None:
            if allow_setup_network:
                # TD-010 §4.5：bind + 有网 = 攻击面叠加，显式开启时告警。
                logger.warning(
                    "host_dir（bind 模式）下显式开启了 allow_setup_network："
                    "pip 意图的执行将在有网（bridge）容器中直写宿主目录，"
                    "请确认已评估攻击面叠加风险。"
                )
            bind_backend = DockerSandboxBackend(
                image=config.image if config is not None else "python:3.11-slim",
                timeout=timeout,
                image_registry=config.image_registry if config is not None else None,
                workspace_bind=host_dir,
                cleanup_workspace=False,
                network_mode=network_mode,
                allow_setup_network=allow_setup_network,
            )
            if not _docker_available(bind_backend):
                raise ValueError(
                    "host_dir（bind 模式）需要可用的 Docker daemon，但当前 Docker "
                    "不可用，已拒绝启动。bind 模式不会降级到 subprocess——那是在"
                    "宿主机上弱隔离裸跑，风险更高。请启动 Docker 后重试。"
                )
            return bind_backend
        return DockerSandboxBackend(
            image=config.image if config is not None else "python:3.11-slim",
            timeout=timeout,
            image_registry=config.image_registry if config is not None else None,
            workspace_volume=f"litmus-ws-{volume_name}" if volume_name is not None else None,
            cleanup_workspace=volume_name is None,
            network_mode=network_mode,
            allow_setup_network=allow_setup_network,
        )
    if backend == "subprocess":
        if volume_name is not None:
            raise ValueError(
                "subprocess 后端不支持命名卷（volume_name），"
                "请直接使用单元 C 的 host_dir"
            )
        # TD-015 单元 C：subprocess + host_dir 为用户显式 opt-in（自担风险，
        # 弱隔离直写宿主机）；git 快照保险由 CLI 装配层强制执行。
        return SubprocessSandboxBackend(timeout=timeout, workspace_root=host_dir)

    logger.warning("未知的 sandbox.backend：%r，回退到 subprocess 后端", backend)
    return SubprocessSandboxBackend(timeout=timeout)


def _docker_available(backend: DockerSandboxBackend) -> bool:
    """同步检查 Docker daemon 是否可达（bind 模式启动门禁）。"""
    client = backend._get_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False
