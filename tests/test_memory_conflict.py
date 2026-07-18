"""记忆冲突检测与审计单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
    MemoryConflictDetector,
    MemoryEntry,
    MemoryExtractor,
    MemoryManager,
    StructuredMemoryStore,
)
from agent.core.state import AgentState
from agent.core.trace import AgentTrace


class _FakeExtractor(MemoryExtractor):
    """测试用提取器，返回预定义条目。"""

    def __init__(self, entries: list[MemoryEntry]) -> None:
        self.entries = entries

    def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        return list(self.entries)


def _enabled_config(**overrides: Any) -> MemoryConfig:
    defaults = {
        "enabled": True,
        "memory_root": ".hermes/memory",
        "max_entries_per_category": 100,
        "retrieval_top_k": 5,
        "inject_max_entries": 5,
        "inject_max_tokens": 800,
        "filter_sensitive": True,
        "sensitive_patterns": ["api_key", "password", "secret", "token"],
        "stale_threshold_days": 30,
        "environment_stale_days": 7,
    }
    defaults.update(overrides)
    return MemoryConfig(**defaults)


def test_detect_environment_version_mismatch(tmp_path: Path) -> None:
    """同名包不同版本应产生 version_mismatch 冲突。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="env1",
            category=MemoryCategory.ENVIRONMENT,
            content={"packages": [{"name": "pandas", "version": "1.0"}]},
            summary="pandas 1.0",
        )
    )
    store.save(
        MemoryEntry(
            entry_id="env2",
            category=MemoryCategory.ENVIRONMENT,
            content={"packages": [{"name": "pandas", "version": "2.0"}]},
            summary="pandas 2.0",
        )
    )

    detector = MemoryConflictDetector()
    conflicts = detector.detect(store)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "version_mismatch"
    assert "env1" in conflicts[0].entry_ids
    assert "env2" in conflicts[0].entry_ids


def test_detect_artifact_duplicate(tmp_path: Path) -> None:
    """相同 path 多条记录应产生 duplicate 冲突。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="art1",
            category=MemoryCategory.ARTIFACTS,
            content={"path": "/workspace/report.md"},
            summary="report 1",
        )
    )
    store.save(
        MemoryEntry(
            entry_id="art2",
            category=MemoryCategory.ARTIFACTS,
            content={"path": "/workspace/report.md"},
            summary="report 2",
        )
    )

    detector = MemoryConflictDetector()
    conflicts = detector.detect(store)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "duplicate"


def test_detect_preference_contradiction(tmp_path: Path) -> None:
    """相同 key 不同 value 应产生 contradiction 冲突。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="pref1",
            category=MemoryCategory.PREFERENCES,
            content={"key": "indent", "value": "spaces"},
            summary="prefer spaces",
        )
    )
    store.save(
        MemoryEntry(
            entry_id="pref2",
            category=MemoryCategory.PREFERENCES,
            content={"key": "indent", "value": "tabs"},
            summary="prefer tabs",
        )
    )

    detector = MemoryConflictDetector()
    conflicts = detector.detect(store)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "contradiction"


def test_detect_failure_pattern_recovery_conflict(tmp_path: Path) -> None:
    """相同 (tool, exc_type) 不同 recovery 应产生 recovery_conflict。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="fp1",
            category=MemoryCategory.FAILURE_PATTERNS,
            content={
                "tool": "sandbox_exec",
                "exc_type": "ModuleNotFoundError",
                "recovery": "pip install",
            },
            summary="missing module",
        )
    )
    store.save(
        MemoryEntry(
            entry_id="fp2",
            category=MemoryCategory.FAILURE_PATTERNS,
            content={
                "tool": "sandbox_exec",
                "exc_type": "ModuleNotFoundError",
                "recovery": "apt install",
            },
            summary="missing module alt",
        )
    )

    detector = MemoryConflictDetector()
    conflicts = detector.detect(store)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "recovery_conflict"


def _write_legacy_entry(
    tmp_path: Path,
    entry_id: str,
    category: str,
    summary: str,
    updated_at: datetime,
    stale: bool = False,
) -> None:
    """直接写入 JSONL，绕过 save() 对 updated_at 的刷新。"""
    category_dir = tmp_path / category
    category_dir.mkdir(parents=True, exist_ok=True)
    stale_str = "true" if stale else "false"
    (category_dir / f"{entry_id}.jsonl").write_text(
        f'{{"entry_id":"{entry_id}","category":"{category}","content":{{}},'
        f'"summary":"{summary}","tags":[],"uri":"",'
        f'"created_at":"{updated_at.isoformat()}","updated_at":"{updated_at.isoformat()}",'
        f'"confidence":1.0,"stale":{stale_str}}}\n',
        encoding="utf-8",
    )


def test_audit_marks_environment_stale_faster(tmp_path: Path) -> None:
    """environment 条目应比其它类别更快被标灰。"""
    now = datetime.now(timezone.utc)
    ten_days_ago = now - timedelta(days=10)
    store = StructuredMemoryStore(tmp_path)
    _write_legacy_entry(tmp_path, "env_old", "environment", "old env", ten_days_ago)
    _write_legacy_entry(tmp_path, "pref_old", "preferences", "old pref", ten_days_ago)

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    stale_marked, conflicts = manager.audit()
    stale_ids = {e.entry_id for e in stale_marked}
    assert "env_old" in stale_ids
    assert "pref_old" not in stale_ids


def test_audit_creates_conflict_links(tmp_path: Path) -> None:
    """audit 应在冲突条目间建立单向链接。"""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="old",
            category=MemoryCategory.ARTIFACTS,
            content={"path": "/workspace/report.md"},
            summary="old report",
            updated_at=yesterday,
        )
    )
    store.save(
        MemoryEntry(
            entry_id="new",
            category=MemoryCategory.ARTIFACTS,
            content={"path": "/workspace/report.md"},
            summary="new report",
            updated_at=now,
        )
    )

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    manager.audit()

    newest = store.get("new")
    assert newest is not None
    assert "old" in newest.linked_entry_ids


def test_audit_disabled_returns_empty(tmp_path: Path) -> None:
    """记忆未启用时 audit 返回空。"""
    store = StructuredMemoryStore(tmp_path)
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(enabled=False),
    )
    stale, conflicts = manager.audit()
    assert stale == []
    assert conflicts == []


def test_audit_does_not_re_save_already_stale(tmp_path: Path) -> None:
    """已标灰条目不应被重复保存。"""
    now = datetime.now(timezone.utc)
    ten_days_ago = now - timedelta(days=10)
    store = StructuredMemoryStore(tmp_path)
    _write_legacy_entry(
        tmp_path, "already_stale", "environment", "already stale", ten_days_ago, stale=True
    )

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    stale_marked, _ = manager.audit()
    assert stale_marked == []
