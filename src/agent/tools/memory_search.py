"""memory_search 工具 —— 让 LLM 用自然语言搜索长期记忆（search-then-read）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agent.core.types import ToolResult

if TYPE_CHECKING:
    from agent.core.memory import MemoryManager


async def memory_search(
    query: str, manager: MemoryManager, limit: int = 5
) -> ToolResult:
    """按自然语言搜索长期记忆。

    这是记忆召回的“发现层”：LLM 不需要知道记忆 URI，只需用自然语言
    描述要找什么；返回的每条候选都带 uri，可传给 `memory_read` 精读。

    Args:
        query: 自然语言查询，如“项目代号”“之前创建的文件”。
        manager: 当前 Agent 的 MemoryManager 实例。
        limit: 最大返回条数，默认 5。

    Returns:
        ToolResult。content 为 JSON 数组：
        [{entry_id, category, summary, content_preview, uri}, ...]；
        无命中时为空数组（非错误）。
    """
    results = await manager.search(query, limit=limit)
    if not results:
        return ToolResult(
            tool_call_id="",
            content="[]（未找到匹配的记忆）",
            success=True,
        )
    return ToolResult(
        tool_call_id="",
        content=json.dumps(results, ensure_ascii=False, indent=2),
        success=True,
    )
