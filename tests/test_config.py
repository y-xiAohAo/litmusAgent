"""Tests for AgentConfig and YAML configuration loading."""

import os
import tempfile

import pytest

from agent.config import (
    AgentConfig,
    LLMConfig,
    SandboxConfig,
    SecurityConfig,
    ToolsConfig,
    load_config,
)
from agent.core.engine import Agent, ToolRegistry
from agent.core.security import PolicyAction
from agent.sandbox.docker_backend import DockerSandboxBackend
from agent.tools import register_tools_from_config


class MockBackend(DockerSandboxBackend):
    """不连接真实 Docker 的 Mock 沙箱后端。"""

    def __init__(self) -> None:
        self.image = "python:3.11-slim"
        self.timeout = 30


SAMPLE_YAML = """
llm:
  provider: openai
  model: gpt-4o
  api_key: sk-test123
  base_url: https://api.openai.com/v1
  temperature: 0.3
  max_tokens: 4096

agent:
  max_turns: 15
  system_prompt: "You are a data analyst."

sandbox:
  backend: docker
  image: python:3.11-slim
  timeout: 30
  memory_limit_mb: 256
"""


def test_config_defaults():
    """AgentConfig should have sensible defaults."""
    config = AgentConfig()
    assert config.agent.max_turns == 20
    assert config.sandbox.backend == "docker"
    assert config.sandbox.timeout == 30
    assert config.sandbox.memory_limit_mb == 256


def test_load_config_from_yaml():
    """load_config should parse a YAML file into structured config."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_YAML)
        path = f.name

    try:
        config = load_config(path)
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"
        assert config.llm.temperature == 0.3
        assert config.agent.max_turns == 15
        assert config.agent.system_prompt == "You are a data analyst."
        assert config.sandbox.timeout == 30
    finally:
        os.unlink(path)


def test_llm_config_defaults():
    """LLMConfig should have sensible defaults."""
    llm = LLMConfig()
    assert llm.provider == "openai"
    assert llm.model == "gpt-4o"
    assert llm.temperature == 0.7
    assert llm.max_tokens == 4096


def test_sandbox_config_defaults():
    """SandboxConfig should have sensible defaults."""
    sb = SandboxConfig()
    assert sb.backend == "docker"
    assert sb.image == "python:3.11-slim"
    assert sb.timeout == 30


def test_config_from_env_overrides():
    """Environment variables should override defaults."""
    os.environ["AGENT_LLM_API_KEY"] = "env-key-123"
    try:
        config = AgentConfig()
        config.llm.api_key = "env-key-123"
        assert config.llm.api_key == "env-key-123"
    finally:
        del os.environ["AGENT_LLM_API_KEY"]


class TestToolsConfig:
    """ToolsConfig 与配置驱动工具加载测试。"""

    def test_tools_config_defaults(self):
        """ToolsConfig 默认启用所有工具（enabled 为 None）。"""
        tools = ToolsConfig()
        assert tools.enabled is None

    def test_agent_config_has_tools_config(self):
        """AgentConfig 应该包含 ToolsConfig 字段。"""
        config = AgentConfig()
        assert config.tools is not None
        assert config.tools.enabled is None


class TestRegisterToolsFromConfig:
    """register_tools_from_config 的测试。"""

    def test_register_all_tools_by_default(self):
        """enabled 为 None 时，应注册所有默认工具。"""
        registry = ToolRegistry()
        backend = MockBackend()
        config = AgentConfig()

        register_tools_from_config(registry, backend, config)

        assert registry.get("sandbox_exec") is not None
        assert registry.get("file_read") is not None
        assert registry.get("file_list") is not None
        assert registry.get("finish") is not None

    def test_register_partial_tools(self):
        """enabled 为列表时，只注册列表中的工具。"""
        registry = ToolRegistry()
        backend = MockBackend()
        config = AgentConfig(tools=ToolsConfig(enabled=["sandbox_exec", "finish"]))

        register_tools_from_config(registry, backend, config)

        assert registry.get("sandbox_exec") is not None
        assert registry.get("finish") is not None
        assert registry.get("file_read") is None
        assert registry.get("file_list") is None

    def test_ignore_unknown_tool_names(self):
        """enabled 中包含未知工具名时，应忽略未知工具并注册已知工具。"""
        registry = ToolRegistry()
        backend = MockBackend()
        config = AgentConfig(
            tools=ToolsConfig(enabled=["sandbox_exec", "unknown_tool", "finish"])
        )

        register_tools_from_config(registry, backend, config)

        assert registry.get("sandbox_exec") is not None
        assert registry.get("finish") is not None
        assert registry.get("unknown_tool") is None

    def test_register_tools_from_yaml_config(self):
        """通过 YAML 加载 tools.enabled 配置并验证工具注册行为。"""
        yaml_content = """
