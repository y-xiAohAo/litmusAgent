"""SQL 记忆存储后端（SQLAlchemy Core，SQLite 测试 / MySQL 验证）。

与 StructuredMemoryStore（JSONL）实现同一 MemoryStore 接口；行为一致性由
tests/test_memory_store_contract.py 的参数化契约套件双后端复验。

设计要点：
  - content/tags/linked_entry_ids 存 JSON 列；updated_at/category 建索引；
  - text 检索复用与 JSONL 后端完全相同的分词与重叠打分（模块级共享函数），
    SQL 层只负责 category/time_range 过滤候选集——职责切分与 JSONL 一致。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa

from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryQuery,
    MemoryStore,
    _ensure_aware_dt,
    _entry_text_of,
    _tokenize_text,
)

_METADATA = sa.MetaData()

ENTRIES_TABLE = sa.Table(
    "memory_entries",
    _METADATA,
    sa.Column("entry_id", sa.String(64), primary_key=True),
    sa.Column("category", sa.String(32), nullable=False),
    sa.Column("uri", sa.String(255), nullable=False, default=""),
    sa.Column("summary", sa.Text, nullable=False, default=""),
    sa.Column("tags", sa.JSON, nullable=False),
    sa.Column("content", sa.JSON, nullable=False),
    sa.Column("source_trace_id", sa.String(64), nullable=True),
    sa.Column("source_run_id", sa.String(64), nullable=True),
    sa.Column("confidence", sa.Float, nullable=False, default=1.0),
    sa.Column("feedback_score", sa.Integer, nullable=True),
    sa.Column("feedback_count", sa.Integer, nullable=False, default=0),
    sa.Column("last_feedback_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("stale", sa.Boolean, nullable=False, default=False),
    sa.Column("linked_entry_ids", sa.JSON, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_memory_entries_cat_updated", "category", "updated_at"),
)


class SqlMemoryStore(MemoryStore):
    """SQLAlchemy Core 实现的记忆存储后端。

    Args:
        url: SQLAlchemy 数据库连接串，如
            `sqlite:////path/to/memory.db` 或
            `mysql+pymysql://user:pass@host:3306/hermes?charset=utf8mb4`。
    """

    def __init__(self, url: str) -> None:
        """初始化并建表（幂等）。"""
        self._engine = sa.create_engine(url)
        _METADATA.create_all(self._engine)

    # ------------------------------------------------------------------
    # 行 ↔ 实体
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sa.Row[Any]) -> MemoryEntry:
        """把数据库行还原为 MemoryEntry（时间戳补 UTC 时区）。"""
        m = row._mapping
        return MemoryEntry(
            entry_id=m["entry_id"],
            category=MemoryCategory(m["category"]),
            uri=m["uri"],
            summary=m["summary"],
            tags=list(m["tags"] or []),
            content=dict(m["content"] or {}),
            source_trace_id=m["source_trace_id"],
            source_run_id=m["source_run_id"],
            confidence=m["confidence"],
            feedback_score=m["feedback_score"],
            feedback_count=m["feedback_count"],
            last_feedback_at=(
                _ensure_aware_dt(m["last_feedback_at"]) if m["last_feedback_at"] else None
            ),
            stale=bool(m["stale"]),
            linked_entry_ids=list(m["linked_entry_ids"] or []),
            created_at=_ensure_aware_dt(m["created_at"]),
            updated_at=_ensure_aware_dt(m["updated_at"]),
        )

    # ------------------------------------------------------------------
    # MemoryStore 接口
    # ------------------------------------------------------------------

    def save(self, entry: MemoryEntry) -> MemoryEntry:
        """保存或覆盖一条记忆（upsert；覆盖时刷新 updated_at，与 JSONL 一致）。"""
        if not entry.uri:
            entry.uri = f"hermes://memory/{entry.category.value}/{entry.entry_id}.jsonl"
        entry.updated_at = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "entry_id": entry.entry_id,
            "category": entry.category.value,
            "uri": entry.uri,
            "summary": entry.summary,
            "tags": list(entry.tags),
            "content": dict(entry.content),
            "source_trace_id": entry.source_trace_id,
            "source_run_id": entry.source_run_id,
            "confidence": entry.confidence,
            "feedback_score": entry.feedback_score,
            "feedback_count": entry.feedback_count,
            "last_feedback_at": entry.last_feedback_at,
            "stale": entry.stale,
            "linked_entry_ids": list(entry.linked_entry_ids),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        with self._engine.begin() as conn:
            updated = conn.execute(
                sa.update(ENTRIES_TABLE)
                .where(ENTRIES_TABLE.c.entry_id == entry.entry_id)
                .values(**values)
            ).rowcount
            if updated == 0:
                conn.execute(sa.insert(ENTRIES_TABLE).values(**values))
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        """按 entry_id 读取单条记忆；不存在返回 None。"""
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(ENTRIES_TABLE).where(ENTRIES_TABLE.c.entry_id == entry_id)
            ).first()
        return self._row_to_entry(row) if row is not None else None

    def query(self, query: MemoryQuery) -> list[MemoryEntry]:
        """按条件检索：SQL 过滤 category/time_range，tags/text 复用共享打分。"""
        stmt = sa.select(ENTRIES_TABLE)
        if query.categories:
            stmt = stmt.where(
                ENTRIES_TABLE.c.category.in_([c.value for c in query.categories])
            )
        if query.time_range is not None:
            start, end = query.time_range
            stmt = stmt.where(
                ENTRIES_TABLE.c.updated_at >= _ensure_aware_dt(start),
                ENTRIES_TABLE.c.updated_at <= _ensure_aware_dt(end),
            )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        entries = [self._row_to_entry(row) for row in rows]

        if query.tags:
            query_tag_set = set(query.tags)
            entries = [e for e in entries if query_tag_set.intersection(e.tags)]

        text = query.text.strip() if query.text else ""
        if text:
            query_tokens = _tokenize_text(text)
            scored: list[tuple[int, MemoryEntry]] = []
            for entry in entries:
                entry_tokens = _tokenize_text(_entry_text_of(entry))
                score = len(query_tokens.intersection(entry_tokens))
                if score > 0:
                    scored.append((score, entry))
            scored.sort(key=lambda item: (item[0], item[1].updated_at.timestamp()), reverse=True)
            entries = [entry for _, entry in scored]

        return entries[: query.top_k]

    def delete(self, entry_id: str) -> bool:
        """删除指定 entry_id 的记忆；成功返回 True。"""
        with self._engine.begin() as conn:
            deleted = conn.execute(
                sa.delete(ENTRIES_TABLE).where(ENTRIES_TABLE.c.entry_id == entry_id)
            ).rowcount
        return deleted > 0

    def cleanup(self, max_age: timedelta | None = None) -> int:
        """清理超过 max_age 的记忆，返回删除数量；None 时不清理。"""
        if max_age is None:
            return 0
        cutoff = datetime.now(timezone.utc) - max_age
        with self._engine.begin() as conn:
            deleted = conn.execute(
                sa.delete(ENTRIES_TABLE).where(ENTRIES_TABLE.c.updated_at < cutoff)
            ).rowcount
        return int(deleted)

    def list_entries(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
        """列出记忆条目（按 updated_at 升序）；可指定类别。"""
        stmt = sa.select(ENTRIES_TABLE).order_by(ENTRIES_TABLE.c.updated_at)
        if category is not None:
            stmt = stmt.where(ENTRIES_TABLE.c.category == category.value)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_entry(row) for row in rows]

    def list_recent(self, limit: int) -> list[MemoryEntry]:
        """按 updated_at 倒序返回最近 limit 条（L0 recency 兜底使用）。"""
        stmt = (
            sa.select(ENTRIES_TABLE)
            .order_by(ENTRIES_TABLE.c.updated_at.desc())
            .limit(max(1, limit))
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [self._row_to_entry(row) for row in rows]
