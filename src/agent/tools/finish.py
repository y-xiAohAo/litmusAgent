"""finish 工具 —— 让 Agent 标记任务完成并交付最终结果。"""

from __future__ import annotations

from agent.core.types import ToolResult


def finish(result: str) -> ToolResult:
    """标记任务完成并返回最终结果。

    这是 Agent 主动结束循环、向用户交付产物的入口。Agent 主循环会识别
    `finish` 工具调用，并把它的 content 作为最终返回值。

    设计要点：
      - 不依赖沙箱后端，只是一个纯数据包装工具。
      - 返回 `success=True`，让主循环知道这是正常交付而非错误。

    参数：
        result: 任务的最终答案或交付物描述。

    返回：
        ToolResult，success 为 True，content 为最终结果。
    """
    return ToolResult(tool_call_id="", content=result, success=True)
