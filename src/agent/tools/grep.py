"""grep 工具 —— 让 Agent 在沙箱内按正则搜索文件内容。"""

from __future__ import annotations

import json

from agent.core.types import ToolResult
from agent.sandbox.base import ExecutionResult, SandboxBackend

# 结果条数硬顶，防止 LLM 传入极大 max_results 导致输出爆炸。
_MAX_RESULTS_CAP = 1000
# 输出字节截断阈值（UTF-8 编码后），超过则截断并注明。
_MAX_OUTPUT_BYTES = 8192

# 沙箱内执行的搜索脚本主体（无插值部分）。
# 约定：脚本 print 一行 JSON，结构为
#   {"matches": ["相对路径:行号:匹配行", ...], "truncated": bool}
# 或 {"error": "{ExcName}: ..."}。
_GREP_SCRIPT_BODY = r"""
# defense-in-depth：策略层（_evaluate_parametric_policy）只能看到工具的
# path 参数，看不到遍历过程中枚举出的每个文件，因此脚本内再按与
# SecurityConfig._apply_bind_read_deny 同口径的 5 类模式硬编码跳过
# 敏感文件（.env*、.ssh、*.pem/*.key、id_rsa、.git）。
# 注意：脚本运行在沙箱内，路径分隔符统一按 / 归一后匹配（兼容 Windows
# subprocess 后端）。
_SENSITIVE_RX = re.compile(
    r"(^|/)\.env|(^|/)\.ssh(/|$)|\.(pem|key)$|(^|/)id_rsa|(^|/)\.git(/|$)"
)


def is_sensitive(rel):
    return _SENSITIVE_RX.search(rel.replace(os.sep, "/").replace("\\", "/").lower())


flags = re.IGNORECASE if ignore_case else 0
try:
    rx = re.compile(pattern, flags)
except re.error as exc:
    print(json.dumps({"error": "re.error: " + str(exc)}))
    sys.exit(0)

if not os.path.exists(path):
    print(json.dumps({"error": "FileNotFoundError: 路径不存在：" + path}))
    sys.exit(0)

matches = []
truncated = False


def scan_file(fp):
    global truncated
    rel = os.path.relpath(fp, base)
    if is_sensitive(rel):
        return False
    try:
        f = open(fp, "r", errors="ignore")
    except OSError:
        # 跳过二进制 / 不可读文件
        return False
    with f:
        for lineno, line in enumerate(f, 1):
            if rx.search(line):
                matches.append(rel + ":" + str(lineno) + ":" + line.rstrip("\n"))
                if len(matches) >= max_results:
                    truncated = True
                    return True
    return False


if os.path.isfile(path):
    # path 为单文件时，相对路径以其所在目录为基准
    base = os.path.dirname(path) or os.sep
    if include is None or fnmatch.fnmatch(os.path.basename(path), include):
        scan_file(path)
else:
    base = path
    stop = False
    # os.walk 默认不 followlinks，避免符号链接环
    for root, dirs, files in os.walk(path):
        dirs.sort()
        files.sort()
        for name in files:
            if include is not None and not fnmatch.fnmatch(name, include):
                continue
            if scan_file(os.path.join(root, name)):
                stop = True
                break
        if stop:
            break

print(json.dumps({"matches": matches, "truncated": truncated}))
"""


def _truncate_output(text: str) -> str:
    """对输出做 8KB 字节截断，截断时追加 ... (truncated) 标记。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= _MAX_OUTPUT_BYTES:
        return text
    return encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore") + "\n... (truncated)"


async def grep(
    pattern: str,
    path: str,
    include: str | None = None,
    ignore_case: bool = False,
    max_results: int = 200,
    *,
    backend: SandboxBackend,
) -> ToolResult:
    """在沙箱内按正则搜索文件内容，返回 `相对路径:行号:匹配行` 列表。

    通过 `SandboxBackend.execute_code` 执行一段只读搜索脚本
    （os.walk + re + fnmatch），不扩展后端协议，Docker/Subprocess
    双后端自动兼容。path 既可为目录也可为单文件；二进制与不可读
    文件逐文件跳过；符号链接不跟随。

    参数：
        pattern: 正则表达式。
        path: 沙箱内的目录或文件路径。
        include: 可选的文件名 fnmatch 过滤模式（如 "*.py"）。
        ignore_case: 是否忽略大小写。
        max_results: 最大返回条数，默认 200，硬顶 1000。
        backend: 沙箱后端实例。

    返回：
        ToolResult。成功时 content 为匹配行列表（无命中时为提示文本）；
        失败时 content 为 `{ExcName}: ...` 格式的错误说明。
    """
    # 用 json.dumps 对参数做安全转义，避免引号或反斜杠破坏代码结构。
    code = (
        "import fnmatch, json, os, re, sys\n"
        f"pattern = {json.dumps(pattern)}\n"
        f"path = {json.dumps(path)}\n"
        f"include = {include!r}\n"
        f"ignore_case = {bool(ignore_case)!r}\n"
        f"max_results = {min(max(1, int(max_results)), _MAX_RESULTS_CAP)}\n"
    ) + _GREP_SCRIPT_BODY

    result: ExecutionResult = await backend.execute_code(code)
    if not result.success:
        return ToolResult(tool_call_id="", content=result.stderr, success=False)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return ToolResult(
            tool_call_id="",
            content=f"解析搜索结果失败：{exc}",
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
