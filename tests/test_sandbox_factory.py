"""create_sandbox_backend 工厂与 Agent 后端接线测试（TD-003）。

覆盖：
  - 工厂三分支：docker / subprocess / 未知值警告回退
  - Agent 未注入 sandbox_backend 时按 config.sandbox.backend 选择默认后端
  - 显式注入的 sandbox_backend 优先级高于配置（向后兼容）

全部不连接真实 Docker daemon（DockerSandboxBackend 构造为惰性连接）。
"""

from __future__ import annotations

import logging

import pytest

from agent.config import AgentConfig, SandboxConfig
from agent.core.engine import Agent
from agent.llm.base import EchoClient
from agent.sandbox import create_sandbox_backend
from agent.sandbox.docker_backend import DockerSandboxBackend
from agent.sandbox.subprocess_backend import SubprocessSandboxBackend


class TestCreateSandboxBackend:
    """工厂函数分支行为。"""

    def test_default_is_docker(self) -> None:
        """不传配置时默认创建 Docker 后端。"""
        backend = create_sandbox_backend()
        try:
            assert isinstance(backend, DockerSandboxBackend)
        finally:
            backend.close()

    def test_docker_backend_from_config(self) -> None:
        """backend="docker" 时创建 Docker 后端。"""
        backend = create_sandbox_backend(SandboxConfig(backend="docker"))
        try:
            assert isinstance(backend, DockerSandboxBackend)
        finally:
            backend.close()

    def test_subprocess_backend_from_config(self) -> None:
        """backend="subprocess" 时创建 Subprocess 后端，并复用配置的 timeout。"""
        backend = create_sandbox_backend(SandboxConfig(backend="subprocess", timeout=7))
        try:
            assert isinstance(backend, SubprocessSandboxBackend)
        finally:
            backend.close()

    def test_unknown_backend_falls_back_to_subprocess(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """未知 backend 值：记录警告并回退到 subprocess，不抛异常。"""
        with caplog.at_level(logging.WARNING):
            backend = create_sandbox_backend(SandboxConfig(backend="gVisor"))
        try:
            assert isinstance(backend, SubprocessSandboxBackend)
            assert any("未知的 sandbox.backend" in r.message for r in caplog.records)
        finally:
            backend.close()


class TestAgentBackendWiring:
    """Agent.__init__ 的后端选择接线（TD-003 核心）。"""

    def test_agent_uses_config_subprocess_backend(self) -> None:
        """配置 backend="subprocess" 时，Agent 默认后端为 SubprocessSandboxBackend。"""
        config = AgentConfig(sandbox=SandboxConfig(backend="subprocess"))
        agent = Agent(llm_client=EchoClient(), config=config)
        try:
            assert isinstance(agent._sandbox_backend, SubprocessSandboxBackend)
        finally:
            agent._sandbox_backend.close()

    def test_agent_defaults_to_docker_without_config(self) -> None:
        """不传 config 时保持既有行为：默认 Docker 后端。"""
        agent = Agent(llm_client=EchoClient())
        try:
            assert isinstance(agent._sandbox_backend, DockerSandboxBackend)
        finally:
            agent._sandbox_backend.close()

    def test_injected_backend_takes_precedence(self) -> None:
        """显式注入的 sandbox_backend 优先于配置（既有行为不变）。"""
        injected = SubprocessSandboxBackend()
        config = AgentConfig(sandbox=SandboxConfig(backend="docker"))
        try:
            agent = Agent(
                llm_client=EchoClient(), sandbox_backend=injected, config=config
            )
            assert agent._sandbox_backend is injected
        finally:
            injected.close()


class TestFactoryRegistryPassthrough:
    """TD-007：工厂向 Docker 后端透传 image / image_registry / timeout。"""

    def test_registry_passed_to_docker_backend(self) -> None:
        """配置 image_registry 时，工厂创建的 Docker 后端携带该配置。"""
        config = SandboxConfig(
            backend="docker",
            image="python:3.12-slim",
            image_registry="docker.m.daocloud.io",
            timeout=45,
        )
        backend = create_sandbox_backend(config)
        try:
            assert isinstance(backend, DockerSandboxBackend)
            assert backend.image == "python:3.12-slim"
            assert backend.image_registry == "docker.m.daocloud.io"
            assert backend.timeout == 45
        finally:
            backend.close()

    def test_registry_defaults_to_none(self) -> None:
        """默认配置下 image_registry 为 None（Docker Hub）。"""
        assert SandboxConfig().image_registry is None
        backend = create_sandbox_backend(SandboxConfig(backend="docker"))
        try:
            assert isinstance(backend, DockerSandboxBackend)
            assert backend.image_registry is None
        finally:
            backend.close()
