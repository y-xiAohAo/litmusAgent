"""ToolResultExternalizer —— 把过长的工具结果外迁到 ContextCache。

这是 Phase 7 上下文压缩的核心组件之二。它决定一个工具结果是否需要外迁，
并在需要时把完整内容写入缓存、在消息中只保留引用和预览。

设计要点：
  - 错误分类在调用本组件之前完成，因此本组件只处理原始 content。
  - 失败 traceback 默认完整保留在消息中（D1），只有超过 exec_error_preview
    时才截断并给出缓存链接。
  - 工具结果外迁不调用 LLM，只使用规则预览，避免不必要的成本和延迟。
"""

from __future__ import annotations

from agent.core.context_cache import CacheEntry, ContextCache


class ToolResultExternalizer:
    """工具结果外迁器。"""

    def __init__(
        self,
        cache: ContextCache,
        threshold: int = 800,
        file_read_preview: int = 500,
        exec_success_preview: int = 200,
        exec_error_preview: int = 1000,
    ) -> None:
        """初始化外迁器。

        Args:
            cache: 用于存储长内容的 ContextCache 实例。
            threshold: 内容超过多少字符时考虑外迁。
            file_read_preview: file_read 成功时保留的预览字符数。
            exec_success_preview: sandbox_exec 成功时保留的预览字符数。
            exec_error_preview: 失败时最多保留多少字符；超过则截断并给链接。
        """
        self._cache = cache
        self._threshold = threshold
        self._file_read_preview = file_read_preview
        self._exec_success_preview = exec_success_preview
        self._exec_error_preview = exec_error_preview

    def externalize_if_needed(
        self,
        run_id: str,
        tool_name: str,
        content: str,
        success: bool,
    ) -> tuple[str, CacheEntry | None]:
        """判断是否需要外迁，并返回要在消息中使用的 content。

        Args:
            run_id: 当前 run 标识。
            tool_name: 工具名。
            content: 原始工具结果内容。
            success: 工具是否执行成功。

        Returns:
            - 用于写入 messages 的 content（原内容或引用+摘要）。
            - 如果发生了外迁，返回 CacheEntry；否则返回 None。
        """
        if len(content) <= self._threshold:
            return content, None

        # context_read / memory_read 读回来的内容不要再外迁，避免循环
        if tool_name in {"context_read", "memory_read"}:
            return content, None

        # 失败 traceback 默认完整保留，只有极长时才截断
        if not success:
            if len(content) <= self._exec_error_preview:
                return content, None
            preview_len = self._exec_error_preview
        elif tool_name == "file_read":
            preview_len = self._file_read_preview
        else:
            preview_len = self._exec_success_preview

        preview = self._make_preview(content, preview_len)
        entry = self._cache.store(
            run_id=run_id,
            tool_name=tool_name,
            content=content,
            summary=preview,
        )

        status = "成功" if success else "失败"
        replacement = (
            f"[工具结果已外迁]\n"
            f"工具: {tool_name}\n"
            f"状态: {status}\n"
            f"缓存: {entry.uri}\n"
            f"摘要:\n"
            f"------\n"
            f"{preview}\n"
            f"...\n\n"
            f"如需完整内容，请调用 context_read(\"{entry.uri}\")"
        )
        return replacement, entry

    def _make_preview(self, content: str, max_length: int) -> str:
        """生成内容预览，保留前 max_length 字符。"""
        if len(content) <= max_length:
            return content
        return content[:max_length]
