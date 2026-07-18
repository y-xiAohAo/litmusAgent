"""测试长期记忆存储层（Phase 8.1）。

覆盖 MemoryCategory、MemoryEntry、MemoryQuery、StructuredMemoryStore
以及 MemoryConfig 的基本行为。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from agent.config import MemoryConfig, load_config
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryQuery,
    StructuredMemoryStore,
)


def _entry(
    entry_id: str,
    category: MemoryCategory,
    summary: str,
    content: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    updated_at: datetime | None = None,
) -> MemoryEntry:
    """构造测试用的 MemoryEntry，简化重复代码。"""
    return MemoryEntry(
        entry_id=entry_id,
        category=category,
        content=content or {},
        summary=summary,
        tags=tags or [],
        updated_at=updated_at or datetime.now(timezone.utc),
    )


def test_memory_category_values() -> None:
    """MemoryCategory 枚举值应符合预期。"""
    assert MemoryCategory.ENVIRONMENT.value == "environment"
    assert MemoryCategory.ARTIFACTS.value == "artifacts"
    assert MemoryCategory.FAILURE_PATTERNS.value == "failure_patterns"
    assert MemoryCategory.TASK_SUMMARIES.value == "task_summaries"
    assert MemoryCategory.PREFERENCES.value == "preferences"


def test_memory_entry_generates_uri() -> None:
    """MemoryEntry 应自动生成标准 URI。"""
    entry = MemoryEntry(
        entry_id="abc123",
        category=MemoryCategory.ENVIRONMENT,
        content={"packages": []},
        summary="test",
    )
    assert entry.uri == "hermes://memory/environment/abc123.jsonl"


def test_structured_store_save_and_get(tmp_path: Path) -> None:
    """save 后应能通过 entry_id 读回。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={"python_version": "3.11"},
        summary="py311",
        tags=["python"],
    )
    saved = store.save(entry)
    assert saved.uri
    assert (tmp_path / "environment" / "e1.jsonl").exists()

    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.entry_id == "e1"
    assert fetched.category == MemoryCategory.ENVIRONMENT
    assert fetched.content["python_version"] == "3.11"


def test_structured_store_get_missing_returns_none(tmp_path: Path) -> None:
    """查询不存在的 entry_id 应返回 None。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    assert store.get("not_exists") is None


def test_structured_store_save_overwrites(tmp_path: Path) -> None:
    """重复保存同一 entry_id 应覆盖旧数据。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={"packages": [{"name": "pandas", "version": "1.0"}]},
        summary="old",
    )
    store.save(entry)
    entry2 = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={"packages": [{"name": "pandas", "version": "2.0"}]},
        summary="new",
    )
    store.save(entry2)
    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.summary == "new"
    assert fetched.content["packages"][0]["version"] == "2.0"


def test_structured_store_query_by_category(tmp_path: Path) -> None:
    """按 category 过滤应只返回匹配条目。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "env"))
    store.save(_entry("e2", MemoryCategory.ARTIFACTS, "art"))
    results = store.query(MemoryQuery(categories=[MemoryCategory.ENVIRONMENT]))
    assert len(results) == 1
    assert results[0].entry_id == "e1"


def test_structured_store_query_by_tags(tmp_path: Path) -> None:
    """按 tags 过滤应匹配至少一个标签。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "a", tags=["pandas"]))
    store.save(_entry("e2", MemoryCategory.ENVIRONMENT, "b", tags=["numpy"]))
    results = store.query(MemoryQuery(tags=["pandas"]))
    assert len(results) == 1
    assert results[0].entry_id == "e1"


