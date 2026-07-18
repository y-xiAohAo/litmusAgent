"""策略引擎单元测试。"""

from __future__ import annotations

import pytest

from agent.core.security import (
    PolicyAction,
    PolicyDecision,
    PolicyEngine,
    PolicyRule,
)


class TestPolicyDecision:
    def test_default_allow(self) -> None:
        decision = PolicyDecision(action=PolicyAction.ALLOW)
        assert decision.action == PolicyAction.ALLOW
        assert decision.reason == ""
        assert decision.is_allowed() is True

    def test_deny_is_not_allowed(self) -> None:
        decision = PolicyDecision(
            action=PolicyAction.DENY, reason="敏感路径"
        )
        assert decision.is_allowed() is False
        assert decision.reason == "敏感路径"


class TestPolicyEngineBasic:
    def test_no_rules_defaults_to_allow(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate("tool", "execute", "sandbox_exec")
        assert decision.action == PolicyAction.ALLOW
        assert decision.is_allowed() is True

    def test_default_action_deny(self) -> None:
        engine = PolicyEngine(default_action=PolicyAction.DENY)
        decision = engine.evaluate("tool", "execute", "unknown")
        assert decision.action == PolicyAction.DENY

    def test_exact_match_deny(self) -> None:
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="dangerous_tool",
                    action=PolicyAction.DENY,
                    reason="禁止调用该工具",
                    use_regex=False,
                ),
            ],
        )
        assert engine.evaluate(
            "tool", "execute", "dangerous_tool"
        ).action == PolicyAction.DENY
        assert engine.evaluate(
            "tool", "execute", "safe_tool"
        ).action == PolicyAction.ALLOW

    def test_regex_match(self) -> None:
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="file/path",
                    operation="read",
                    pattern=r".*\.ssh.*",
                    action=PolicyAction.DENY,
                    reason="禁止读取 SSH 密钥",
                ),
            ],
        )
        assert engine.evaluate(
            "file/path", "read", "/home/user/.ssh/id_rsa"
        ).action == PolicyAction.DENY
        assert engine.evaluate(
            "file/path", "read", "/tmp/result.txt"
        ).action == PolicyAction.ALLOW

    def test_resource_operation_filtering(self) -> None:
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern=".*",
                    action=PolicyAction.DENY,
                    reason="禁止所有工具",
                ),
            ],
        )
        assert engine.evaluate(
            "tool", "execute", "anything"
        ).action == PolicyAction.DENY
        assert engine.evaluate(
            "file/path", "read", "anything"
        ).action == PolicyAction.ALLOW

    def test_priority_override(self) -> None:
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="sandbox_exec",
                    action=PolicyAction.DENY,
                    priority=0,
                ),
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="sandbox_exec",
                    action=PolicyAction.ALLOW,
                    priority=10,
                ),
            ],
        )
        decision = engine.evaluate("tool", "execute", "sandbox_exec")
        assert decision.action == PolicyAction.ALLOW

    def test_review_action(self, caplog: pytest.LogCaptureFixture) -> None:
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="reviewed_tool",
                    action=PolicyAction.REVIEW,
                    reason="需要审计",
                    use_regex=False,
                ),
            ],
        )
        decision = engine.evaluate("tool", "execute", "reviewed_tool")
        assert decision.action == PolicyAction.REVIEW
        assert "策略审查" in caplog.text


class TestPolicyEngineDefaultLoading:
    def test_default_rules_loaded_from_yaml(self) -> None:
        """默认规则集应从包内 YAML 文件成功加载。"""
        engine = PolicyEngine.default()
        # 验证高危 import 被拒绝，说明 YAML 规则已生效
        assert engine.evaluate(
            "sandbox/code", "execute", "import os"
        ).action == PolicyAction.DENY
        # 验证安全代码被放行
        assert engine.evaluate(
            "sandbox/code", "execute", "print('hello')"
        ).action == PolicyAction.ALLOW


