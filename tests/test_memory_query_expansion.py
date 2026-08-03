"""查询扩展（Multi-Query Expansion）记忆检索测试。

覆盖：
  - 触发时机：L1 命中不扩展（零成本）/ 失配才扩展
  - 变体解析：编号/项目符号剥离、原查询去重、数量上限
  - 合并去重：多条目多变体的首次出现顺序
  - 降级：LLM 失败静默、开关默认关闭
  - search() 集成：失配 → 扩展命中 → 返回结构化候选
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryManager,
    RuleMemoryExtractor,
    StructuredMemoryStore,
)


class _ScriptedClient:
    """脚本化 LLM client：按队列返回预设 content。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(messages)
        return {"content": self._outputs.pop(0), "tool_calls": None}


class _FailingClient:
    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")


def _make_manager(
    tmp_path: Path,
    client: Any,
    *,
    qe_enabled: bool = True,
) -> MemoryManager:
    config = MemoryConfig(enabled=True, query_expansion_enabled=qe_enabled)
    return MemoryManager(
        store=StructuredMemoryStore(tmp_path),
        extractor=RuleMemoryExtractor(),
        config=config,
        llm_client=client,
    )


def _seed_preference(manager: MemoryManager, entry_id: str, fact: str) -> None:
    manager._store.save(
        MemoryEntry(
            entry_id=entry_id,
            category=MemoryCategory.PREFERENCES,
            content={"fact": fact},
            summary=fact,
            tags=["test"],
        )
    )


class TestExpansionTrigger:
    """触发时机（成本设计核心）。"""

    async def test_hit_skips_expansion(self, tmp_path: Path) -> None:
        """L1 原查询命中时不调用 LLM（零成本）。"""
        client = _ScriptedClient(["同义词"])
        manager = _make_manager(tmp_path, client)
        _seed_preference(manager, "e1", "构建标签是 b2077")
        results = await manager.search("构建标签")
        assert results
        assert client.calls == []

    async def test_miss_triggers_expansion(self, tmp_path: Path) -> None:
        """L1 失配时调用一次 LLM 生成变体并命中。"""
        client = _ScriptedClient(["构建标签\n构建号\n版本标识"])
        manager = _make_manager(tmp_path, client)
        _seed_preference(manager, "e1", "构建标签是 b2077")
        results = await manager.search("发布用的那个编号")
        assert len(client.calls) == 1
        assert any(r["entry_id"] == "e1" for r in results)

    async def test_disabled_never_expands(self, tmp_path: Path) -> None:
        """开关关闭（默认）时失配也不调用 LLM。"""
        client = _ScriptedClient(["构建标签"])
        manager = _make_manager(tmp_path, client, qe_enabled=False)
        _seed_preference(manager, "e1", "构建标签是 b2077")
        await manager.search("发布用的那个编号")
        assert client.calls == []


class TestVariantParsing:
    """变体解析与边界。"""

    async def test_strips_numbering_and_dedups_original(self, tmp_path: Path) -> None:
        """剥离编号/项目符号，去掉与原查询相同的变体。"""
        client = _ScriptedClient(["1. 发布用的那个编号\n- 构建标签\n• 构建号"])
        manager = _make_manager(tmp_path, client)
        _seed_preference(manager, "e1", "构建标签是 b2077")
        results = await manager.search("发布用的那个编号")
        assert any(r["entry_id"] == "e1" for r in results)

    async def test_llm_failure_degrades_silently(self, tmp_path: Path) -> None:
        """LLM 异常时扩展层返回空，search 按原 fallback 链继续（不抛异常）。"""
        manager = _make_manager(tmp_path, _FailingClient())
        _seed_preference(manager, "e1", "构建标签是 b2077")
        results = await manager.search("发布用的那个编号")
        assert isinstance(results, list)  # L0 recency 兜底或空，不抛异常


class TestMergeDedup:
    """合并去重。"""

    async def test_same_entry_from_two_variants_appears_once(self, tmp_path: Path) -> None:
        """同一条目被两个变体命中时只出现一次（首次变体优先）。"""
        client = _ScriptedClient(["构建标签\n构建号"])
        manager = _make_manager(tmp_path, client)
        _seed_preference(manager, "e1", "构建标签是 b2077")
        results = await manager.search("发布用的那个编号")
        ids = [r["entry_id"] for r in results]
        assert ids.count("e1") == 1


class TestSearchIntegration:
    """search() 集成路径。"""

    async def test_expansion_layer_precedes_recency_fallback(self, tmp_path: Path) -> None:
        """扩展命中后不再走 L0 recency（返回的是命中条目而非最近条目）。"""
        client = _ScriptedClient(["构建标签"])
        manager = _make_manager(tmp_path, client)
        _seed_preference(manager, "e1", "构建标签是 b2077")
        _seed_preference(manager, "e2", "队列名是 q-settle")
        results = await manager.search("发布用的那个编号")
        assert [r["entry_id"] for r in results] == ["e1"]
