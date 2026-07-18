"""file_write 工具 —— 让 Agent 在沙箱内创建或覆盖文件。"""

from __future__ import annotations

from agent.core.types import ToolResult
from agent.sandbox.base import SandboxBackend


async def file_write(
    path: str,
    content: str,
    backend: SandboxBackend,
) -> ToolResult:
    """在沙箱内创建或覆盖指定文件。

    这是 Agent 生成代码、文本产物并写入沙箱的入口。内容会按 UTF-8
    编码后交给 `SandboxBackend.put_file()` 写入目标路径。

    设计要点：
      - 复用后端已经实现的文件注入能力，工具层只做"编码 + 写入 + 结果包装"。
      - 写入失败时不抛异常，而是返回 `success=False`，让 LLM 能看到错误
        并决定下一步（例如换一个路径或检查权限）。

    参数：
        path: 沙箱内的目标文件路径，例如 "/workspace/main.py"。
        content: 要写入的完整 UTF-8 文本内容。
        backend: 用于写入文件的 Docker 沙箱后端实例。

    返回：
        ToolResult。成功时 content 为确认信息；失败时 content 为错误说明。
    """
    data = content.encode("utf-8")
    success = await backend.put_file(path, data)
    if not success:
        return ToolResult(
            tool_call_id="",
            content=f"OSError: 文件写入失败：{path}",
            success=False,
        )
    return ToolResult(
        tool_call_id="",
        content=f"已写入 {path}（{len(data)} 字节）",
        success=True,
    )
