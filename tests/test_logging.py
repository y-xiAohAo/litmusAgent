"""Tests for structured logging configuration."""

from agent.logging import configure_logging, get_logger


def test_get_logger_returns_bound_logger():
    """get_logger should return a structlog BoundLogger."""
    logger = get_logger("test_module")
    assert logger is not None
    # structlog loggers have .bind() method
    assert hasattr(logger, "bind")


def test_logger_outputs_message(capsys):
    """Logger.info() should produce output to stderr."""
    configure_logging(level="INFO", json_format=False)
    logger = get_logger("test")
    logger.info("hello world", user="alice")

    captured = capsys.readouterr()
    assert "hello" in captured.err
    assert "alice" in captured.err


def test_logger_supports_levels(capsys):
    """DEBUG messages should be suppressed at INFO level."""
    configure_logging(level="INFO", json_format=False)
    logger = get_logger("test")
    logger.debug("should not appear")

    captured = capsys.readouterr()
    assert "should not appear" not in captured.err


def test_json_format_is_valid(capsys):
    """When json_format=True, output should be parseable JSON."""
    import json

    configure_logging(level="INFO", json_format=True)
    logger = get_logger("test")
    logger.info("json test", count=42)

    captured = capsys.readouterr()
    # Each line should be valid JSON
    for line in captured.err.strip().split("\n"):
        if line.strip():
            data = json.loads(line)
            assert data["event"] == "json test"
            assert data["count"] == 42