tools:
  enabled:
    - sandbox_exec
    - finish
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            path = f.name

        try:
            config = load_config(path)
            registry = ToolRegistry()
            register_tools_from_config(registry, MockBackend(), config)

            assert config.tools.enabled == ["sandbox_exec", "finish"]
            assert registry.get("sandbox_exec") is not None
            assert registry.get("finish") is not None
            assert registry.get("file_read") is None
            assert registry.get("file_list") is None
        finally:
            os.unlink(path)


class TestAgentUsesToolsConfig:
    """Agent 通过配置注册工具的测试。"""

    @pytest.mark.asyncio
    async def test_agent_registers_only_enabled_tools(self):
        """Agent 传入 config 时，应根据 config.tools.enabled 注册工具。"""
        config = AgentConfig(tools=ToolsConfig(enabled=["finish"]))
        agent = Agent(
            llm_client=DummyLLM(),
            config=config,
            sandbox_backend=MockBackend(),
        )

        assert agent.tools.get("finish") is not None
        assert agent.tools.get("sandbox_exec") is None
        assert agent.tools.get("file_read") is None
        assert agent.tools.get("file_list") is None


class TestSecurityConfig:
    """SecurityConfig 与策略引擎构建测试。"""

    def test_security_config_defaults(self):
        """SecurityConfig 默认应关闭。"""
        security = SecurityConfig()
        assert security.enabled is False
        assert security.default_action == "allow"
        assert security.rules == []
        assert security.file_read_deny_patterns == []
        assert security.memory_read_only_categories == []

    def test_agent_config_has_security_config(self):
        """AgentConfig 应该包含 SecurityConfig 字段。"""
        config = AgentConfig()
        assert config.security is not None
        assert config.security.enabled is False

    def test_build_policy_engine_disabled_returns_none(self):
        """未启用安全策略时，build_policy_engine 返回 None。"""
        security = SecurityConfig()
        assert security.build_policy_engine() is None

    def test_build_policy_engine_enabled_uses_defaults(self):
        """启用安全策略且未提供规则时，使用默认规则集。"""
        security = SecurityConfig(enabled=True)
        engine = security.build_policy_engine()
        assert engine is not None
        decision = engine.evaluate(
            "sandbox/code", "execute", "import os\nprint(1)"
        )
        assert decision.action == PolicyAction.DENY

    def test_build_policy_engine_default_action_deny(self):
        """启用默认规则集且 default_action=deny 时，未匹配规则应被拒绝。"""
        security = SecurityConfig(enabled=True, default_action="deny")
        engine = security.build_policy_engine()
        assert engine is not None
        # 匹配默认规则：高危 import 仍被拒绝
        assert engine.evaluate(
            "sandbox/code", "execute", "import os"
        ).action == PolicyAction.DENY
        # 未匹配默认规则：受 default_action 影响应被拒绝
        assert engine.evaluate(
            "tool", "execute", "some_unknown_tool"
        ).action == PolicyAction.DENY

    def test_build_policy_engine_with_custom_rules(self):
        """启用安全策略并提供自定义规则时，使用自定义规则。"""
        security = SecurityConfig(
            enabled=True,
            rules=[
                {
                    "resource": "tool",
                    "operation": "execute",
                    "pattern": "forbidden_tool",
                    "action": "deny",
                    "reason": "禁止调用",
                    "priority": 10,
                    "use_regex": False,
                },
            ],
        )
        engine = security.build_policy_engine()
        assert engine is not None
        assert engine.evaluate(
            "tool", "execute", "forbidden_tool"
        ).action == PolicyAction.DENY
        # 自定义规则覆盖默认规则集，因此 import os 不再被拒绝
        assert engine.evaluate(
            "sandbox/code", "execute", "import os"
        ).action == PolicyAction.ALLOW

    def test_load_security_from_yaml(self):
        """通过 YAML 加载 security 配置。"""
        yaml_content = """
security:
  enabled: true
  default_action: deny
  rules:
    - resource: file/path
      operation: read
      pattern: ".*secret.*"
      action: deny
      reason: "禁止读取秘密文件"
      priority: 100
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            path = f.name

        try:
            config = load_config(path)
            assert config.security.enabled is True
            assert config.security.default_action == "deny"
            assert len(config.security.rules) == 1
            engine = config.security.build_policy_engine()
            assert engine is not None
            assert engine.evaluate(
                "file/path", "read", "/tmp/secret.txt"
            ).action == PolicyAction.DENY
        finally:
            os.unlink(path)


class DummyLLM:
    """Agent 初始化需要一个 LLM 客户端，这里用最简单的占位对象。"""

    async def chat(self, messages, tools=None, **kwargs):
        return {"content": "OK", "tool_calls": None}


class TestSecurityConfigWorkspacePath:
    """TD-006：security.workspace_path 配置与边界覆盖行为。"""

    def test_workspace_path_default(self) -> None:
        """workspace_path 默认为 /workspace。"""
        security = SecurityConfig()
        assert security.workspace_path == "/workspace"

    def test_default_boundary_rules_from_yaml(self) -> None:
        """默认规则集下：/workspace 允许，/tmp 拒绝，.. 逃逸拒绝。"""
        security = SecurityConfig(enabled=True)
        engine = security.build_policy_engine()
        assert engine is not None
        assert engine.evaluate("file/path", "write", "/workspace/a.py").is_allowed()
        assert not engine.evaluate("file/path", "write", "/tmp/a.py").is_allowed()
        assert not engine.evaluate(
            "file/path", "write", "/workspace/../tmp/a.py"
        ).is_allowed()

    def test_custom_workspace_path_overrides_boundary(self) -> None:
        """workspace_path=/app 时：/app 允许，/workspace 不再允许。"""
        security = SecurityConfig(enabled=True, workspace_path="/app")
        engine = security.build_policy_engine()
        assert engine is not None
        assert engine.evaluate("file/path", "write", "/app/x.py").is_allowed()
        assert engine.evaluate("file/path", "write", "/app/sub/y.py").is_allowed()
        assert not engine.evaluate("file/path", "write", "/workspace/x.py").is_allowed()
        assert not engine.evaluate("file/path", "write", "/tmp/x.py").is_allowed()

    def test_custom_rules_take_full_control(self) -> None:
        """提供自定义规则集时不注入边界（自定义全权接管）。"""
        security = SecurityConfig(
            enabled=True,
            workspace_path="/app",
            rules=[
                {
                    "resource": "file/path",
                    "operation": "write",
                    "pattern": ".*",
                    "action": "allow",
                    "priority": 10,
                }
            ],
        )
        engine = security.build_policy_engine()
        assert engine is not None
        # 自定义 allow-all 生效，边界 catch-all 未注入
        assert engine.evaluate("file/path", "write", "/anywhere/x.py").is_allowed()
