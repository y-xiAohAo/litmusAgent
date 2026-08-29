"""Abstract base class and test doubles for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# TD-020：流式渲染回调签名。
# TokenCallback：content / reasoning_content 分片回调。
TokenCallback = Callable[[str], None]
# 工具进度回调：on_tool_start(工具名, 参数摘要) / on_tool_end(工具名, 是否成功)。
ToolStartCallback = Callable[[str, str], None]
ToolEndCallback = Callable[[str, bool], None]


@dataclass
class StreamEvents:
    """流式渲染回调集合（TD-020）。

    全部为可选的同步回调，由渲染层（CLI/Web）构造、引擎与 LLM 客户端触发。
    回调实现方需自行保证轻量与非阻塞；抛出的异常不应影响引擎主流程
    （引擎侧已用 try/except 兜底，见 Agent._emit_stream_event）。
    """

    on_token: TokenCallback | None = None        # content 分片
    on_reasoning: TokenCallback | None = None    # reasoning_content 分片（思考链）
    on_tool_start: ToolStartCallback | None = None   # 工具执行前（name, args 摘要）
    on_tool_end: ToolEndCallback | None = None       # 工具执行后（name, ok）


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

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        events: StreamEvents | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """流式聊天完成请求（TD-020）。

        默认实现：回退到 chat()，收完后把 content / reasoning_content
        一次性回调给 events，返回与原 chat() 相同的 dict 结构。
        子类（如 OpenAIClient）可覆写为真正的 SSE 流式实现；
        只实现 chat() 的既有 mock / 测试替身零改动即可获得本方法。
        """
        result = await self.chat(messages, tools=tools, **kwargs)
        if events is not None:
            content = result.get("content") or ""
            if content and events.on_token is not None:
                events.on_token(content)
            reasoning = result.get("reasoning_content") or ""
            if reasoning and events.on_reasoning is not None:
                events.on_reasoning(reasoning)
        return result


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

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        events: StreamEvents | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """逐词回调 on_token 模拟流式输出（TD-020），返回结构与 chat() 一致。"""
        result = await self.chat(messages, tools=tools, **kwargs)
        if events is not None and events.on_token is not None:
            content = result.get("content") or ""
            for word in content.split(" "):
                events.on_token(word + " ")
        return result
