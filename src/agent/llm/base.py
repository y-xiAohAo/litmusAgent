"""Abstract base class and test doubles for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Returns a dict with at minimum:
            - "content": str (assistant response text)
            - "tool_calls": list | None
        """
        ...


class EchoClient(BaseLLMClient):
    """Dummy client for testing — echoes last user message."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        last = messages[-1]["content"] if messages else ""
        return {"content": f"You said: {last}", "tool_calls": None}
