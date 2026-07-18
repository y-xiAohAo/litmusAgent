"""ContextCompressor —— 历史消息压缩器。

Phase 7 上下文压缩的核心组件之四。当消息历史的 token 占用超过预算时，
通过保护头部/尾部、摘要中间区域等方式，把上下文控制在预算以内。

设计要点：
  - 只压缩发送给 LLM 的 `messages`，不影响 Trace 中的完整记录。
  - 保护头部（前 N 条）和尾部（最近 K 个 assistant 回合），避免 LLM "失忆"。
  - 中间区域使用 Summarizer 生成单条摘要消息。
  - 摘要后仍超预算，则逐步缩短摘要直至丢弃中间区域；最后手段对尾部做截断。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent.core.types import Message

if TYPE_CHECKING:
    from agent.core.context_cache import CacheEntry
    from agent.core.summarizer import Summarizer
    from agent.core.token_estimator import TokenEstimator


@dataclass
class CompressionResult:
    """上下文压缩结果。

    Attributes:
        messages: 压缩后的消息列表。
        original_token_count: 压缩前的 token 估算值。
        compressed_token_count: 压缩后的 token 估算值。
        original_message_count: 压缩前的消息条数。
        compressed_message_count: 压缩后的消息条数。
        strategy: 采用的压缩策略名称。
        summary: 中间区域生成的摘要文本（如果未生成则为空字符串）。
        removed_ranges: 被移除/替换的消息索引区间列表（左闭右开）。
        cache_entries: 压缩过程中新增的缓存条目（当前为空，由外迁器负责）。
    """

    messages: list[Message]
    original_token_count: int
    compressed_token_count: int
    original_message_count: int
    compressed_message_count: int
    strategy: str
    summary: str
    removed_ranges: list[tuple[int, int]]
    cache_entries: list[CacheEntry]


class ContextCompressor(ABC):
    """上下文压缩器抽象基类。"""

    @abstractmethod
    async def compress(
        self,
        messages: list[Message],
        budget: int,
        token_estimator: TokenEstimator,
    ) -> CompressionResult:
        """压缩消息历史，使其 token 占用不超过 budget。

        Args:
            messages: 原始消息历史。
            budget: token 预算上限。
            token_estimator: token 估算器。

        Returns:
            压缩结果。
        """
        ...


class HybridCompressor(ContextCompressor):
    """混合压缩器。

    策略：
      1. 若未超预算，直接返回原列表。
      2. 保护前 `protect_first_n` 条消息。
      3. 从尾部向前数，保护最近 `protect_last_n_turns` 个 assistant 回合
         （每个回合从一条 assistant 消息开始，包含其后所有 tool 消息）。
      4. 对中间区域生成一条摘要消息并替换原区域。
      5. 若仍超预算，逐步缩短摘要；最终丢弃中间区域。
      6. 最后手段：从尾部最旧消息开始截断内容，但始终保留最后一条消息完整。
    """

    def __init__(
        self,
        summarizer: Summarizer,
        protect_first_n: int = 2,
        protect_last_n_turns: int = 2,
        default_summary_max_chars: int = 500,
        min_summary_max_chars: int = 100,
    ) -> None:
        """初始化混合压缩器。

        Args:
            summarizer: 用于摘要中间区域的 Summarizer。
            protect_first_n: 保护前 N 条消息不被压缩/删除。
            protect_last_n_turns: 保护最近 K 个 assistant 回合。
            default_summary_max_chars: 默认摘要最大字符数。
            min_summary_max_chars: 摘要最小字符数，短于此值时停止缩短并尝试丢弃。
        """
        self._summarizer = summarizer
        self._protect_first_n = max(0, protect_first_n)
        self._protect_last_n_turns = max(0, protect_last_n_turns)
        self._default_summary_max_chars = default_summary_max_chars
        self._min_summary_max_chars = min_summary_max_chars

    async def compress(
        self,
        messages: list[Message],
        budget: int,
        token_estimator: TokenEstimator,
    ) -> CompressionResult:
        """执行混合压缩。"""
        original_message_count = len(messages)
        original_token_count = token_estimator.estimate(messages)
        if original_token_count <= budget:
            return CompressionResult(
                messages=messages,
                original_token_count=original_token_count,
                compressed_token_count=original_token_count,
                original_message_count=original_message_count,
                compressed_message_count=original_message_count,
                strategy="none",
                summary="",
                removed_ranges=[],
                cache_entries=[],
            )

        tail_start = self._find_tail_start(messages, self._protect_last_n_turns)
        # 头部边界需对齐到完整 tool_call/tool 结果对，避免拆分
        head_end = self._align_head_boundary(messages, self._protect_first_n)
        # 头部和尾部不能重叠；重叠时优先保证头部
        if tail_start < head_end:
            tail_start = head_end

        head = messages[:head_end]
        tail = messages[tail_start:]
        middle = messages[head_end:tail_start]
        removed_range = (head_end, tail_start)

        # 没有可压缩的中间区域，只能对尾部做 fallback 截断
        if not middle:
            compressed = self._fallback_truncate(head + tail, budget, token_estimator)
            return CompressionResult(
                messages=compressed,
                original_token_count=original_token_count,
                compressed_token_count=token_estimator.estimate(compressed),
                original_message_count=original_message_count,
                compressed_message_count=len(compressed),
                strategy="fallback_truncate",
                summary="",
                removed_ranges=[],
                cache_entries=[],
            )

        middle_text = self._middle_to_text(middle)
        summary_max_chars = self._default_summary_max_chars
        summary = await self._summarizer.summarize(middle_text, max_length=summary_max_chars)
        summary_msg = Message(role="user", content=f"[上下文摘要]\n{summary}")

        compressed = head + [summary_msg] + tail
        compressed_token_count = token_estimator.estimate(compressed)

        # 逐步缩短摘要直到满足预算或达到最小长度
        while compressed_token_count > budget and summary_max_chars > self._min_summary_max_chars:
            summary_max_chars = max(self._min_summary_max_chars, summary_max_chars // 2)
            summary = await self._summarizer.summarize(middle_text, max_length=summary_max_chars)
            summary_msg = Message(role="user", content=f"[上下文摘要]\n{summary}")
            compressed = head + [summary_msg] + tail
            compressed_token_count = token_estimator.estimate(compressed)

        strategy = "hybrid_summary"
        # 缩短后仍超预算，丢弃中间区域
        if compressed_token_count > budget:
            compressed = head + tail
            compressed_token_count = token_estimator.estimate(compressed)
            strategy = "hybrid_drop_middle"
            summary = ""

        # 最后手段：截断尾部旧消息内容，但保留最后一条完整
        if compressed_token_count > budget:
            compressed = self._fallback_truncate(compressed, budget, token_estimator)
            compressed_token_count = token_estimator.estimate(compressed)
            strategy = "hybrid_truncate_tail"

        return CompressionResult(
            messages=compressed,
            original_token_count=original_token_count,
            compressed_token_count=compressed_token_count,
            original_message_count=original_message_count,
            compressed_message_count=len(compressed),
            strategy=strategy,
            summary=summary,
            removed_ranges=[removed_range],
            cache_entries=[],
        )

    def _find_tail_start(self, messages: list[Message], n_turns: int) -> int:
        """找到尾部第 N 个 assistant 回合的起始索引。

        从后向前扫描，遇到 assistant 消息即视为一个回合的开始。
        若消息不足 N 个回合，则返回 0（保护全部）。
        """
        if n_turns <= 0:
            return len(messages)
        turn_count = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "assistant":
                turn_count += 1
                if turn_count == n_turns:
                    return i
        return 0

    def _align_head_boundary(self, messages: list[Message], head_end: int) -> int:
        """把头部边界对齐到完整 tool_call/tool 结果对。

        如果前 `head_end` 条消息的最后一条 assistant 消息带有 tool_calls，
        则必须把它后续的所有 tool 结果也纳入头部，避免拆分回合。
        """
        if head_end <= 0 or head_end > len(messages):
            return head_end

        # 找到 head 范围内最近一条带 tool_calls 的 assistant
        last_assistant_with_tools = -1
        for i in range(head_end - 1, -1, -1):
            msg = messages[i]
            if msg.role == "assistant" and msg.tool_calls:
                last_assistant_with_tools = i
                break
        if last_assistant_with_tools == -1:
            return head_end

        # 从原 head_end 开始，把连续的 tool 消息纳入头部
        new_end = head_end
        for i in range(head_end, len(messages)):
            if messages[i].role == "tool":
                new_end = i + 1
            else:
                break
        return new_end

    def _middle_to_text(self, messages: list[Message]) -> str:
        """把中间区域消息转换为可供摘要的文本。"""
        lines: list[str] = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                lines.append(f"Assistant: {msg.content or ''}")
                for tc in msg.tool_calls:
                    args = str(tc.arguments)
                    if len(args) > 200:
                        args = args[:200] + "..."
                    lines.append(f"  -> tool_call {tc.name}({args})")
            elif msg.role == "tool":
                content = msg.content or ""
                if len(content) > 200:
                    content = content[:200] + "..."
                lines.append(f"Tool {msg.name or ''}: {content}")
            else:
                content = msg.content or ""
                if len(content) > 200:
                    content = content[:200] + "..."
                lines.append(f"{msg.role}: {content}")
        return "\n".join(lines)

    def _fallback_truncate(
        self,
        messages: list[Message],
        budget: int,
        token_estimator: TokenEstimator,
    ) -> list[Message]:
        """最后手段：从尾部最旧消息开始截断内容，直到满足预算。

        始终保留最后一条消息完整，防止 LLM 完全失忆。
        """
        if not messages:
            return messages

        if token_estimator.estimate(messages) <= budget:
            return messages

        # 复制消息，避免修改原始对象
        mutable: list[Message] = [
            Message(
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
                name=m.name,
            )
            for m in messages
        ]

        for _ in range(20):  # 安全上限，避免死循环
            current = token_estimator.estimate(mutable)
            if current <= budget:
                break
            for idx in range(len(mutable) - 1):
                m = mutable[idx]
                if len(m.content) > 20:
                    new_len = max(20, len(m.content) // 2)
                    mutable[idx] = Message(
                        role=m.role,
                        content=m.content[:new_len] + "...",
                        tool_calls=m.tool_calls,
                        tool_call_id=m.tool_call_id,
                        name=m.name,
                    )

        return mutable
