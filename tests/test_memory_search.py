"""memory_search 工具与 MemoryManager.search() 测试（search-then-read 重构）。

覆盖：
  - search()：命中含完整字段 / 空库返回 [] / limit 截断 / L1 未命中走 L0 兜底 / 未启用返回 []
  - memory_search 工具：ToolResult 结构 / registry 注册可调用 / 无命中提示
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryManager,
    StructuredMemoryStore,
)


class _FakeExtractor:
    def extract(self, trace, state, run_metadata):  # noqa: ANN001, ANN202
        return []


def _make_manager(root: Path, **config_kwargs) -> MemoryManager:
    store = StructuredMemoryStore(root)
    config = MemoryConfig(enabled=True, **config_kwargs)
    return MemoryManager(store=store, extractor=_FakeExtractor(), config=config)


def _save(manager: MemoryManager, entry_id: str, summary: str, preview: str = "") -> None:
    manager._store.save(
        MemoryEntry(
            entry_id=entry_id,
            category=MemoryCategory.ARTIFACTS,
            content={
                "path": f"/workspace/{entry_id}.md",
                "content_preview": preview,
            },
            summary=summary,
            tags=["artifact"],
        )
    )


class TestManagerSearch:
    """MemoryManager.search() 方法。"""

    @pytest.mark.asyncio
    async def test_hit_returns_full_fields(self, tmp_path: Path) -> None:
        """命中结果应含 entry_id/category/summary/content_preview/uri。"""
        manager = _make_manager(tmp_path)
        _save(manager, "abc123", "生成产物：/workspace/notes.md", "代号 hermes-2026")

        results = await manager.search("notes.md")
        assert len(results) == 1
        item = results[0]
        assert item["entry_id"] == "abc123"
        assert item["category"] == "artifacts"
        assert "notes.md" in item["summary"]
        assert item["content_preview"] == "代号 hermes-2026"
        assert item["uri"].startswith("hermes://memory/artifacts/")

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty_list(self, tmp_path: Path) -> None:
        """空库返回空列表而非错误。"""
        manager = _make_manager(tmp_path)
        assert await manager.search("任意查询") == []

    @pytest.mark.asyncio
    async def test_limit_truncates_results(self, tmp_path: Path) -> None:
        """结果数受 limit 约束。"""
        manager = _make_manager(tmp_path)
        for i in range(5):
            _save(manager, f"e{i}", f"生成产物：/workspace/f{i}.md")

        results = await manager.search("生成产物", limit=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_l1_miss_uses_recency_fallback(self, tmp_path: Path) -> None:
        """字面未命中时按 L0 兜底返回最近记忆。"""
        manager = _make_manager(tmp_path)
        _save(manager, "e1", "生成产物：/workspace/notes.md")

        results = await manager.search("完全不相关的词")
        assert len(results) == 1
        assert results[0]["entry_id"] == "e1"

    @pytest.mark.asyncio
    async def test_disabled_config_returns_empty(self, tmp_path: Path) -> None:
        """记忆未启用时返回空列表。"""
        store = StructuredMemoryStore(tmp_path)
        manager = MemoryManager(
            store=store, extractor=_FakeExtractor(), config=MemoryConfig(enabled=False)
        )
        _save(manager, "e1", "生成产物：/workspace/notes.md")
        assert await manager.search("notes") == []


class TestMemorySearchTool:
    """memory_search 工具 handler 与注册。"""

    @pytest.mark.asyncio
    async def test_tool_returns_json_candidates(self, tmp_path: Path) -> None:
        """工具返回包含候选 JSON 的 ToolResult。"""
        from agent.tools.memory_search import memory_search

        manager = _make_manager(tmp_path)
        _save(manager, "abc123", "生成产物：/workspace/notes.md", "代号 x")

        result = await memory_search("notes", manager=manager)
        assert result.success is True
        assert "abc123" in result.content
        assert "hermes://memory/artifacts/" in result.content

    @pytest.mark.asyncio
    async def test_tool_no_hit_friendly_message(self, tmp_path: Path) -> None:
        """无命中时返回友好空结果（非错误）。"""
        from agent.tools.memory_search import memory_search

        manager = _make_manager(tmp_path)
        result = await memory_search("不存在的记忆xyz", manager=manager)
        assert result.success is True
        assert "[]" in result.content or "未找到" in result.content

    def test_registered_with_memory_tools(self) -> None:
        """register_memory_tools 应同时注册 memory_read 与 memory_search。"""
        from agent.core.engine import ToolRegistry
        from agent.tools import register_memory_tools

        manager = _make_manager(Path("dummy"))
        registry = ToolRegistry()
        register_memory_tools(registry, manager)
        assert registry.get("memory_read") is not None
        assert registry.get("memory_search") is not None
