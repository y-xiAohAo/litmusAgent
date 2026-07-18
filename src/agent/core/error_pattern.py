"""错误模式账本 —— 反思式错误恢复的数据基础。

这个模块解决的核心问题：Agent 在单次运行中反复遇到同类错误时，
需要知道「这个错误已经出现过几次」，才能生成更有针对性的恢复建议。

设计要点：
  - 按 (工具名, 异常类型) 聚类错误，符合 Agent 的运行方式。
  - 提供错误消息签名提取能力，供后续 Task 做更精细的次级匹配。
  - 不调用 LLM，不修改错误分类规则，只负责「记录 + 识别」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 从错误内容中提取异常类型名，例如 "NameError: ..." → "NameError"
# 与 engine.py 中 _classify_tool_error 使用的正则保持一致
_EXCEPTION_TYPE_RE = re.compile(r"(\w+Error|\w+Exception)")


def _extract_exception_type(error_content: str) -> str | None:
    """从错误内容中提取异常类型名。

    Args:
        error_content: 工具返回的错误内容，通常形如 "NameError: ..."。

    Returns:
        匹配到的异常类型名；如果无法识别，返回 None。
    """
    match = _EXCEPTION_TYPE_RE.search(error_content)
    return match.group(1) if match else None


def _extract_message_signature(exc_type: str, error_content: str) -> str | None:
    """从错误消息中提取关键标识，用于更精细的次级模式匹配。

    不同异常类型的关注点是不同的：
      - NameError: 提取未定义的变量名，如 name 'pd' → 'pd'。
      - KeyError: 提取缺失的键名，如 'date' → 'date'。
      - AttributeError: 提取不存在的属性名，如 has no attribute 'colum' → 'colum'。
      - 其他类型: 暂不做次级匹配，返回 None。

    Args:
        exc_type: 异常类型名。
        error_content: 原始错误内容。

    Returns:
        提取到的关键标识；如果无法提取或不需要提取，返回 None。
    """
    if exc_type == "NameError":
        name_match = re.search(r"name\s+['\"]([^'\"]+)['\"]", error_content)
        return name_match.group(1) if name_match else None

    if exc_type == "KeyError":
        # 匹配 "KeyError: 'date'" 或 "KeyError('date')" 中的键名
        key_match = re.search(r"KeyError[:\(]\s*['\"]([^'\"]+)['\"]", error_content)
        return key_match.group(1) if key_match else None

    if exc_type == "AttributeError":
        attr_match = re.search(r"has no attribute\s+['\"]([^'\"]+)['\"]", error_content)
        return attr_match.group(1) if attr_match else None

    return None


@dataclass
class ErrorPattern:
    """一个错误模式的记录。

    Attributes:
        tool_name: 发生错误的工具名。
        exc_type: 异常类型名，如 "NameError"。
        count: 该模式出现的次数。
        messages: 最近若干条原始错误消息，用于后续分析相似度。
        last_seen_at: 最近一次出现的时间（UTC）。
    """

    tool_name: str
    exc_type: str
    count: int = 1
    messages: list[str] = field(default_factory=list)
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorPatternLedger:
    """错误模式账本 —— 记录单次运行中的错误模式。

    使用 (tool_name, exc_type) 作为主键聚类错误。
    后续 Task 会在此基础上加入阈值判断、反思提示生成和 action 升级。

    Attributes:
        max_history: 每个模式保留的最近错误消息条数上限。
    """

    def __init__(self, max_history: int = 5) -> None:
        """初始化账本。

        Args:
            max_history: 每个 ErrorPattern 最多保留多少条最近消息，默认 5 条。
        """
        self.max_history = max_history
        self._patterns: dict[tuple[str, str], ErrorPattern] = {}

    def record(self, tool_name: str, error_content: str) -> ErrorPattern:
        """记录一次工具错误，返回对应的错误模式。

        如果是该模式第一次出现，会创建新的 ErrorPattern；
        否则更新出现次数、消息历史和最后出现时间。

        Args:
            tool_name: 发生错误的工具名。
            error_content: 工具返回的错误内容。

        Returns:
            更新后的 ErrorPattern。
        """
        exc_type = _extract_exception_type(error_content) or "UnknownError"
        key = (tool_name, exc_type)

        if key not in self._patterns:
            pattern = ErrorPattern(
                tool_name=tool_name,
                exc_type=exc_type,
                count=1,
                messages=[error_content],
            )
            self._patterns[key] = pattern
            return pattern

        pattern = self._patterns[key]
        pattern.count += 1
        pattern.messages.append(error_content)
        # 只保留最近 max_history 条消息，避免无限制增长
        if len(pattern.messages) > self.max_history:
            pattern.messages = pattern.messages[-self.max_history :]
        pattern.last_seen_at = datetime.now(timezone.utc)
        return pattern

    def match(self, tool_name: str, error_content: str) -> ErrorPattern | None:
        """根据工具名和错误内容查询已有的错误模式。

        Args:
            tool_name: 工具名。
            error_content: 错误内容。

        Returns:
            匹配到的 ErrorPattern；如果不存在，返回 None。
        """
        exc_type = _extract_exception_type(error_content) or "UnknownError"
        return self._patterns.get((tool_name, exc_type))

    def get_pattern(self, tool_name: str, exc_type: str) -> ErrorPattern | None:
        """按主键直接查询错误模式。

        Args:
            tool_name: 工具名。
            exc_type: 异常类型名。

        Returns:
            匹配到的 ErrorPattern；如果不存在，返回 None。
        """
        return self._patterns.get((tool_name, exc_type))

    def clear(self) -> None:
        """清空账本中的所有模式。"""
        self._patterns.clear()
