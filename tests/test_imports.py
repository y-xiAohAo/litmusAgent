"""Test that all key modules import cleanly without errors."""


def test_import_agent_top_level():
    """Top-level agent imports should work."""
    from agent import Agent
    assert Agent is not None


def test_import_core_types():
    """core.types module should exist and export types."""
    from agent.core.types import Message
    assert Message is not None


def test_import_engine():
    """Engine module should import without circular dependencies."""
    from agent.core.engine import Agent
    assert Agent is not None


def test_import_llm():
    """LLM module should export all client classes."""
    from agent.llm import BaseLLMClient
    assert BaseLLMClient is not None


def test_import_tools():
    """Tools module should re-export types."""
    from agent.tools import ToolSpec
    assert ToolSpec is not None
