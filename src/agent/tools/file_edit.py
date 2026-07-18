"""file_edit 工具 —— 让 Agent 精确编辑沙箱内已有文件的内容。"""

from __future__ import annotations

from agent.core.types import ToolResult
from agent.sandbox.base import SandboxBackend


async def file_edit(
    path: str,
    old_string: str,
    new_string: str,
    backend: SandboxBackend,
) -> ToolResult:
    """在沙箱内对文件进行精确的字符串替换编辑。

    这是 Agent 修改已有代码/文本的主要方式：读取文件后，找到 `old_string`
    的唯一出现位置并替换为 `new_string`，再写回沙箱。

    设计要点：
      - 要求 `old_string` 在文件中必须且只能出现一次，防止 LLM 使用模糊片段
        导致歧义替换或误改多处。
      - 文件不存在、`old_string` 找不到或出现多次时，都返回 `success=False`
        并附带明确原因，让 LLM 可以调整参数后重试。
      - 复用后端的 `get_file` / `put_file`，工具层只做"读取 + 替换 + 写回"。

    参数：
        path: 沙箱内的目标文件路径，例如 "/workspace/main.py"。
        old_string: 要被替换的原始字符串片段，必须在文件中唯一出现。
        new_string: 用于替换的新字符串片段；传空字符串可实现删除该片段。
        backend: 用于读写文件的 Docker 沙箱后端实例。

    返回：
        ToolResult。成功时 content 为确认信息；失败时 content 为错误说明。
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
        return ToolResult(
            tool_call_id="",
            content=f"文件解码失败：{exc}",
            success=False,
        )

    count = content.count(old_string)
    if count == 0:
        return ToolResult(
            tool_call_id="",
            content=(
                f"未能找到要替换的文本片段：{old_string!r} "
                f"在 {path} 中出现 0 次，请检查片段是否正确。"
            ),
            success=False,
        )
    if count > 1:
        return ToolResult(
            tool_call_id="",
            content=(
                f"要替换的文本片段不唯一：{old_string!r} "
                f"在 {path} 中出现 {count} 次，请提供更精确的片段。"
            ),
            success=False,
        )

    new_content = content.replace(old_string, new_string, 1)
    success = await backend.put_file(path, new_content.encode("utf-8"))
    if not success:
        return ToolResult(
            tool_call_id="",
            content=f"OSError: 文件编辑后写回失败：{path}",
            success=False,
        )

    return ToolResult(
        tool_call_id="",
        content=f"已编辑 {path}，替换 1 处内容",
        success=True,
    )
