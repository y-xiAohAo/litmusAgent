"""RuntimeServices 工厂与统一注册测试（TD-005）。

覆盖：
  - from_config：None 配置 / 压缩启用 / 记忆启用（含 policy 注入）/ 注入优先 / 记忆未启用
  - register_internal_tools：cache→context_read、manager→memory_read、开关关闭、空服务
"""

from __future__ import annotations

from agent.config import AgentConfig
from agent.core.context_cache import ContextCache
from agent.core.engine import ToolRegistry
from agent.core.runtime import RuntimeServices
from agent.core.security import PolicyEngine
from agent.core.state import ExecutionContext


def make_config(**kwargs) -> AgentConfig:  # noqa: ANN003
    """构造带指定覆盖项的 AgentConfig。"""
    config = AgentConfig()
    for key, value in kwargs.items():
        section, _, field_name = key.partition("__")
        setattr(getattr(config.agent, section), field_name, value)
    return config


class TestRuntimeServicesFromConfig:
    """RuntimeServices.from_config 工厂行为。"""

    def test_none_config_returns_empty_services(self) -> None:
        """无配置时：仅 execution_context，无 cache / manager。"""
        ctx = ExecutionContext()
        services = RuntimeServices.from_config(None, None, ctx)
        assert services.execution_context is ctx
        assert services.context_cache is None
        assert services.memory_manager is None

    def test_compression_enabled_creates_cache(self) -> None:
        """启用压缩时创建默认 ContextCache。"""
        config = make_config(compression__enabled=True)
        services = RuntimeServices.from_config(config, None, ExecutionContext())
        assert services.context_cache is not None
        assert services.memory_manager is None

    def test_memory_enabled_creates_manager_with_policy(self) -> None:
        """启用记忆时创建 MemoryManager，且注入同一 PolicyEngine。"""
        policy = PolicyEngine(rules=[])
        config = make_config(memory__enabled=True)
        services = RuntimeServices.from_config(config, policy, ExecutionContext())
        assert services.memory_manager is not None
        assert getattr(services.memory_manager, "_policy", None) is policy

    def test_injected_dependencies_take_precedence(self) -> None:
        """显式注入的 cache / manager 优先于配置创建。"""
        config = make_config(compression__enabled=True, memory__enabled=True)
        injected_cache = ContextCache(root_dir=".hermes/test-cache", session_id="s1")
        config_mem = make_config(memory__enabled=True)
        injected_manager = RuntimeServices.from_config(
            config_mem, None, ExecutionContext()
        ).memory_manager
        services = RuntimeServices.from_config(
            config,
            None,
            ExecutionContext(),
            context_cache=injected_cache,
            memory_manager=injected_manager,
        )
        assert services.context_cache is injected_cache
        assert services.memory_manager is injected_manager

    def test_memory_disabled_no_manager(self) -> None:
        """记忆未启用（默认）时无 manager。"""
        config = AgentConfig()
        services = RuntimeServices.from_config(config, None, ExecutionContext())
        assert services.memory_manager is None


class TestRegisterInternalTools:
    """register_internal_tools 统一注册编排。"""

    def test_cache_registers_context_read(self) -> None:
        """context_cache 存在时注册 context_read。"""
        from agent.tools import register_internal_tools

        config = make_config(compression__enabled=True)
        services = RuntimeServices.from_config(config, None, ExecutionContext())
        registry = ToolRegistry()
        register_internal_tools(registry, services, config)
        assert registry.get("context_read") is not None
        assert registry.get("memory_read") is None

    def test_manager_registers_memory_read(self) -> None:
        """memory_manager 存在时注册 memory_read。"""
        from agent.tools import register_internal_tools

        config = make_config(memory__enabled=True)
        services = RuntimeServices.from_config(config, None, ExecutionContext())
        registry = ToolRegistry()
        register_internal_tools(registry, services, config)
        assert registry.get("memory_read") is not None
        assert registry.get("context_read") is None

    def test_register_flags_disable_tools(self) -> None:
        """register_context_read / register_memory_read 开关关闭时不注册。"""
        from agent.tools import register_internal_tools

        config = make_config(
            compression__enabled=True,
            memory__enabled=True,
            compression__register_context_read=False,
            memory__register_memory_read=False,
        )
        services = RuntimeServices.from_config(config, None, ExecutionContext())
        registry = ToolRegistry()
        register_internal_tools(registry, services, config)
        assert registry.get("context_read") is None
        assert registry.get("memory_read") is None

    def test_empty_services_register_nothing(self) -> None:
        """空服务（无 cache / manager）不注册任何内部工具。"""
        from agent.tools import register_internal_tools

        services = RuntimeServices(execution_context=ExecutionContext())
        registry = ToolRegistry()
        register_internal_tools(registry, services, None)
        assert registry.get("context_read") is None
        assert registry.get("memory_read") is None