def test_structured_store_query_by_text(tmp_path: Path) -> None:
    """按 text 查询应做关键词/字符重叠打分。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ARTIFACTS, "sales report", tags=["sales"]))
    store.save(_entry("e2", MemoryCategory.ARTIFACTS, "user guide", tags=["guide"]))
    results = store.query(MemoryQuery(text="sales"))
    assert len(results) == 1
    assert results[0].entry_id == "e1"


def test_structured_store_query_top_k(tmp_path: Path) -> None:
    """top_k 应限制返回数量。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    for i in range(5):
        store.save(
            MemoryEntry(
                entry_id=f"e{i}",
                category=MemoryCategory.PREFERENCES,
                content={},
                summary=f"pref {i}",
                tags=[f"tag{i}"],
            )
        )
    results = store.query(MemoryQuery(top_k=2))
    assert len(results) == 2


def test_structured_store_delete(tmp_path: Path) -> None:
    """delete 应移除文件并返回是否成功。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "x"))
    assert store.delete("e1") is True
    assert store.get("e1") is None
    assert store.delete("e1") is False


def test_structured_store_list_entries(tmp_path: Path) -> None:
    """list_entries 应能列出全部或指定 category 的条目。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "env"))
    store.save(_entry("e2", MemoryCategory.ARTIFACTS, "art"))
    all_entries = store.list_entries()
    assert len(all_entries) == 2
    env_entries = store.list_entries(MemoryCategory.ENVIRONMENT)
    assert len(env_entries) == 1


def test_structured_store_cleanup_by_age(tmp_path: Path) -> None:
    """cleanup 应按时间清理过期记忆。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    category_dir = tmp_path / "environment"
    category_dir.mkdir(parents=True)
    old_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    (category_dir / "old.jsonl").write_text(
        f'{{"entry_id":"old","category":"environment","content":{{}},'
        f'"summary":"old","tags":[],"uri":"",'
        f'"created_at":"{old_time}","updated_at":"{old_time}",'
        f'"confidence":1.0}}\n',
        encoding="utf-8",
    )
    store.save(_entry("new", MemoryCategory.ENVIRONMENT, "new"))
    removed = store.cleanup(max_age=timedelta(days=30))
    assert removed == 1
    assert store.get("old") is None
    assert store.get("new") is not None


def test_structured_store_rejects_path_traversal(tmp_path: Path) -> None:
    """entry_id 包含路径遍历字符时应拒绝。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    bad = MemoryEntry(
        entry_id="../../etc/passwd",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="bad",
    )
    with pytest.raises(ValueError):
        store.save(bad)


def test_memory_config_defaults() -> None:
    """MemoryConfig 默认值应符合 Phase 8 设计。"""
    config = MemoryConfig()
    assert config.enabled is False
    assert config.backend == "structured"
    assert config.memory_root == ".hermes/memory"
    assert config.max_entries_per_category == 100
    assert config.stale_threshold_days == 30
    assert config.environment_stale_days == 7


def test_agent_config_loads_memory_section(tmp_path: Path) -> None:
    """YAML 中 agent.memory 配置应能被正确加载。"""
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "agent:\n  memory:\n    enabled: true\n    memory_root: .hermes/test_memory\n",
        encoding="utf-8",
    )
    config = load_config(yaml_path)
    assert config.agent.memory.enabled is True
    assert config.agent.memory.memory_root == ".hermes/test_memory"


def test_structured_store_query_by_time_range(tmp_path: Path) -> None:
    """按时间范围过滤应只返回范围内条目。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    category_dir = tmp_path / "environment"
    category_dir.mkdir(parents=True)
    old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    (category_dir / "old.jsonl").write_text(
        f'{{"entry_id":"old","category":"environment","content":{{}},'
        f'"summary":"old env","tags":[],"uri":"",'
        f'"created_at":"{old_time}","updated_at":"{old_time}",'
        f'"confidence":1.0}}\n',
        encoding="utf-8",
    )
    store.save(_entry("new", MemoryCategory.ENVIRONMENT, "new env"))

    start = datetime.now(timezone.utc) - timedelta(days=5)
    end = datetime.now(timezone.utc) + timedelta(days=1)
    results = store.query(MemoryQuery(time_range=(start, end)))
    assert len(results) == 1
    assert results[0].entry_id == "new"


def test_structured_store_query_combined_filters(tmp_path: Path) -> None:
    """category、tags、text 应同时生效（与关系）。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ARTIFACTS, "sales report", tags=["sales"]))
    store.save(_entry("e2", MemoryCategory.ARTIFACTS, "user guide", tags=["sales"]))
    store.save(_entry("e3", MemoryCategory.ENVIRONMENT, "sales env", tags=["sales"]))

    results = store.query(
        MemoryQuery(
            categories=[MemoryCategory.ARTIFACTS],
            tags=["sales"],
            text="report",
        )
    )
    assert len(results) == 1
    assert results[0].entry_id == "e1"


