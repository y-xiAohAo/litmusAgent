"""反思策略生成器 —— 把错误模式转化为结构化恢复建议。

这个模块解决的核心问题：Agent 已经知道「某个错误出现了 N 次」，
但它应该对 LLM 说什么、说到什么程度？

设计要点：
  - 硬编码规则 + 计数阈值，不调用 LLM，保证确定性和低成本。
  - 按异常类型定制升级路径，不同错误有不同的恢复语义。
  - 复用 6.1 的 `_extract_message_signature()` 做轻量签名收敛分析。
  - 输出结构化 dict，方便 6.3 接入主循环和 Trace。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.core.error_handler import ErrorSeverity, RecoveryAction
from agent.core.error_pattern import ErrorPattern, _extract_message_signature

# 按异常类型定制的升级路径。
# 每个路径是一个有序列表，从初始策略到最终策略。
# 例如 NameError 会先 CHECK_CONTEXT，再 SIMPLIFY_TASK，最后 REPORT。
_ESCALATION_PATHS: dict[str, list[tuple[ErrorSeverity, RecoveryAction]]] = {
    # --- 可恢复：需要先检查环境 ---
    "NameError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "KeyError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "AttributeError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "ImportError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "ModuleNotFoundError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "FileNotFoundError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],

    # --- 可恢复：代码需要重写 ---
    "SyntaxError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "IndentationError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "TypeError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "ValueError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "ZeroDivisionError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "IndexError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],

    # --- 降级：任务太重 ---
    "MemoryError": [
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "TimeoutError": [
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "RecursionError": [
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],

    # --- 致命：无法恢复 ---
    "PermissionError": [
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    "UnknownError": [
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
}


def _choose_escalation_stage(
    count: int, escalate_threshold: int, fatal_threshold: int, max_stage: int,
) -> int:
    """根据出现次数选择升级路径中的阶段。

    规则：
      - count < escalate_threshold → stage 0（初始策略）
      - escalate_threshold <= count < fatal_threshold → stage 1
      - count >= fatal_threshold → stage 2（如果存在）

    Args:
        count: 错误出现次数。
        escalate_threshold: 开始升级的阈值。
        fatal_threshold: 升级到最终阶段的阈值。
        max_stage: 该异常类型升级路径的最大有效阶段索引。

    Returns:
        选择的阶段索引。
    """
    if count < escalate_threshold:
        return 0
    if count < fatal_threshold:
        return min(1, max_stage)
    return min(2, max_stage)


@dataclass
class ReflectionAdvice:
    """反思策略生成器返回的结构化建议。

    Attributes:
        hint: 追加给 LLM 的反思提示文本；如果不需要提示，为空字符串。
        severity: 原始或升级后的严重程度。
        action: 原始或升级后的恢复策略。
        is_escalated: 是否发生了 severity/action 升级。
        reflection_payload: 供 Trace 记录的结构化数据。
    """

    hint: str
    severity: ErrorSeverity
    action: RecoveryAction
    is_escalated: bool
    reflection_payload: dict[str, Any]


class ReflectiveAdvisor:
    """基于硬编码规则生成反思建议和恢复策略升级。

    这个类不调用 LLM，只根据错误模式的出现次数、异常类型和最近消息签名
    做确定性决策。

    Attributes:
        reflection_threshold: 开始生成反思提示的重复次数，默认 2。
        escalate_threshold: 开始升级恢复策略的重复次数，默认 4。
        fatal_threshold: 升级到最终阶段（通常是 FATAL + REPORT）的重复次数，
            默认 escalate_threshold + 2。
    """

    def __init__(
        self,
        reflection_threshold: int = 2,
        escalate_threshold: int = 4,
        fatal_threshold: int | None = None,
    ) -> None:
        """初始化反思策略生成器。

        Args:
            reflection_threshold: 开始生成反思提示的重复次数。
            escalate_threshold: 开始升级 severity/action 的重复次数。
            fatal_threshold: 升级到最终阶段的重复次数；为 None 时使用
                escalate_threshold + 2。
        """
        self.reflection_threshold = reflection_threshold
        self.escalate_threshold = escalate_threshold
        self.fatal_threshold = (
            fatal_threshold if fatal_threshold is not None else escalate_threshold + 2
        )

    def advise(
        self,
        pattern: ErrorPattern,
        severity: ErrorSeverity,
        action: RecoveryAction,
    ) -> ReflectionAdvice:
        """根据错误模式生成反思建议。

        Args:
            pattern: 当前错误模式，来自 ErrorPatternLedger。
            severity: 错误分类器给出的当前严重程度。
            action: 错误分类器给出的当前恢复策略。

        Returns:
            结构化的 ReflectionAdvice，包含提示文本和可能升级后的策略。
        """
        # 次数不足，不生成任何反思提示，也不做签名分析
        if pattern.count < self.reflection_threshold:
            return ReflectionAdvice(
                hint="",
                severity=severity,
                action=action,
                is_escalated=False,
                reflection_payload=self._build_payload(
                    pattern, None, "", severity, action, False,
                ),
            )

        # 分类器已判定为 FATAL 的错误无需再反思提示，直接保持原策略
        if severity == ErrorSeverity.FATAL:
            return ReflectionAdvice(
                hint="",
                severity=severity,
                action=action,
                is_escalated=False,
                reflection_payload=self._build_payload(
                    pattern, None, "", severity, action, False,
                ),
            )

        signature = self._resolve_signature(pattern)
        target_severity, target_action, is_escalated = self._resolve_strategy(
            pattern, severity, action,
        )
        hint = self._build_hint(pattern, signature, target_severity, is_escalated)

        return ReflectionAdvice(
            hint=hint,
            severity=target_severity,
            action=target_action,
            is_escalated=is_escalated,
            reflection_payload=self._build_payload(
                pattern, signature, hint, target_severity, target_action, is_escalated,
            ),
        )

    def _resolve_strategy(
        self,
        pattern: ErrorPattern,
        severity: ErrorSeverity,
        action: RecoveryAction,
    ) -> tuple[ErrorSeverity, RecoveryAction, bool]:
        """确定最终的 severity 和 action，以及是否发生了升级。

        以 ErrorClassifier 输出的 (severity, action) 作为当前阶段，
        根据重复次数在升级路径中向上推进；如果当前阶段不在预设路径中，
        则直接尊重分类器输出，不做覆盖。
        """
        path = _ESCALATION_PATHS.get(pattern.exc_type, [
            (ErrorSeverity.FATAL, RecoveryAction.REPORT),
        ])
        max_stage = len(path) - 1

        try:
            current_stage = path.index((severity, action))
        except ValueError:
            # 自定义分类器的输出不在预设路径中：尊重它，不升级
            return severity, action, False

        if pattern.count < self.escalate_threshold:
            target_stage = current_stage
        elif pattern.count < self.fatal_threshold:
            target_stage = min(current_stage + 1, max_stage)
        else:
            target_stage = min(current_stage + 2, max_stage)

        target_severity, target_action = path[target_stage]
        is_escalated = target_stage > current_stage
        return target_severity, target_action, is_escalated

    def _resolve_signature(self, pattern: ErrorPattern) -> str | None:
        """对最近错误消息做签名收敛分析。

        如果某个签名在消息中占多数，返回该签名；否则返回 None。
        """
        if not pattern.messages:
            return None

        signatures: dict[str, int] = {}
        for msg in pattern.messages:
            sig = _extract_message_signature(pattern.exc_type, msg)
            if sig is not None:
                signatures[sig] = signatures.get(sig, 0) + 1

        if not signatures:
            return None

        most_common_sig, max_count = max(signatures.items(), key=lambda item: item[1])
        if max_count > len(pattern.messages) / 2:
            return most_common_sig
        return None

    def _build_hint(
        self,
        pattern: ErrorPattern,
        signature: str | None,
        severity: ErrorSeverity,
        is_escalated: bool,
    ) -> str:
        """根据模式、签名和最终策略生成中文反思提示。"""
        exc_type = pattern.exc_type
        count = pattern.count

        if severity == ErrorSeverity.FATAL and is_escalated:
            return (
                f"警告：{exc_type} 已反复出现 {count} 次，自动恢复可能性较低，"
                "建议终止当前任务并向用户说明情况。"
            )

        if is_escalated:
            base = (
                f"注意：{exc_type} 已累计出现 {count} 次，问题可能不是单次偶然错误。"
            )
        else:
            base = f"注意：{exc_type} 已多次出现（当前第 {count} 次）。"

        if signature is not None:
            detail = (
                f"且多与 '{signature}' 有关，建议先检查相关变量/键/属性"
                "是否已正确声明或导入。"
            )
        else:
            detail = "建议检查代码逻辑或环境状态，必要时换用更简单的方法。"

        return base + detail

    def _build_payload(
        self,
        pattern: ErrorPattern,
        signature: str | None,
        hint: str,
        severity: ErrorSeverity,
        action: RecoveryAction,
        is_escalated: bool,
    ) -> dict[str, Any]:
        """构造供 Trace 使用的 reflection 事件负载。"""
        return {
            "tool_name": pattern.tool_name,
            "exc_type": pattern.exc_type,
            "count": pattern.count,
            "signature": signature,
            "signature_total_messages": len(pattern.messages),
            "hint": hint,
            "severity": severity.name,
            "action": action.name,
            "is_escalated": is_escalated,
        }
