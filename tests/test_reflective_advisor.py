"""Tests for the reflective error recovery advisor."""

from __future__ import annotations

from agent.core.error_handler import ErrorSeverity, RecoveryAction
from agent.core.error_pattern import ErrorPattern
from agent.core.reflective_advisor import ReflectiveAdvisor


class TestReflectiveAdvisor:
    """Tests for ReflectiveAdvisor — generates hints and escalates recovery strategy."""

    def test_no_reflection_on_first_error(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=1)
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert advice.hint == ""
        assert advice.is_escalated is False
        assert advice.severity == ErrorSeverity.RECOVERABLE
        assert advice.action == RecoveryAction.CHECK_CONTEXT

    def test_reflection_hint_without_escalation(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=2)
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert advice.hint != ""
        assert "多次出现" in advice.hint
        assert advice.is_escalated is False
        assert advice.severity == ErrorSeverity.RECOVERABLE
        assert advice.action == RecoveryAction.CHECK_CONTEXT

    def test_reflection_with_signature_convergence(self):
        advisor = ReflectiveAdvisor()
        messages = [
            "NameError: name 'pd' is not defined",
            "NameError: name 'pd' is not defined",
            "NameError: name 'pd' is not defined",
        ]
        pattern = ErrorPattern(
            tool_name="sandbox_exec", exc_type="NameError", count=3, messages=messages,
        )
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert "pd" in advice.hint
        assert advice.is_escalated is False

    def test_reflection_without_signature(self):
        advisor = ReflectiveAdvisor()
        messages = [
            "NameError: name 'pd' is not defined",
            "NameError: name 'np' is not defined",
            "NameError: name 'df' is not defined",
        ]
        pattern = ErrorPattern(
            tool_name="sandbox_exec", exc_type="NameError", count=3, messages=messages,
        )
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert advice.hint != ""
        assert "pd" not in advice.hint
        assert "np" not in advice.hint
        assert advice.is_escalated is False

    def test_escalation_to_degrade(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=4)
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert advice.is_escalated is True
        assert advice.severity == ErrorSeverity.DEGRADE
        assert advice.action == RecoveryAction.SIMPLIFY_TASK

    def test_escalation_to_fatal(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=6)
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert advice.is_escalated is True
        assert advice.severity == ErrorSeverity.FATAL
        assert advice.action == RecoveryAction.REPORT

    def test_timeout_initial_degrade_escalates_to_fatal(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="TimeoutError", count=4)
        advice = advisor.advise(
            pattern, ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK,
        )

        assert advice.is_escalated is True
        assert advice.severity == ErrorSeverity.FATAL
        assert advice.action == RecoveryAction.REPORT

    def test_type_error_rewrite_code_escalates_to_simplify(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="TypeError", count=4)
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE,
        )

        assert advice.is_escalated is True
        assert advice.severity == ErrorSeverity.DEGRADE
        assert advice.action == RecoveryAction.SIMPLIFY_TASK

    def test_permission_error_no_escalation(self):
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="PermissionError", count=10)
        advice = advisor.advise(
            pattern, ErrorSeverity.FATAL, RecoveryAction.REPORT,
        )

        assert advice.is_escalated is False
        assert advice.severity == ErrorSeverity.FATAL
        assert advice.action == RecoveryAction.REPORT

    def test_custom_thresholds(self):
        advisor = ReflectiveAdvisor(reflection_threshold=3, escalate_threshold=5)

        pattern_below = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=2)
        advice_below = advisor.advise(
            pattern_below, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        pattern_at_threshold = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=3)
        advice_hint = advisor.advise(
            pattern_at_threshold, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        pattern_at_escalate = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=5)
        advice_escalate = advisor.advise(
            pattern_at_escalate, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        assert advice_below.hint == ""
        assert advice_below.is_escalated is False
        assert advice_hint.hint != ""
        assert advice_hint.is_escalated is False
        assert advice_escalate.is_escalated is True
        assert advice_escalate.severity == ErrorSeverity.DEGRADE

    def test_reflection_payload_contains_key_fields(self):
        advisor = ReflectiveAdvisor()
        messages = ["NameError: name 'pd' is not defined"] * 3
        pattern = ErrorPattern(
            tool_name="sandbox_exec", exc_type="NameError", count=3, messages=messages,
        )
        advice = advisor.advise(
            pattern, ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT,
        )

        payload = advice.reflection_payload
        assert "count" in payload
        assert "exc_type" in payload
        assert "hint" in payload
        assert "is_escalated" in payload

    def test_fatal_input_is_respected(self) -> None:
        """当 ErrorClassifier 已判定为 FATAL 时，Advisor 不应覆盖为低级别。"""
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=3)
        advice = advisor.advise(
            pattern, ErrorSeverity.FATAL, RecoveryAction.REPORT,
        )

        assert advice.severity == ErrorSeverity.FATAL
        assert advice.action == RecoveryAction.REPORT
        assert advice.is_escalated is False
        assert advice.hint == ""

    def test_custom_initial_stage_is_respected(self) -> None:
        """当 ErrorClassifier 从 DEGRADE 开始时，Advisor 不应降级为 RECOVERABLE。"""
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=2)
        advice = advisor.advise(
            pattern, ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK,
        )

        assert advice.severity == ErrorSeverity.DEGRADE
        assert advice.action == RecoveryAction.SIMPLIFY_TASK
        assert advice.is_escalated is False

    def test_escalation_from_custom_stage(self) -> None:
        """当 ErrorClassifier 从 DEGRADE 开始且重复次数足够时，Advisor 应升级到 FATAL。"""
        advisor = ReflectiveAdvisor()
        pattern = ErrorPattern(tool_name="sandbox_exec", exc_type="NameError", count=4)
        advice = advisor.advise(
            pattern, ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK,
        )

        assert advice.severity == ErrorSeverity.FATAL
        assert advice.action == RecoveryAction.REPORT
        assert advice.is_escalated is True