class TestPolicyEngineDefaultRules:
    def test_default_rules_allow_sandbox_exec(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate("tool", "execute", "sandbox_exec")
        assert decision.action == PolicyAction.ALLOW

    def test_default_rules_deny_os_import(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "sandbox/code", "execute", "import os\nprint(os.getcwd())"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_deny_subprocess_import(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "sandbox/code", "execute", "import subprocess\n"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_deny_from_import(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "sandbox/code", "execute", "from os import path\n"
        )
        assert decision.action == PolicyAction.DENY
        decision = engine.evaluate(
            "sandbox/code", "execute", "from os.path import join\n"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_deny_network_import(self) -> None:
        engine = PolicyEngine.default()
        for module in ("socket", "urllib", "requests", "httpx"):
            decision = engine.evaluate(
                "sandbox/code", "execute", f"import {module}\n"
            )
            assert decision.action == PolicyAction.DENY, module

    def test_default_rules_deny_dynamic_import(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "sandbox/code", "execute", "__import__('os')"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_deny_exec_builtin(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "sandbox/code", "execute", "exec('print(1)')"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_allow_safe_code(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "sandbox/code", "execute", "print('hello world')"
        )
        assert decision.action == PolicyAction.ALLOW

    def test_default_rules_deny_etc_passwd(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "file/path", "read", "/etc/passwd"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_deny_ssh_path(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "file/path", "read", "/home/user/.ssh/id_rsa"
        )
        assert decision.action == PolicyAction.DENY

    def test_default_rules_allow_workspace_path(self) -> None:
        engine = PolicyEngine.default()
        decision = engine.evaluate(
            "file/path", "read", "/workspace/result.txt"
        )
        assert decision.action == PolicyAction.ALLOW


class TestPolicyEngineFromConfig:
    def test_from_config_empty_rules_no_defaults(self) -> None:
        engine = PolicyEngine.from_config(rules=[], default_action="allow")
        assert engine.evaluate(
            "sandbox/code", "execute", "import os"
        ).action == PolicyAction.ALLOW

    def test_custom_rules_override_default(self) -> None:
        engine = PolicyEngine.from_config(
            rules=[
                {
                    "resource": "tool",
                    "operation": "execute",
                    "pattern": "forbidden",
                    "action": "deny",
                    "reason": "禁止",
                    "priority": 10,
                    "use_regex": False,
                },
            ],
            default_action="allow",
        )
        assert engine.evaluate(
            "tool", "execute", "forbidden"
        ).action == PolicyAction.DENY
        # 默认规则集不再生效
        assert engine.evaluate(
            "sandbox/code", "execute", "import os"
        ).action == PolicyAction.ALLOW

    def test_default_action_deny_from_config(self) -> None:
        engine = PolicyEngine.from_config(
            rules=[],
            default_action="deny",
        )
        assert engine.evaluate(
            "tool", "execute", "anything"
        ).action == PolicyAction.DENY

    def test_invalid_default_action_raises(self) -> None:
        with pytest.raises(ValueError, match="default_action 不合法"):
            PolicyEngine.from_config(
                rules=[],
                default_action="block",
            )

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="action 不合法"):
            PolicyEngine.from_config(
                rules=[
                    {
                        "resource": "tool",
                        "operation": "execute",
                        "pattern": ".*",
                        "action": "block",
                    },
                ],
            )

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValueError, match="缺少必要字段"):
            PolicyEngine.from_config(
                rules=[{"resource": "tool", "operation": "execute"}],
            )

    def test_invalid_regex_falls_back_to_substring(self) -> None:
        engine = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="[invalid(",
                    action=PolicyAction.DENY,
                    use_regex=True,
                ),
            ],
        )
        # 非法正则退化为子串匹配，因此包含 "[invalid(" 的 subject 会命中
        decision = engine.evaluate(
            "tool", "execute", "prefix [invalid( suffix"
        )
        assert decision.action == PolicyAction.DENY
