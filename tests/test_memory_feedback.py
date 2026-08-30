"""记忆反馈 API 单元测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
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
    }
    defaults.update(overrides)
    return MemoryConfig(**defaults)


def test_record_feedback_success(tmp_path: Path) -> None:
    """成功记录反馈应更新字段。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="pandas",
        tags=["pandas"],
    )
    store.save(entry)

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.record_feedback("e1", 1) is True

    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.feedback_score == 1
    assert fetched.feedback_count == 1
    assert fetched.last_feedback_at is not None
    # save() 会再次 bump updated_at（memory.py 既有语义）；Windows 时钟分辨率粗
    # （~15.6ms）使两次读数恰好相等，Linux 下可能差几微秒——断言放宽到 1 秒窗口。
    delta = abs((fetched.updated_at - fetched.last_feedback_at).total_seconds())
    assert delta < 1.0


def test_record_feedback_overwrites_latest(tmp_path: Path) -> None:
    """多次反馈只保留最新值，feedback_count 递增。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="pandas",
        tags=["pandas"],
    )
    store.save(entry)

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.record_feedback("e1", 1) is True
    assert manager.record_feedback("e1", -1) is True

    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.feedback_score == -1
    assert fetched.feedback_count == 2


def test_record_feedback_neutral_clears_score(tmp_path: Path) -> None:
    """score=0 可用于取消之前的反馈。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="pandas",
        tags=["pandas"],
    )
    store.save(entry)

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.record_feedback("e1", 1) is True
    assert manager.record_feedback("e1", 0) is True

    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.feedback_score == 0
    assert fetched.feedback_count == 2


def test_record_feedback_missing_entry(tmp_path: Path) -> None:
    """条目不存在时返回 False。"""
    store = StructuredMemoryStore(tmp_path)
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.record_feedback("not_exists", 1) is False


def test_record_feedback_invalid_score(tmp_path: Path) -> None:
    """非法分数返回 False。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="pandas",
    )
    store.save(entry)

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.record_feedback("e1", 2) is False
    assert manager.record_feedback("e1", -2) is False


def test_record_feedback_when_disabled(tmp_path: Path) -> None:
    """记忆未启用时返回 False。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="pandas",
    )
    store.save(entry)

    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(enabled=False),
    )
    assert manager.record_feedback("e1", 1) is False
