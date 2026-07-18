"""context_read 工具 —— 读取 hermes://context/... 缓存内容。

这是 Phase 7 上下文压缩的内部配套工具。当工具结果（如 sandbox_exec 输出、
file_read 内容）被外迁到 `ContextCache` 后，LLM 可以通过该工具按需读回完整内容。

注意：此工具读取的是 Agent 内部缓存，不是沙箱文件；URI 必须经过
`ContextCache.read()` 校验，禁止路径遍历。
"""

from __future__ import annotations

from agent.core.context_cache import ContextCache
from agent.core.types import ToolResult


async def context_read(uri: str, cache: ContextCache) -> ToolResult:
    """通过 URI 读取本地缓存内容。

    Args:
        uri: hermes://context/<session_id>/<run_id>/<entry_id>.md 格式的 URI。
        cache: 当前 Agent 的 ContextCache 实例。

    Returns:
        成功时返回 ToolResult(content=缓存内容, success=True)；
        URI 无效或缓存不存在时返回 ToolResult(content=错误提示, success=False)。
    """
    content = cache.read(uri)
    if content is None:
        return ToolResult(
            tool_call_id="",
            content=f"缓存不存在或 URI 无效：{uri}",
            success=False,
        )
    return ToolResult(tool_call_id="", content=content, success=True)
