"""memory_read 工具 —— 让 LLM 按需读取长期记忆详情。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.core.security import PolicyAction
from agent.core.types import ToolResult

if TYPE_CHECKING:
    from agent.core.memory import MemoryManager


async def memory_read(uri: str, manager: MemoryManager) -> ToolResult:
    """读取 hermes://memory/... 格式的长期记忆内容。

    Args:
        uri: 记忆 URI，例如 hermes://memory/environment/<entry_id>.jsonl。
        manager: 当前 Agent 的 MemoryManager 实例。

    Returns:
        命中时返回包含完整 entry JSON 的 ToolResult；
        未命中、URI 非法或被策略拒绝时返回 success=False。
    """
    decision = manager.check_read_policy(uri)
    if decision is not None and decision.action == PolicyAction.DENY:
        return ToolResult(
            tool_call_id="",
            content=f"策略拒绝：{decision.reason}",
            success=False,
        )

    content = manager.read(uri)
    if content is None:
        return ToolResult(
            tool_call_id="",
            content=f"记忆不存在或 URI 无效：{uri}",
            success=False,
        )
    return ToolResult(tool_call_id="", content=content, success=True)
