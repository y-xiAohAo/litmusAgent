"""file_read 工具 —— 让 Agent 读取沙箱内的文件内容。"""

from __future__ import annotations

from agent.core.types import ToolResult
from agent.sandbox.base import SandboxBackend


async def file_read(path: str, backend: SandboxBackend) -> ToolResult:
    """读取沙箱内指定路径的文件内容。

    这是 Agent 查看沙箱产物的入口：把 LLM 传来的路径交给
    `SandboxBackend.get_file()`，并把二进制内容解码为文本后返回。

    设计要点：
      - 复用后端已经实现的文件提取能力，工具层只做"读取 + 解码 + 结果包装"。
      - 文件不存在时不抛异常，而是返回 `success=False`，让 LLM 能看到错误
        并决定下一步（例如先列出目录确认文件名）。

    参数：
        path: 沙箱内的文件路径，例如 "/tmp/result.txt"。
        backend: 用于读取文件的 Docker 沙箱后端实例。

    返回：
        ToolResult。成功时 content 为文件文本内容；失败时 content 为错误说明。
    """
    data = await backend.get_file(path)
    if data is None:
        return ToolResult(
            tool_call_id="",
            content=f"FileNotFoundError: 文件不存在或读取失败：{path}",
            success=False,
        )
    try:
        content = data.decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover
        # errors="replace" 通常不会抛异常，这里保留兜底。
        return ToolResult(
            tool_call_id="",
            content=f"文件解码失败：{exc}",
            success=False,
        )
    return ToolResult(tool_call_id="", content=content, success=True)
