"""glob 工具 —— 让 Agent 在沙箱内按文件名模式匹配文件。"""

from __future__ import annotations

import json

from agent.core.types import ToolResult
from agent.sandbox.base import ExecutionResult, SandboxBackend

# 结果条数硬顶，防止 LLM 传入极大 max_results 导致输出爆炸。
_MAX_RESULTS_CAP = 1000
# 输出字节截断阈值（UTF-8 编码后），超过则截断并注明。
_MAX_OUTPUT_BYTES = 8192

# 沙箱内执行的匹配脚本主体（无插值部分）。
# 脚本在沙箱内独立进程运行，可安全使用 stdlib glob（与本工具模块同名无冲突）。
# 约定：脚本 print 一行 JSON，结构为
#   {"matches": ["相对路径", ...], "truncated": bool}
# 或 {"error": "{ExcName}: ..."}。
_GLOB_SCRIPT_BODY = r"""
if not os.path.isdir(path):
    print(json.dumps({"error": "NotADirectoryError: 目录不存在：" + path}))
    sys.exit(0)

# defense-in-depth：策略层（_evaluate_parametric_policy）只能看到工具的
# path 参数，看不到枚举出的每个命中项，因此脚本内再按与
# SecurityConfig._apply_bind_read_deny 同口径的 5 类模式硬编码过滤
# 敏感文件（.env*、.ssh、*.pem/*.key、id_rsa、.git）。
_SENSITIVE_RX = re.compile(
    r"(^|/)\.env|(^|/)\.ssh(/|$)|\.(pem|key)$|(^|/)id_rsa|(^|/)\.git(/|$)"
)


def is_sensitive(rel):
    return _SENSITIVE_RX.search(rel.replace(os.sep, "/").replace("\\", "/").lower())


# root_dir=path 使结果天然为相对路径；recursive=True 支持 ** 递归通配
hits = [
    h
    for h in sorted(glob.glob(pattern, root_dir=path, recursive=True))
    if not is_sensitive(h)
]
truncated = len(hits) > max_results
hits = hits[:max_results]
print(json.dumps({"matches": hits, "truncated": truncated}))
"""


def _truncate_output(text: str) -> str:
    """对输出做 8KB 字节截断，截断时追加 ... (truncated) 标记。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= _MAX_OUTPUT_BYTES:
        return text
    return encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore") + "\n... (truncated)"


async def glob(
    pattern: str,
    path: str = "/workspace",
    max_results: int = 200,
    *,
    backend: SandboxBackend,
) -> ToolResult:
    """在沙箱内按文件名模式匹配文件，返回每行一个相对路径。

    通过 `SandboxBackend.execute_code` 执行一段只读匹配脚本
    （标准库 glob.glob，recursive=True 支持 `**` 递归），不扩展
    后端协议，Docker/Subprocess 双后端自动兼容。

    参数：
        pattern: glob 模式（如 "**/*.py"），相对 path 解析。
        path: 沙箱内的搜索根目录，默认 "/workspace"。
        max_results: 最大返回条数，默认 200，硬顶 1000。
        backend: 沙箱后端实例。

    返回：
        ToolResult。成功时 content 为相对路径列表（无命中时为提示文本）；
        失败时 content 为 `{ExcName}: ...` 格式的错误说明。
    """
    # 用 json.dumps 对参数做安全转义，避免引号或反斜杠破坏代码结构。
    code = (
        "import glob, json, os, re, sys\n"
        f"pattern = {json.dumps(pattern)}\n"
        f"path = {json.dumps(path)}\n"
        f"max_results = {min(max(1, int(max_results)), _MAX_RESULTS_CAP)}\n"
    ) + _GLOB_SCRIPT_BODY

    result: ExecutionResult = await backend.execute_code(code)
    if not result.success:
        return ToolResult(tool_call_id="", content=result.stderr, success=False)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return ToolResult(
            tool_call_id="",
            content=f"解析匹配结果失败：{exc}",
            success=False,
        )

    error = payload.get("error")
    if error is not None:
        return ToolResult(tool_call_id="", content=error, success=False)

    matches: list[str] = payload["matches"]
    if not matches:
        return ToolResult(tool_call_id="", content="（无匹配结果）", success=True)

    text = "\n".join(matches)
    if payload.get("truncated"):
        text += "\n... (truncated)"
    return ToolResult(tool_call_id="", content=_truncate_output(text), success=True)