def test_structured_store_query_returns_empty_when_no_match(tmp_path: Path) -> None:
    """无匹配时应返回空列表。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "pandas", tags=["pandas"]))
    assert store.query(MemoryQuery(text="nonexistent")) == []
    assert store.query(MemoryQuery(tags=["numpy"])) == []


def test_structured_store_query_empty_store(tmp_path: Path) -> None:
    """空 store 查询应返回空列表。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    assert store.query(MemoryQuery()) == []


def test_structured_store_get_rejects_path_traversal(tmp_path: Path) -> None:
    """get 也应拒绝非法 entry_id。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    with pytest.raises(ValueError):
        store.get("../etc/passwd")


def test_structured_store_delete_rejects_path_traversal(tmp_path: Path) -> None:
    """delete 也应拒绝非法 entry_id。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    with pytest.raises(ValueError):
        store.delete("../etc/passwd")


def test_structured_store_cleanup_none_returns_zero(tmp_path: Path) -> None:
    """cleanup(max_age=None) 不应删除任何条目。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "env"))
    assert store.cleanup(max_age=None) == 0
    assert store.get("e1") is not None


def test_structured_store_cleanup_empty_store(tmp_path: Path) -> None:
    """空 store 清理应返回 0。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    assert store.cleanup(max_age=timedelta(days=1)) == 0


def test_memory_entry_default_timestamps_are_utc_aware() -> None:
    """MemoryEntry 默认时间戳应带 UTC 时区。"""
    entry = MemoryEntry(
        entry_id="t1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="ts",
    )
    assert entry.created_at.tzinfo is not None
    assert entry.updated_at.tzinfo is not None


def test_structured_store_loads_naive_datetime_as_utc(tmp_path: Path) -> None:
    """手动编辑导致缺少时区时，应假设为 UTC。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    category_dir = tmp_path / "environment"
    category_dir.mkdir(parents=True)
    file_path = category_dir / "e1.jsonl"
    file_path.write_text(
        '{"entry_id":"e1","category":"environment","content":{},'
        '"summary":"x","tags":[],"uri":"",'
        '"created_at":"2026-07-01T10:00:00","updated_at":"2026-07-01T10:00:00",'
        '"confidence":1.0}\n',
        encoding="utf-8",
    )
    entry = store.get("e1")
    assert entry is not None
    assert entry.created_at.tzinfo is not None
    assert entry.updated_at.tzinfo is not None


def test_structured_store_query_whitespace_text_returns_all(tmp_path: Path) -> None:
    """纯空白 text 应视为无过滤条件，返回所有条目。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "env"))
    store.save(_entry("e2", MemoryCategory.ARTIFACTS, "art"))
    results = store.query(MemoryQuery(text="   "))
    assert len(results) == 2


def test_structured_store_query_empty_list_means_no_filter(tmp_path: Path) -> None:
    """空 categories/tags 列表应等效于不过滤。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "env"))
    store.save(_entry("e2", MemoryCategory.ARTIFACTS, "art"))
    assert len(store.query(MemoryQuery(categories=[]))) == 2
    assert len(store.query(MemoryQuery(tags=[]))) == 2


def test_structured_store_save_updates_updated_at(tmp_path: Path) -> None:
    """覆盖写入时应刷新 updated_at。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    old_time = datetime.now(timezone.utc) - timedelta(days=1)
    entry = _entry(
        "e1",
        MemoryCategory.ENVIRONMENT,
        "old",
        updated_at=old_time,
    )
    store.save(entry)
    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.updated_at > old_time


