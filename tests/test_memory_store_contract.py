"""记忆存储后端行为一致性契约套件。

同一组契约测试对 JSONL（StructuredMemoryStore）与 SQL（SqlMemoryStore）
两个后端参数化复跑——任何后端实现都必须通过这些用例，保证 store 可插拔
替换时上层行为不变（TD-SQL）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryQuery,
    MemoryStore,
    StructuredMemoryStore,
)
from agent.core.memory_sql_store import SqlMemoryStore


def _make_store(kind: str, tmp_path: Path) -> MemoryStore:
    if kind == "jsonl":
        return StructuredMemoryStore(tmp_path / "jsonl")
    if kind == "sql":
        sql_dir = tmp_path / "sql"
        sql_dir.mkdir(parents=True, exist_ok=True)
        return SqlMemoryStore(f"sqlite:///{sql_dir / 'memory.db'}")
    raise ValueError(kind)


@pytest.fixture(params=["jsonl", "sql"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> MemoryStore:
    """参数化后端：JSONL / SQL(SQLite)。"""
    return _make_store(request.param, tmp_path)


def _entry(entry_id: str, fact: str, **overrides) -> MemoryEntry:
    defaults: dict = {
        "category": MemoryCategory.PREFERENCES,
        "content": {"fact": fact},
        "summary": fact,
        "tags": ["test"],
    }
    defaults.update(overrides)
    return MemoryEntry(entry_id=entry_id, **defaults)


class TestSaveRoundtrip:
    """保存与读取。"""

    def test_save_and_list_roundtrip_all_fields(self, store: MemoryStore) -> None:
        """保存后全字段（含 tags/content/uri/confidence）读回一致。"""
        entry = _entry(
            "e1",
            "项目代号是蓝鲸计划",
            tags=["代号", "项目"],
            confidence=0.9,
            source_run_id="run-1",
        )
        store.save(entry)
        entries = store.list_entries()
        assert len(entries) == 1
        got = entries[0]
        assert got.entry_id == "e1"
        assert got.content["fact"] == "项目代号是蓝鲸计划"
        assert got.summary == "项目代号是蓝鲸计划"
        assert set(got.tags) == {"代号", "项目"}
        assert got.uri.startswith("hermes://memory/preferences/")
        assert abs(got.confidence - 0.9) < 1e-9
        assert got.source_run_id == "run-1"

    def test_save_same_id_overwrites_and_refreshes(self, store: MemoryStore) -> None:
        """同 entry_id 覆盖保存：只有一条记录，内容更新。"""
        store.save(_entry("e1", "旧值"))
        store.save(_entry("e1", "新值"))
        entries = store.list_entries()
        assert len(entries) == 1
        assert entries[0].content["fact"] == "新值"

    def test_get_existing_and_missing(self, store: MemoryStore) -> None:
        """get：存在的返回条目，不存在返回 None。"""
        store.save(_entry("e1", "存在"))
        assert store.get("e1") is not None
        assert store.get("nope") is None


class TestQuery:
    """条件检索。"""

    def test_category_filter(self, store: MemoryStore) -> None:
        """按类别过滤。"""
        store.save(_entry("e1", "偏好事实", category=MemoryCategory.PREFERENCES))
        store.save(_entry("e2", "任务摘要", category=MemoryCategory.TASK_SUMMARIES))
        results = store.query(MemoryQuery(categories=[MemoryCategory.TASK_SUMMARIES]))
        assert [e.entry_id for e in results] == ["e2"]

    def test_tags_filter(self, store: MemoryStore) -> None:
        """tags 至少命中一个。"""
        store.save(_entry("e1", "事实一", tags=["alpha"]))
        store.save(_entry("e2", "事实二", tags=["beta"]))
        results = store.query(MemoryQuery(tags=["alpha"]))
        assert [e.entry_id for e in results] == ["e1"]

    def test_text_overlap_ranking(self, store: MemoryStore) -> None:
        """text 重叠打分：命中的排前，未命中被过滤。"""
        store.save(_entry("e1", "缓存阈值是 42.7"))
        store.save(_entry("e2", "负责人是林晚"))
        results = store.query(MemoryQuery(text="缓存阈值", top_k=5))
        assert [e.entry_id for e in results] == ["e1"]

    def test_top_k_limit(self, store: MemoryStore) -> None:
        """top_k 截断。"""
        for i in range(5):
            store.save(_entry(f"e{i}", f"代号 alpha {i}"))
        results = store.query(MemoryQuery(text="alpha", top_k=2))
        assert len(results) == 2

    def test_time_range_filter(self, store: MemoryStore) -> None:
        """time_range 对 updated_at 过滤。"""
        store.save(_entry("e1", "范围测试"))
        now = datetime.now(timezone.utc)
        results = store.query(MemoryQuery(time_range=(now - timedelta(hours=1), now)))
        assert [e.entry_id for e in results] == ["e1"]
        results = store.query(
            MemoryQuery(time_range=(now - timedelta(days=10), now - timedelta(days=5)))
        )
        assert results == []


class TestDeleteAndCleanup:
    """删除与清理。"""

    def test_delete_existing_and_missing(self, store: MemoryStore) -> None:
        """delete：存在返回 True 并移除，不存在返回 False。"""
        store.save(_entry("e1", "待删除"))
        assert store.delete("e1") is True
        assert store.list_entries() == []
        assert store.delete("e1") is False

    def test_cleanup_removes_old_keeps_new(self, store: MemoryStore) -> None:
        """cleanup：超龄删除，新条目保留；None 不清理。"""
        store.save(_entry("e1", "新条目"))
        assert store.cleanup(None) == 0
        # 把 e1 的时间戳改老（JSONL 改文件 / SQL 改列）
        old_ts = datetime.now(timezone.utc) - timedelta(days=60)
        _age_entry(store, "e1", old_ts)
        assert store.cleanup(timedelta(days=30)) == 1
        assert store.list_entries() == []

    def test_list_recent_newest_first_with_limit(self, store: MemoryStore) -> None:
        """list_recent：最新优先，limit 截断。"""
        base = datetime.now(timezone.utc) - timedelta(hours=3)
        for i in range(3):
            entry = _entry(f"e{i}", f"条目 {i}")
            store.save(entry)
            _age_entry(store, f"e{i}", base + timedelta(hours=i))
        recent = store.list_recent(2)
        assert [e.entry_id for e in recent] == ["e2", "e1"]


def _age_entry(store: MemoryStore, entry_id: str, ts: datetime) -> None:
    """把条目时间戳改为指定值（JSONL 改文件；SQL 改列）。"""
    import json as _json

    if isinstance(store, StructuredMemoryStore):
        file_path = store._root / "preferences" / f"{entry_id}.jsonl"
        data = _json.loads(file_path.read_text(encoding="utf-8"))
        data["updated_at"] = ts.isoformat()
        file_path.write_text(_json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        import sqlalchemy as sa

        from agent.core.memory_sql_store import ENTRIES_TABLE

        with store._engine.begin() as conn:
            conn.execute(
                sa.update(ENTRIES_TABLE)
                .where(ENTRIES_TABLE.c.entry_id == entry_id)
                .values(updated_at=ts)
            )
