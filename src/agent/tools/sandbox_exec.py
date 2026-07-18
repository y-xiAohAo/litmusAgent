"""sandbox_exec 工具 —— 让 Agent 在沙箱中执行 Python 代码。"""

from __future__ import annotations

import re

from agent.core.state import ExecutionContext
from agent.core.types import ToolResult
from agent.sandbox.base import ExecutionResult, SandboxBackend

# 行级匹配 `pip install ...`（兼容 `!pip install` 笔记本风格）
_PIP_INSTALL_RE = re.compile(r"^\s*!?\s*(?:pip|pip3)\s+install\s+(.+?)\s*$")

# subprocess 列表形态匹配：["pip", "install", ...] 或
# [sys.executable, "-m", "pip", "install", ...]（单双引号均可）
_PIP_LIST_RE = re.compile(
    r"[\"']pip3?[\"']\s*,\s*[\"']install[\"']\s*,?\s*([^\)]*)",
    re.IGNORECASE,
)

# 字符串形态匹配：os.system("pip install pkg") / subprocess.run("pip install pkg")
_PIP_STRING_RE = re.compile(r"[\"']pip3?\s+install\s+([^\"']+)[\"']")

# 列表形态中的引号 token
_QUOTED_TOKEN_RE = re.compile(r"[\"']([^\"']+)[\"']")


def _normalize_package(token: str) -> str | None:
    """归一化包名：截断版本钉与 extras；选项与依赖文件返回 None。

    例如：`requests==2.31.0` → `requests`，`uvicorn[standard]` → `uvicorn`，
    `--quiet` / `-r` / `requirements.txt` → None。
    """
    token = token.strip()
    if not token or token.startswith("-") or token.endswith(".txt"):
        return None
    for sep in ("==", ">=", "<=", "!=", "~=", ">", "<", "["):
        if sep in token:
            token = token.split(sep, 1)[0]
    return token.strip() or None


def _extract_pip_packages(code: str) -> list[str]:
    """从代码中提取 `pip install` 的包名列表（示例级启发式，TD-004 + FAST 增强）。

    支持三种形态：
      1. 行级：`pip install pkg`（含 `!pip` 笔记本风格，跳过注释行）；
      2. 列表形态：`subprocess.run(["pip", "install", "pkg"])`，
         含 `[sys.executable, "-m", "pip", "install", ...]` 变体；
      3. 字符串形态：`os.system("pip install pkg")`。

    所有形态统一归一化（去版本钉/extras，过滤 `-` 选项与 `.txt` 依赖文件）。
    注意：这是示例级实现，记录的是“代码意图”而非运行时事实，
    仍由“成功执行才记录”的门禁兜底。
    """
    packages: list[str] = []

    def _collect(tokens: list[str]) -> None:
        for token in tokens:
            normalized = _normalize_package(token)
            if normalized is not None and normalized not in packages:
                packages.append(normalized)

    for line in code.splitlines():
        if line.strip().startswith("#"):
            continue
        # 形态 1：行级 pip install
        match = _PIP_INSTALL_RE.match(line)
        if match:
            _collect(match.group(1).split())
        # 形态 2：subprocess 列表形态
        for list_match in _PIP_LIST_RE.finditer(line):
            _collect(_QUOTED_TOKEN_RE.findall(list_match.group(1)))
        # 形态 3：字符串形态
        for str_match in _PIP_STRING_RE.finditer(line):
            _collect(str_match.group(1).split())

    return packages


async def sandbox_exec(
    code: str,
    backend: SandboxBackend,
    execution_context: ExecutionContext | None = None,
) -> ToolResult:
    """在沙箱中执行 Python 代码。

    这是 Agent 与沙箱层之间的桥接函数：它把 LLM 传来的代码片段交给
    `SandboxBackend.execute_code()` 执行，并把执行结果转换为
    `ToolResult`，供 Agent 主循环继续决策。

    设计要点：
      - 不直接操作沙箱实现，复用后端的执行能力。
      - 成功与失败都通过 ToolResult.success 显式表达，而不是抛异常，
        这样 LLM 能看到 stderr 并自我修正。
      - TD-004：传入 execution_context 时，成功执行后把代码中的
        `pip install` 包名记录到 `packages_installed` 键，供后续
        tool call 判断"已安装"状态。

    参数：
        code: 要执行的 Python 源代码。
        backend: 用于执行代码的沙箱后端实例。
        execution_context: 可选的执行上下文（由 ToolRegistry 自动注入）。

    返回：
        ToolResult。成功时 content 为 stdout；失败时 content 为 stderr，
        success 为 False。
    """
    result: ExecutionResult = await backend.execute_code(code)
    if result.success:
        if execution_context is not None:
            packages = _extract_pip_packages(code)
            if packages:
                installed: list[str] = execution_context.get("packages_installed", [])
                for pkg in packages:
                    if pkg not in installed:
                        installed.append(pkg)
                execution_context.set("packages_installed", installed)
        return ToolResult(tool_call_id="", content=result.stdout, success=True)
    return ToolResult(tool_call_id="", content=result.stderr, success=False)
