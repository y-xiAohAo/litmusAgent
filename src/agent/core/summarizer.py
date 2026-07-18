"""Summarizer —— 文本摘要器。

Phase 7 上下文压缩的核心组件之三。用于把过旧的消息历史压缩成摘要。

设计要点：
  - 提供 `Summarizer` 抽象接口，支持规则摘要和 LLM 摘要两种实现。
  - `StaticSummarizer` 不调用 LLM，作为默认兜底。
  - `LLMSummarizer` 使用独立注入的小模型 client，不占用主模型资源。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Summarizer(ABC):
    """文本摘要器抽象基类。"""

    @abstractmethod
    async def summarize(self, content: str, max_length: int = 500) -> str:
        """对给定内容生成摘要。

        Args:
            content: 要摘要的原始文本。
            max_length: 返回摘要的最大字符数（粗略上限）。

        Returns:
            摘要文本。
        """
        ...


class StaticSummarizer(Summarizer):
    """规则摘要器。

    策略：
      1. 保留前若干完整行，直到占用约一半预算。
      2. 若内容包含 Traceback / Error: / Exception: 等错误行，也加入摘要。
      3. 最终按 `max_length` 硬截断，避免摘要本身过长。

    不调用 LLM，成本低、确定性高，适合作为默认兜底。
    """

    _ERROR_MARKERS = ("Traceback", "Error:", "Exception:", "Failed:")

    async def summarize(self, content: str, max_length: int = 500) -> str:
        """返回 content 的前若干行 + 错误行摘要。"""
        if len(content) <= max_length:
            return content
        if not content:
            return content

        lines = content.splitlines()
        selected: list[str] = []
        used = 0
        half_budget = max_length // 2

        # 1. 至少保留第一行，再尽量多保留后续行直到占用一半预算
        for line in lines:
            if selected and used + len(line) + 1 > half_budget:
                break
            selected.append(line)
            used += len(line) + 1

        # 2. 收集错误/异常行（去重）
        seen = set(selected)
        for line in lines:
            if line in seen:
                continue
            if any(marker in line for marker in self._ERROR_MARKERS):
                selected.append(line)
                seen.add(line)

        summary = "\n".join(selected)
        if len(summary) > max_length:
            summary = summary[:max_length].rstrip() + "\n..."
        else:
            summary += "\n..."
        return summary


class LLMSummarizer(Summarizer):
    """基于小模型的摘要器。

    使用独立注入的 LLM client，通常配置为比主模型更小、更便宜的模型
    （如 gpt-4o-mini），专门负责这种低创意、可并行的摘要任务。

    当小模型调用失败时，会自动降级为 `StaticSummarizer`，避免主循环中断。
    """

    def __init__(
        self,
        llm_client: Any,
        model: str = "gpt-4o-mini",
        max_tokens: int = 512,
    ) -> None:
        """初始化 LLM 摘要器。

        Args:
            llm_client: 实现了 `chat(messages, tools=None, **kwargs)` 的 LLM client。
            model: 模型名称，用于日志和元数据；实际调用由 llm_client 决定。
            max_tokens: 调用 LLM 时限制输出长度。
        """
        self._llm_client = llm_client
        self._model = model
        self._max_tokens = max_tokens
        self._fallback = StaticSummarizer()

    async def summarize(self, content: str, max_length: int = 500) -> str:
        """调用小模型生成中文摘要，并按 max_length 截断。

        如果小模型调用失败，则降级为 StaticSummarizer 兜底。
        """
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "你是一位擅长提取关键信息的助手。"
                    "请用中文对下面的内容进行简洁摘要，保留核心事实和结论。"
                ),
            },
            {"role": "user", "content": content},
        ]
        try:
            response = await self._llm_client.chat(
                messages=messages,
                tools=None,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            logger.warning(
                "LLMSummarizer 调用失败，降级为 StaticSummarizer: %s", exc
            )
            return await self._fallback.summarize(content, max_length)

        summary = response.get("content", "") or ""
        if len(summary) > max_length:
            summary = summary[:max_length]
        return summary
