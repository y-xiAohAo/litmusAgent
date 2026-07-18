"""Core type definitions for the agent framework."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message in the conversation."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    """A request from the LLM to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """The result of executing a tool."""

    tool_call_id: str
    content: str
    success: bool = True


@dataclass
class ToolSpec:
    """Schema definition for a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any] = field(repr=False)

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible function definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
