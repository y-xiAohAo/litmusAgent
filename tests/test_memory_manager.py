"""MemoryManager 单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class _FailingExtractor(MemoryExtractor):
    """测试用提取器，总是抛出异常。"""

    def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        raise RuntimeError("boom")


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


def test_manager_inject_returns_empty_when_disabled(tmp_path: Path) -> None:
    """未启用记忆时 inject 返回空字符串。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="e1",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="pip install pandas",
            tags=["pandas"],
        )
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(enabled=False),
    )
    assert manager.inject("install pandas") == ""


def test_manager_inject_returns_empty_for_blank_input(tmp_path: Path) -> None:
    """用户输入为空时不注入。"""
    store = StructuredMemoryStore(tmp_path)
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.inject("   ") == ""
    assert manager.inject("") == ""


def test_manager_inject_limits_entries_and_tokens(tmp_path: Path) -> None:
    """注入应同时受 inject_max_entries 与 inject_max_tokens 限制。"""
    store = StructuredMemoryStore(tmp_path)
    for i in range(5):
        store.save(
            MemoryEntry(
                entry_id=f"e{i}",
                category=MemoryCategory.ENVIRONMENT,
                content={},
                summary=f"summary {i}",
                tags=["pandas"],
            )
        )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(
            retrieval_top_k=10,
            inject_max_entries=2,
            inject_max_tokens=10,
        ),
    )
    fragment = manager.inject("pandas")
    lines = [line for line in fragment.split("\n") if line.strip()]
    assert len(lines) <= 3  # header + 最多 2 条
    # token 预算很小，总字符应被截断
    assert len(fragment) <= 10 * 3 + 20


async def test_manager_record_saves_extracted_entries(tmp_path: Path) -> None:
    """record 应调用 extractor 并把条目写入 store。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={"packages": [{"name": "pandas", "version": None}]},
        summary="pip install pandas",
        tags=["pandas"],
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([entry]),
        config=_enabled_config(),
    )
    saved = await manager.record(AgentTrace(), AgentState())
    assert len(saved) == 1
    assert store.get("e1") is not None


async def test_manager_record_filters_sensitive_content(tmp_path: Path) -> None:
    """filter_sensitive 开启时应红码敏感内容。"""
    store = StructuredMemoryStore(tmp_path)
    entry = MemoryEntry(
        entry_id="e1",
        category=MemoryCategory.ENVIRONMENT,
        content={
            "api_key": "sk-12345",
            "packages": [{"name": "pandas", "version": None}],
        },
        summary="配置 api_key=sk-12345",
        tags=["secret"],
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([entry]),
        config=_enabled_config(),
    )
    saved = await manager.record(AgentTrace(), AgentState())
    assert saved[0].content["api_key"] == "[REDACTED]"
    assert saved[0].summary == "[REDACTED]"


async def test_manager_record_enforces_max_entries_per_category(tmp_path: Path) -> None:
    """超过 max_entries_per_category 时应淘汰最旧条目。"""
    store = StructuredMemoryStore(tmp_path)
    for i in range(2):
        store.save(
            MemoryEntry(
                entry_id=f"old{i}",
                category=MemoryCategory.ENVIRONMENT,
                content={},
                summary=f"old {i}",
                tags=[],
            )
        )

    new_entry = MemoryEntry(
        entry_id="new",
        category=MemoryCategory.ENVIRONMENT,
        content={},
        summary="new",
        tags=[],
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([new_entry]),
        config=_enabled_config(max_entries_per_category=2),
    )
    await manager.record(AgentTrace(), AgentState())

    env_entries = store.list_entries(category=MemoryCategory.ENVIRONMENT)
    assert len(env_entries) == 2
    entry_ids = {e.entry_id for e in env_entries}
    assert "new" in entry_ids
    assert "old0" not in entry_ids


async def test_manager_record_failure_returns_empty_list(tmp_path: Path) -> None:
    """extractor 异常时不应抛到上层，返回空列表。"""
    store = StructuredMemoryStore(tmp_path)
    manager = MemoryManager(
        store=store,
        extractor=_FailingExtractor(),
        config=_enabled_config(),
    )
    assert await manager.record(AgentTrace(), AgentState()) == []


def test_manager_cleanup_delegates_to_store(tmp_path: Path) -> None:
    """cleanup 应安全委托给 store 并返回整数。"""
    store = StructuredMemoryStore(tmp_path)
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    assert manager.cleanup() == 0



def test_manager_inject_feedback_boosts_positive(tmp_path: Path) -> None:
    """feedback_score=1 的记忆应优先于无反馈记忆。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="neutral",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="neutral pandas summary",
            tags=["pandas"],
        )
    )
    store.save(
        MemoryEntry(
            entry_id="liked",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="liked pandas summary",
            tags=["pandas"],
            feedback_score=1,
        )
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(retrieval_top_k=5, inject_max_entries=1),
    )
    fragment = manager.inject("install pandas")
    assert "liked pandas summary" in fragment
    assert "neutral pandas summary" not in fragment


