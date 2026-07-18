"""Tests for the reflective error pattern ledger."""

from __future__ import annotations

from agent.core.error_pattern import (
    ErrorPattern,
    ErrorPatternLedger,
    _extract_exception_type,
    _extract_message_signature,
)


class TestExtractExceptionType:
    """Tests for extracting exception type names from error contents."""

    def test_extract_name_error(self):
        content = "NameError: name 'pd' is not defined"
        assert _extract_exception_type(content) == "NameError"

    def test_extract_key_error(self):
        content = "KeyError: 'date'"
        assert _extract_exception_type(content) == "KeyError"

    def test_extract_timeout_error(self):
        content = "TimeoutError: execution exceeded 30s"
        assert _extract_exception_type(content) == "TimeoutError"

    def test_extract_custom_exception(self):
        content = "HTTPException: not found"
        assert _extract_exception_type(content) == "HTTPException"

    def test_extract_generic_exception(self):
        content = "Something went wrong"
        assert _extract_exception_type(content) is None


class TestExtractMessageSignature:
    """Tests for extracting message signatures for sub-pattern matching."""

    def test_name_error_variable(self):
        content = "NameError: name 'pd' is not defined"
        assert _extract_message_signature("NameError", content) == "pd"

    def test_key_error_key(self):
        content = "KeyError: 'date'"
        assert _extract_message_signature("KeyError", content) == "date"

    def test_attribute_error_attribute(self):
        content = "AttributeError: 'DataFrame' has no attribute 'colum'"
        assert _extract_message_signature("AttributeError", content) == "colum"

    def test_other_error_returns_none(self):
        content = "TimeoutError: execution exceeded 30s"
        assert _extract_message_signature("TimeoutError", content) is None


class TestErrorPatternLedger:
    """Tests for the error pattern ledger."""

    def test_record_first_error_creates_pattern(self):
        ledger = ErrorPatternLedger()
        pattern = ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")

        assert isinstance(pattern, ErrorPattern)
        assert pattern.tool_name == "sandbox_exec"
        assert pattern.exc_type == "NameError"
        assert pattern.count == 1
        assert pattern.messages == ["NameError: name 'pd' is not defined"]

    def test_record_same_pattern_increments_count(self):
        ledger = ErrorPatternLedger()
        ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")
        pattern = ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")

        assert pattern.count == 2

    def test_different_tools_are_separate_patterns(self):
        ledger = ErrorPatternLedger()
        pattern_a = ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")
        pattern_b = ledger.record("file_read", "NameError: name 'path' is not defined")

        assert pattern_a.count == 1
        assert pattern_b.count == 1
        assert pattern_a is not pattern_b

    def test_different_exception_types_are_separate_patterns(self):
        ledger = ErrorPatternLedger()
        pattern_a = ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")
        pattern_b = ledger.record("sandbox_exec", "KeyError: 'date'")

        assert pattern_a.exc_type == "NameError"
        assert pattern_b.exc_type == "KeyError"
        assert pattern_a is not pattern_b

    def test_match_returns_existing_pattern(self):
        ledger = ErrorPatternLedger()
        recorded = ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")
        matched = ledger.match("sandbox_exec", "NameError: name 'pd' is not defined")

        assert matched is recorded
        assert matched.count == 1

    def test_match_returns_none_for_unknown_pattern(self):
        ledger = ErrorPatternLedger()
        assert ledger.match("sandbox_exec", "NameError: name 'pd' is not defined") is None

    def test_get_pattern_by_key(self):
        ledger = ErrorPatternLedger()
        ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")
        pattern = ledger.get_pattern("sandbox_exec", "NameError")

        assert pattern is not None
        assert pattern.exc_type == "NameError"

    def test_clear_resets_ledger(self):
        ledger = ErrorPatternLedger()
        ledger.record("sandbox_exec", "NameError: name 'pd' is not defined")
        ledger.clear()

        assert ledger.match("sandbox_exec", "NameError: name 'pd' is not defined") is None

    def test_max_history_truncates_messages(self):
        ledger = ErrorPatternLedger(max_history=3)
        for i in range(5):
            ledger.record("sandbox_exec", f"NameError: name 'x{i}' is not defined")
        pattern = ledger.get_pattern("sandbox_exec", "NameError")

        assert pattern is not None
        assert len(pattern.messages) == 3
        # 最早的两条消息已经被裁剪掉
        assert "NameError: name 'x0' is not defined" not in pattern.messages
        assert "NameError: name 'x1' is not defined" not in pattern.messages
        # 最近的三条消息保留
        assert "NameError: name 'x4' is not defined" in pattern.messages

    def test_unknown_error_uses_fallback_key(self):
        ledger = ErrorPatternLedger()
        pattern = ledger.record("sandbox_exec", "Something went wrong")

        assert pattern.exc_type == "UnknownError"
        assert pattern.count == 1
