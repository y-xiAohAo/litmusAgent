"""file_list 工具 —— 让 Agent 列出沙箱内指定目录的文件。"""

from __future__ import annotations

import json

from agent.core.types import ToolResult
from agent.sandbox.base import ExecutionResult, SandboxBackend


async def file_list(path: str, backend: SandboxBackend) -> ToolResult:
    """列出沙箱内指定目录下的文件和子目录。

    沙箱后端首选可选能力 `list_dir()`（如 SubprocessSandboxBackend）；
    后端不提供时回退到 `execute_code()` 执行一小段 Python 代码完成
    `os.listdir(path)`。这样设计的好处：
      - 不强制扩展后端协议，保持 Phase 3 沙箱层稳定。
      - 返回结构化数据（JSON 数组或名称列表），工具层再转成 LLM 易读的换行列表。

    参数：
        path: 沙箱内的目录路径，例如 "/tmp"。
        backend: 用于执行列表操作的 Docker 沙箱后端实例。

    返回：
        ToolResult。成功时 content 为文件/目录列表（每行一个）；
        失败时 content 为错误说明。
    """
    # 可选能力优先：原生 list_dir 直接走路径映射，语义最准确。
    list_dir = getattr(backend, "list_dir", None)
    if callable(list_dir):
        entries_native = await list_dir(path)
        if entries_native is None:
            return ToolResult(
                tool_call_id="",
                content=f"FileNotFoundError: 目录不存在或不可读：{path}",
                success=False,
            )
        return ToolResult(tool_call_id="", content="\n".join(entries_native), success=True)

    # 回退路径：用 json.dumps 对路径做安全转义，避免单引号或反斜杠破坏代码结构。
    safe_path = json.dumps(path)
    code = (
        "import json, os\n"
        f"path = {safe_path}\n"
        "print(json.dumps(os.listdir(path)))"
    )

    result: ExecutionResult = await backend.execute_code(code)
    if not result.success:
        return ToolResult(tool_call_id="", content=result.stderr, success=False)

    try:
        entries: list[str] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return ToolResult(
            tool_call_id="",
            content=f"解析目录列表失败：{exc}",
            success=False,
        )

    return ToolResult(tool_call_id="", content="\n".join(entries), success=True)