def test_manager_inject_feedback_penalizes_negative(tmp_path: Path) -> None:
    """feedback_score=-1 的记忆应排在无反馈记忆之后。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="disliked",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="disliked pandas summary",
            tags=["pandas"],
            feedback_score=-1,
        )
    )
    store.save(
        MemoryEntry(
            entry_id="neutral",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="neutral pandas summary",
            tags=["pandas"],
        )
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(retrieval_top_k=5, inject_max_entries=1),
    )
    fragment = manager.inject("install pandas")
    assert "neutral pandas summary" in fragment
    assert "disliked pandas summary" not in fragment


def test_manager_inject_stale_decay_environment_faster(tmp_path: Path) -> None:
    """environment 记忆应比其它类别更快衰减。"""
    now = datetime.now(timezone.utc)
    ten_days_ago = now - timedelta(days=10)
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="env_old",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="old environment pandas",
            tags=["pandas"],
            updated_at=ten_days_ago,
        )
    )
    store.save(
        MemoryEntry(
            entry_id="pref_old",
            category=MemoryCategory.PREFERENCES,
            content={},
            summary="old preferences pandas",
            tags=["pandas"],
            updated_at=ten_days_ago,
        )
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(
            retrieval_top_k=5,
            inject_max_entries=1,
            stale_threshold_days=30,
            environment_stale_days=7,
        ),
    )
    fragment = manager.inject("pandas")
    # environment 10 天已接近一个半衰期，preferences 10 天仅 1/3 半衰期
    assert "old preferences pandas" in fragment
    assert "old environment pandas" not in fragment


def test_manager_inject_confidence_multiplier(tmp_path: Path) -> None:
    """confidence 较低的记忆应排在后面。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="low_conf",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="low confidence pandas",
            tags=["pandas"],
            confidence=0.3,
        )
    )
    store.save(
        MemoryEntry(
            entry_id="high_conf",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="high confidence pandas",
            tags=["pandas"],
            confidence=1.0,
        )
    )
    manager = MemoryManager(
        store=store,
        extractor=_FakeExtractor([]),
        config=_enabled_config(retrieval_top_k=5, inject_max_entries=1),
    )
    fragment = manager.inject("install pandas")
    assert "high confidence pandas" in fragment
    assert "low confidence pandas" not in fragment


def test_manager_rank_entries_orders_by_effective_score(tmp_path: Path) -> None:
    """_rank_entries 应综合 effective_score 和 updated_at 排序。"""
    now = datetime.now(timezone.utc)
    entries = [
        MemoryEntry(
            entry_id="a",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="pandas",
            tags=["pandas"],
            feedback_score=1,
            updated_at=now - timedelta(days=1),
        ),
        MemoryEntry(
            entry_id="b",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="pandas",
            tags=["pandas"],
            updated_at=now,
        ),
    ]
    manager = MemoryManager(
        store=StructuredMemoryStore(tmp_path),
        extractor=_FakeExtractor([]),
        config=_enabled_config(),
    )
    ranked = manager._rank_entries(entries, "pandas")
    assert ranked[0].entry_id == "a"
    assert ranked[1].entry_id == "b"
