"""Tests for the error classification and recovery system."""


from agent.core.error_handler import ErrorClassifier, ErrorSeverity, RecoveryAction


class TestErrorClassification:
    """Tests for ErrorClassifier — maps exceptions to severity + action."""

    def test_syntax_error_is_recoverable_rewrite(self):
        severity, action = ErrorClassifier.classify(
            SyntaxError("invalid syntax")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.REWRITE_CODE

    def test_name_error_is_recoverable_check_context(self):
        severity, action = ErrorClassifier.classify(
            NameError("name 'df' is not defined")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.CHECK_CONTEXT

    def test_key_error_is_recoverable_check_context(self):
        severity, action = ErrorClassifier.classify(
            KeyError("'date'")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.CHECK_CONTEXT

    def test_attribute_error_is_recoverable_check_context(self):
        severity, action = ErrorClassifier.classify(
            AttributeError("'DataFrame' has no attribute 'colum'")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.CHECK_CONTEXT

    def test_type_error_is_recoverable_rewrite(self):
        severity, action = ErrorClassifier.classify(
            TypeError("unsupported operand type(s)")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.REWRITE_CODE

    def test_value_error_is_recoverable_rewrite(self):
        severity, action = ErrorClassifier.classify(
            ValueError("invalid literal for int()")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.REWRITE_CODE

    def test_memory_error_is_degrade(self):
        severity, action = ErrorClassifier.classify(
            MemoryError("out of memory")
        )
        assert severity == ErrorSeverity.DEGRADE
        assert action == RecoveryAction.SIMPLIFY_TASK

    def test_timeout_error_is_degrade(self):
        severity, action = ErrorClassifier.classify(
            TimeoutError("execution exceeded 30s")
        )
        assert severity == ErrorSeverity.DEGRADE
        assert action == RecoveryAction.SIMPLIFY_TASK

    def test_permission_error_is_fatal(self):
        severity, action = ErrorClassifier.classify(
            PermissionError("Permission denied")
        )
        assert severity == ErrorSeverity.FATAL
        assert action == RecoveryAction.REPORT

    def test_generic_exception_is_fatal(self):
        severity, action = ErrorClassifier.classify(
            Exception("something weird happened")
        )
        assert severity == ErrorSeverity.FATAL
        assert action == RecoveryAction.REPORT

    def test_recursion_error_is_degrade(self):
        severity, action = ErrorClassifier.classify(
            RecursionError("maximum recursion depth exceeded")
        )
        assert severity == ErrorSeverity.DEGRADE
        assert action == RecoveryAction.SIMPLIFY_TASK

    def test_import_error_is_recoverable(self):
        severity, action = ErrorClassifier.classify(
            ImportError("No module named 'pandas'")
        )
        assert severity == ErrorSeverity.RECOVERABLE
        assert action == RecoveryAction.CHECK_CONTEXT


class TestErrorSeverity:
    """Tests for ErrorSeverity enum values."""

    def test_severity_order(self):
        """RECOVERABLE < DEGRADE < FATAL in terms of urgency."""
        assert ErrorSeverity.RECOVERABLE.value < ErrorSeverity.DEGRADE.value
        assert ErrorSeverity.DEGRADE.value < ErrorSeverity.FATAL.value


class TestRecoveryAction:
    """Tests for RecoveryAction enum values."""

    def test_all_actions_have_unique_values(self):
        values = [a.value for a in RecoveryAction]
        assert len(values) == len(set(values))
