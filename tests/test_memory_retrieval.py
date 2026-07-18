"""记忆系统分层检索测试（L0 recency 兜底 + L2 语义重排 + 内容快照）。

覆盖：
  - L0：零命中时注入最近 N 条 / 关闭时零注入 / 按时间降序
  - L2：LLM JSON 排序 / LLM 失败降级 L0 / 未启用不调 LLM
  - 快照：file_write 产物记忆含 content_preview（截断）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _make_entry(entry_id: str, summary: str, hours_ago: int) -> MemoryEntry:
    """构造指定时间的记忆条目。"""
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return MemoryEntry(
        entry_id=entry_id,
        category=MemoryCategory.ARTIFACTS,
        content={"path": f"/workspace/{entry_id}.md"},
        summary=summary,
        tags=["artifact"],
        updated_at=ts,
    )


def _make_manager(root: Path, **config_kwargs) -> MemoryManager:
    store = StructuredMemoryStore(root)
    config = MemoryConfig(enabled=True, **config_kwargs)
    return MemoryManager(store=store, extractor=_FakeExtractor(), config=config)


class TestRecencyFallback:
    """L0：零命中时的 recency 兜底注入。"""

    def test_zero_overlap_injects_recent_entries(self, tmp_path: Path) -> None:
        """查询与记忆零重叠时，兜底注入最近 N 条记忆。"""
        manager = _make_manager(tmp_path)
        manager._store.save(_make_entry("e1", "生成产物：/workspace/notes.md", 1))
        manager._store.save(_make_entry("e2", "生成产物：/workspace/old.md", 100))

        injected = manager.inject("完全不相关的查询内容")
        assert injected != ""
        assert "notes.md" in injected

    def test_fallback_disabled_returns_empty(self, tmp_path: Path) -> None:
        """recency_fallback=False 时恢复零注入（旧行为）。"""
        manager = _make_manager(tmp_path, recency_fallback=False)
        manager._store.save(_make_entry("e1", "生成产物：/workspace/notes.md", 1))

        assert manager.inject("完全不相关的查询内容") == ""

    def test_fallback_ordered_by_recency(self, tmp_path: Path) -> None:
        """兜底注入按 updated_at 降序（最新在前）。"""
        manager = _make_manager(tmp_path)
        manager._store.save(_make_entry("old", "生成产物：/workspace/old.md", 100))
        manager._store.save(_make_entry("new", "生成产物：/workspace/new.md", 1))

        injected = manager.inject("完全不相关的查询内容")
        assert injected.index("new.md") < injected.index("old.md")

    def test_overlap_hit_still_uses_l1(self, tmp_path: Path) -> None:
        """字面命中时走 L1 正常路径（不触发兜底）。"""
        manager = _make_manager(tmp_path)
        manager._store.save(_make_entry("e1", "生成产物：/workspace/notes.md", 1))

        injected = manager.inject("查看 notes.md 的内容")
        assert "notes.md" in injected


class _FakeLLM:
    """返回预设 JSON 排序的假 LLM。"""

    def __init__(self, response: str | Exception) -> None:
        self._response = response
        self.calls = 0

    async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return {"content": self._response, "tool_calls": None}


class TestSemanticRerank:
    """L2：条件 LLM 语义重排。"""

    @pytest.mark.asyncio
    async def test_semantic_rank_orders_by_llm(self, tmp_path: Path) -> None:
        """L1 未命中 + semantic_retrieval 开启 → LLM 排序决定注入内容。"""
        manager = _make_manager(tmp_path, semantic_retrieval=True)
        manager._store.save(_make_entry("e1", "生成产物：/workspace/aaa.md", 1))
        manager._store.save(_make_entry("e2", "生成产物：/workspace/bbb.md", 2))
        llm = _FakeLLM('{"ranking": ["e2", "e1"]}')
        manager._llm_client = llm

        injected = await manager.inject_async("查找我需要的文件")
        assert injected != ""
        assert llm.calls == 1
        assert injected.index("bbb.md") < injected.index("aaa.md")

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_recency(self, tmp_path: Path) -> None:
        """LLM 调用失败 → 降级 L0 recency 注入。"""
        manager = _make_manager(tmp_path, semantic_retrieval=True)
        manager._store.save(_make_entry("e1", "生成产物：/workspace/aaa.md", 1))
        manager._llm_client = _FakeLLM(RuntimeError("api down"))

        injected = await manager.inject_async("查找文件")
        assert "aaa.md" in injected

    @pytest.mark.asyncio
    async def test_semantic_disabled_no_llm_call(self) -> None:
        """semantic_retrieval 关闭时（默认）不调用 LLM。"""
        manager = _make_manager(Path(tempfile.mkdtemp()), semantic_retrieval=False)
        llm = _FakeLLM('{"ranking": []}')
        manager._llm_client = llm
        manager._store.save(_make_entry("e1", "生成产物：/workspace/aaa.md", 1))

        injected = await manager.inject_async("查找文件")
        assert llm.calls == 0
        assert "aaa.md" in injected  # 走 L0 兜底

    @pytest.mark.asyncio
    async def test_l1_hit_skips_llm(self, tmp_path: Path) -> None:
        """L1 字面命中时不调用 LLM（条件触发）。"""
        manager = _make_manager(tmp_path, semantic_retrieval=True)
        manager._store.save(_make_entry("e1", "生成产物：/workspace/notes.md", 1))
        llm = _FakeLLM('{"ranking": ["e1"]}')
        manager._llm_client = llm

        injected = await manager.inject_async("查看 notes.md")
        assert llm.calls == 0
        assert "notes.md" in injected


import tempfile  # noqa: E402


class TestArtifactContentPreview:
    """artifact 记忆的内容快照（file_write 产物）。"""

    def _trace_with_file_write(self, content: str):
        """构造含一次成功 file_write 事件的假 Trace。"""

        class FakeTrace:
            def to_dict(self):  # noqa: ANN202
                return {
                    "steps": [
                        {
                            "events": [
                                {
                                    "event_type": "tool_execution",
                                    "payload": {
                                        "tool": "file_write",
                                        "arguments": {
                                            "path": "/workspace/notes.md",
                                            "content": content,
                                        },
                                        "success": True,
                                        "content": "已写入 /workspace/notes.md",
                                    },
                                }
                            ]
                        }
                    ]
                }

        return FakeTrace()

    def test_file_write_records_content_preview(self) -> None:
        """file_write 产物的 artifact 记忆应含 content_preview。"""
        from agent.core.memory import RuleMemoryExtractor

        extractor = RuleMemoryExtractor()
        entries = extractor.extract(
            self._trace_with_file_write("我的项目代号是 hermes-2026"),
            None,
            {},
        )
        artifacts = [e for e in entries if e.category == MemoryCategory.ARTIFACTS]
        assert artifacts, "应提取出 artifact 记忆"
        preview = artifacts[0].content.get("content_preview", "")
        assert "hermes-2026" in preview

    def test_content_preview_truncated(self) -> None:
        """content_preview 截断到 200 字。"""
        from agent.core.memory import RuleMemoryExtractor

        extractor = RuleMemoryExtractor()
        entries = extractor.extract(
            self._trace_with_file_write("x" * 500),
            None,
            {},
        )
        artifacts = [e for e in entries if e.category == MemoryCategory.ARTIFACTS]
        preview = artifacts[0].content.get("content_preview", "")
        assert len(preview) <= 200


class TestInjectorPreview:
    """MemoryInjector 注入文本中的内容快照。"""

    def test_inject_includes_content_preview(self, tmp_path: Path) -> None:
        """artifact 记忆的 content_preview 应出现在注入文本中。"""
        manager = _make_manager(tmp_path)
        entry = _make_entry("e1", "生成产物：/workspace/notes.md", 1)
        entry.content["content_preview"] = "我的项目代号是 hermes-2026"
        manager._store.save(entry)

        injected = manager.inject("完全不相关的查询")
        assert "hermes-2026" in injected
