"""安全策略引擎 —— 统一评估 Agent 各类资源访问请求。

Phase 9 引入的策略引擎用于把代码执行、文件操作、记忆读写等安全规则
系统化、可配置化。默认关闭，开启后使用一组宽松的默认规则集，仅拦截
明显高危的操作。

设计原则：
  1. 轻量：不引入外部策略引擎或 DSL，只用 Python 标准库。
  2. 可配置：规则可以通过 YAML 完全自定义。
  3. 不阻塞主循环：策略拒绝返回 PolicyDecision，由调用方决定如何
     优雅地处理（例如返回 ToolResult(success=False)）。
  4. 默认放行：没有匹配到规则时，行为由 default_action 决定；Phase 9
     默认采用 ALLOW，避免破坏现有功能。

匹配流程：
  1. 过滤 resource 与 operation 同时匹配的规则。
  2. 按 priority 降序排列。
  3. 取第一条 pattern 匹配 subject 的规则返回其决策。
  4. 无匹配时返回 default_action 对应的决策。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

_logger = logging.getLogger(__name__)


class PolicyAction(str, Enum):
    """策略决策动作。"""

    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


@dataclass
class PolicyDecision:
    """单条策略决策结果。"""

    action: PolicyAction
    reason: str = ""

    def is_allowed(self) -> bool:
        """是否被允许。"""
        return self.action == PolicyAction.ALLOW


@dataclass
class PolicyRule:
    """单条策略规则。

    Attributes:
        resource: 资源类型，如 "tool"、"sandbox/code"、"file/path"、
            "memory/category"。
        operation: 操作类型，如 "execute"、"read"、"write"。
        pattern: 匹配 subject 的模式字符串。
        action: 命中后的决策动作。
        reason: 人类可读的拒绝/审查原因。
        priority: 规则优先级，数字越大越优先。
        use_regex: 是否按正则表达式解释 pattern；False 时使用子串匹配。
    """

    resource: str
    operation: str
    pattern: str
    action: PolicyAction
    reason: str = ""
    priority: int = 0
    use_regex: bool = True


class PolicyEngine:
    """策略引擎 —— 按 resource + operation + pattern 评估请求。"""

    def __init__(
        self,
        rules: list[PolicyRule] | None = None,
        default_action: PolicyAction = PolicyAction.ALLOW,
    ) -> None:
        """初始化策略引擎。

        Args:
            rules: 初始规则列表；None 表示空列表。
            default_action: 没有规则命中时的默认决策，默认 ALLOW。
        """
        self._rules: list[PolicyRule] = list(rules) if rules is not None else []
        self._default_action = default_action

    @property
    def default_action(self) -> PolicyAction:
        """获取默认决策动作。"""
        return self._default_action

    def add_rule(self, rule: PolicyRule) -> None:
        """添加一条规则。"""
        self._rules.append(rule)

    def evaluate(
        self,
        resource: str,
        operation: str,
        subject: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """评估单个请求是否被允许。

        匹配逻辑：
          1. 过滤 resource 与 operation 同时匹配的规则。
          2. 按 priority 降序排列。
          3. 取第一条 pattern 匹配 subject 的规则返回其决策。
          4. 无匹配时返回 default_action 对应的决策。

        Args:
            resource: 资源类型。
            operation: 操作类型。
            subject: 被检查的主体内容，如代码字符串、文件路径等。
            context: 可选的上下文信息，供审计或更复杂的规则使用。

        Returns:
            PolicyDecision，包含决策动作和人类可读原因。
        """
        # REVIEW 动作触发时记录审计日志占位；context 也保留供后续扩展。
        _ = context

        # 防御非字符串 subject：LLM 可能传入数字、null 等异常类型，
        # 统一转字符串避免正则匹配抛 TypeError 中断主循环。
        subject = str(subject)

        candidates = [
            rule
            for rule in self._rules
            if rule.resource == resource and rule.operation == operation
        ]
        if not candidates:
            return PolicyDecision(
                action=self._default_action,
                reason="没有匹配的规则，采用默认决策",
            )

        candidates.sort(key=lambda rule: rule.priority, reverse=True)

        for rule in candidates:
            if self._matches(rule, subject):
                if rule.action == PolicyAction.REVIEW:
                    _logger.warning(
                        "策略审查：resource=%s operation=%s pattern=%s subject=%r",
                        rule.resource,
                        rule.operation,
                        rule.pattern,
                        subject[:200],
                    )
                return PolicyDecision(action=rule.action, reason=rule.reason)

        return PolicyDecision(
            action=self._default_action,
            reason="没有匹配的规则，采用默认决策",
        )

    @staticmethod
    def _matches(rule: PolicyRule, subject: str) -> bool:
        """判断规则是否匹配 subject。"""
        if rule.use_regex:
            try:
                return re.search(rule.pattern, subject) is not None
            except re.error:
                # 非法正则退化为子串匹配，避免规则错误导致引擎崩溃。
                _logger.warning("正则表达式非法，退化为子串匹配：%s", rule.pattern)
                return rule.pattern in subject
        return rule.pattern in subject

    @classmethod
    def default(
        cls,
        rules_path: str | Path | None = None,
        default_action: str = "allow",
    ) -> PolicyEngine:
        """从 YAML 文件加载默认宽松规则集。

        默认规则集只在 SecurityConfig.enabled=True 且用户未提供自定义规则
        时启用，目的是拦截明显高危的操作，同时不影响正常开发任务。

        Args:
            rules_path: 自定义规则文件路径；None 时使用包内默认规则文件
                `default_security_rules.yaml`。
            default_action: 默认决策动作，"allow" 或 "deny"。

        Returns:
            加载好默认规则的 PolicyEngine。

        Raises:
            FileNotFoundError: 默认规则文件不存在。
            ValueError: YAML 格式损坏、规则字段不合法或 default_action 不合法。
        """
        if rules_path is None:
            data = (
                files("agent.core")
                .joinpath("default_security_rules.yaml")
                .read_text(encoding="utf-8")
            )
        else:
            data = Path(rules_path).read_text(encoding="utf-8")

        raw: dict[str, Any] = yaml.safe_load(data) or {}

        rules = raw.get("rules")
        if rules is None:
            raise ValueError("默认规则文件缺少 'rules' 顶层键")

        return cls.from_config(rules=rules, default_action=default_action)

    @classmethod
    def from_config(
        cls,
        rules: list[dict[str, Any]] | None,
        default_action: str = "allow",
    ) -> PolicyEngine:
        """从配置字典列表构建策略引擎。

        Args:
            rules: 规则字典列表；None 或空列表时使用默认规则集。
            default_action: 默认动作字符串，"allow" 或 "deny"。

        Returns:
            配置好的 PolicyEngine 实例。

        Raises:
            ValueError: 规则字典缺少必要字段或 action 不合法。
        """
        action_map = {
            "allow": PolicyAction.ALLOW,
            "deny": PolicyAction.DENY,
            "review": PolicyAction.REVIEW,
        }
        default = action_map.get(default_action)
        if default is None:
            raise ValueError(f"default_action 不合法：{default_action}")

        rules = rules or []
        parsed_rules: list[PolicyRule] = []
        for idx, raw in enumerate(rules):
            for field in ("resource", "operation", "pattern", "action"):
                if field not in raw:
                    raise ValueError(
                        f"规则第 {idx} 条缺少必要字段：{field}"
                    )
            action = action_map.get(raw["action"])
            if action is None:
                raise ValueError(
                    f"规则第 {idx} 条 action 不合法：{raw['action']}"
                )
            parsed_rules.append(
                PolicyRule(
                    resource=str(raw["resource"]),
                    operation=str(raw["operation"]),
                    pattern=str(raw["pattern"]),
                    action=action,
                    reason=str(raw.get("reason", "")),
                    priority=int(raw.get("priority", 0)),
                    use_regex=bool(raw.get("use_regex", True)),
                )
            )

        return cls(rules=parsed_rules, default_action=default)