def test_structured_store_query_time_range_with_naive_datetime(tmp_path: Path) -> None:
    """time_range 传入 naive datetime 时不应报错。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(_entry("e1", MemoryCategory.ENVIRONMENT, "env"))
    start = datetime.now() - timedelta(days=1)
    end = datetime.now() + timedelta(days=1)
    results = store.query(MemoryQuery(time_range=(start, end)))
    assert len(results) == 1


def test_structured_store_query_matches_numeric_content(tmp_path: Path) -> None:
    """content 中的数字应参与检索。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    store.save(
        _entry(
            "e1",
            MemoryCategory.ENVIRONMENT,
            "env",
            content={"timeout": 30},
        )
    )
    results = store.query(MemoryQuery(text="30"))
    assert len(results) == 1


def test_structured_store_rejects_malicious_entry_id_on_load(tmp_path: Path) -> None:
    """从磁盘加载到恶意 entry_id 时应拒绝。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    category_dir = tmp_path / "environment"
    category_dir.mkdir(parents=True)
    file_path = category_dir / "safe.jsonl"
    file_path.write_text(
        '{"entry_id":"../etc/passwd","category":"environment","content":{},'
        '"summary":"x","tags":[],"uri":"",'
        '"created_at":"2026-07-01T10:00:00+00:00","updated_at":"2026-07-01T10:00:00+00:00",'
        '"confidence":1.0}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        store.list_entries()


def test_structured_store_loads_old_jsonl_without_84_fields(tmp_path: Path) -> None:
    """Phase 8.1~8.3 生成的旧 JSONL 应能平滑升级到 8.4。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    category_dir = tmp_path / "environment"
    category_dir.mkdir(parents=True)
    file_path = category_dir / "legacy.jsonl"
    file_path.write_text(
        '{"entry_id":"legacy","category":"environment","content":{"packages":[]},'
        '"summary":"legacy entry","tags":["pandas"],"uri":"",'
        '"created_at":"2026-07-01T10:00:00+00:00","updated_at":"2026-07-01T10:00:00+00:00",'
        '"confidence":1.0}\n',
        encoding="utf-8",
    )
    entry = store.get("legacy")
    assert entry is not None
    assert entry.feedback_score is None
    assert entry.feedback_count == 0
    assert entry.last_feedback_at is None
    assert entry.stale is False
    assert entry.linked_entry_ids == []


def test_structured_store_loads_84_fields(tmp_path: Path) -> None:
    """包含 8.4 新字段的 JSONL 应正确反序列化。"""
    store = StructuredMemoryStore(root_dir=tmp_path)
    category_dir = tmp_path / "environment"
    category_dir.mkdir(parents=True)
    file_path = category_dir / "new.jsonl"
    file_path.write_text(
        '{"entry_id":"new","category":"environment","content":{"packages":[]},'
        '"summary":"new entry","tags":["pandas"],"uri":"",'
        '"created_at":"2026-07-01T10:00:00+00:00","updated_at":"2026-07-02T10:00:00+00:00",'
        '"confidence":0.9,"feedback_score":1,"feedback_count":2,'
        '"last_feedback_at":"2026-07-02T10:00:00+00:00","stale":true,'
        '"linked_entry_ids":["old1","old2"]}\n',
        encoding="utf-8",
    )
    entry = store.get("new")
    assert entry is not None
    assert entry.feedback_score == 1
    assert entry.feedback_count == 2
    assert entry.stale is True
    assert entry.linked_entry_ids == ["old1", "old2"]
    assert entry.confidence == 0.9


def test_memory_entry_84_defaults() -> None:
    """新字段默认值应符合 8.4 设计。"""
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="test",
    )
    assert entry.feedback_score is None
    assert entry.feedback_count == 0
    assert entry.last_feedback_at is None
    assert entry.stale is False
    assert entry.linked_entry_ids == []
