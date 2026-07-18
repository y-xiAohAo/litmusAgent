"""Token 估算器 —— 估算消息列表的 token 占用量。

这是 Phase 7 上下文压缩的基础组件。因为不是所有环境都会安装 tiktoken，
所以默认使用基于字符数的轻量估算；需要精确估算时可选择 TiktokenEstimator。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.core.types import Message


class TokenEstimator(ABC):
    """Token 估算器抽象基类。

    子类需要实现 `estimate(messages)`，返回给定消息列表预估占用的 token 数。
    """

    @abstractmethod
    def estimate(self, messages: list[Message]) -> int:
        """估算消息列表的 token 占用量。

        Args:
            messages: 要估算的 Message 列表。

        Returns:
            预估 token 数（非负整数）。
        """
        ...


class CharTokenEstimator(TokenEstimator):
    """基于字符数的轻量 token 估算器。

    假设平均每 `chars_per_token` 个字符对应 1 个 token。这个假设对英文
    和代码大致成立（通常 1 token ≈ 4 个字符），对中文会低估，但足够
    用于触发压缩的阈值判断。
    """

    def __init__(self, chars_per_token: int = 4) -> None:
        """初始化估算器。

        Args:
            chars_per_token: 多少个字符估算为 1 个 token，必须大于 0。

        Raises:
            ValueError: 如果 chars_per_token <= 0。
        """
        if chars_per_token <= 0:
            raise ValueError("chars_per_token 必须大于 0")
        self.chars_per_token = chars_per_token

    def estimate(self, messages: list[Message]) -> int:
        """按字符数估算 token。

        估算内容包括：
          - 每条消息的 content
          - assistant 消息中 tool_calls 的 name 和 arguments
        """
        total_chars = 0
        for msg in messages:
            total_chars += len(msg.content or "")
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total_chars += len(tc.name)
                    total_chars += len(str(tc.arguments))
        return total_chars // self.chars_per_token


class TiktokenEstimator(TokenEstimator):
    """使用 tiktoken 进行精确 token 估算。

    需要额外安装 tiktoken；未安装时实例化会抛出 ImportError。
    """

    def __init__(self, model: str = "gpt-4o") -> None:
        """初始化 tiktoken 估算器。

        Args:
            model: 模型名称，tiktoken 会根据模型选择对应编码。

        Raises:
            ImportError: 如果当前环境未安装 tiktoken。
        """
        try:
            import tiktoken
        except ImportError as exc:
            raise ImportError(
                "使用 TiktokenEstimator 需要安装 tiktoken：pip install tiktoken"
            ) from exc
        self.model = model
        self._encoding = tiktoken.encoding_for_model(model)

    def estimate(self, messages: list[Message]) -> int:
        """使用 tiktoken 精确估算 token 数。"""
        total = 0
        for msg in messages:
            total += len(self._encoding.encode(msg.content or ""))
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(self._encoding.encode(tc.name))
                    total += len(self._encoding.encode(str(tc.arguments)))
        return total
