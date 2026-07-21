"""LLM 对话事实提取器与配套机制测试（TD-013）。

覆盖：
  - LLMMemoryExtractor：预过滤规则 / JSON 容错解析 / 失败降级 / 条目构造
  - MemoryManager：PREFERENCES 内容规范化去重 / max_age_days 清理
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
from agent.core.memory_llm_extractor import LLMMemoryExtractor
from agent.core.state import AgentState
from agent.core.trace import AgentTrace
from agent.core.types import Message


class _ScriptedClient:
    """脚本化 LLM client：按队列返回预设 content（异步 chat 契约）。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[list[dict[str, Any]]] = []

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(messages)
        return {"content": self._outputs.pop(0), "tool_calls": None}


class _FailingClient:
    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")


def _user_messages(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


def _trace_with_tool_event() -> AgentTrace:
    from agent.core.trace import TraceEvent, TraceStep

    return AgentTrace(
        steps=[
            TraceStep(
                step_index=0,
                events=[
                    TraceEvent(
                        event_type="tool_execution",
                        timestamp=datetime.now(timezone.utc),
                        payload={},
                    )
                ],
            )
        ]
    )


class TestPrefilter:
    """预过滤规则（成本护栏）。"""

    async def test_no_user_message_skips_all(self) -> None:
        """无 user 消息时不发起 LLM 调用。"""
        client = _ScriptedClient(['{"facts": [], "task_summary": null}'])
        extractor = LLMMemoryExtractor(client)
        entries = await extractor.extract(
            AgentTrace(), AgentState(), {"messages": [Message(role="assistant", content="hi")]}
        )
        assert entries == []
        assert client.calls == []

    async def test_short_user_text_skips_facts(self) -> None:
        """user 输入过短（纯触发语）跳过事实，但有工具事件时仍可提取摘要。"""
        client = _ScriptedClient(['{"facts": [{"content": "x"}], "task_summary": "跑了测试"}'])
        extractor = LLMMemoryExtractor(client)
        entries = await extractor.extract(
            _trace_with_tool_event(),
            AgentState(),
            {"messages": _user_messages("继续")},
        )
        assert [e.category for e in entries] == [MemoryCategory.TASK_SUMMARIES]

    async def test_no_tool_events_skips_summary(self) -> None:
        """无工具事件（纯对话）跳过任务摘要、保留事实提取。"""
        client = _ScriptedClient(
            ['{"facts": [{"content": "代号是蓝鲸计划", "tags": ["代号"]}], "task_summary": "x"}']
        )
        extractor = LLMMemoryExtractor(client)
        entries = await extractor.extract(
            AgentTrace(),
            AgentState(),
            {"messages": _user_messages("请记住：项目代号是蓝鲸计划，很重要。")},
        )
        assert [e.category for e in entries] == [MemoryCategory.PREFERENCES]


class TestExtraction:
    """提取与条目构造。"""

    async def test_facts_and_summary_become_entries(self) -> None:
        """LLM JSON 输出应映射为 PREFERENCES / TASK_SUMMARIES 条目。"""
        client = _ScriptedClient(
            [
                '{"facts": [{"content": "阈值是 42.7", "tags": ["告警"]}],'
                ' "task_summary": "完成阈值配置"}'
            ]
        )
        extractor = LLMMemoryExtractor(client)
        entries = await extractor.extract(
            _trace_with_tool_event(),
            AgentState(),
            {"messages": _user_messages("请记住：告警阈值是 42.7。")},
        )
        categories = sorted(e.category.value for e in entries)
        assert categories == ["preferences", "task_summaries"]
        pref = next(e for e in entries if e.category == MemoryCategory.PREFERENCES)
        assert pref.content["fact"] == "阈值是 42.7"
        assert "告警" in pref.tags
        assert "llm-extract" in pref.tags

    async def test_parse_tolerates_markdown_and_noise(self) -> None:
        """容错解析：Markdown 代码块包裹与杂文本。"""
        client = _ScriptedClient(
            [
                '好的，提取结果如下：\n```json\n'
                '{"facts": [{"content": "端口 9187"}], "task_summary": null}\n```'
            ]
        )
        extractor = LLMMemoryExtractor(client)
        entries = await extractor.extract(
            AgentTrace(),
            AgentState(),
            {"messages": _user_messages("请记住：服务端口是 9187。")},
        )
        assert len(entries) == 1
        assert entries[0].content["fact"] == "端口 9187"

    async def test_parse_garbage_returns_empty(self) -> None:
        """非 JSON 输出应解析为空，不抛异常。"""
        facts, summary = LLMMemoryExtractor._parse_output("完全不是 JSON")
        assert facts == [] and summary is None

    async def test_llm_failure_degrades_to_empty(self) -> None:
        """LLM 异常应降级为空列表（不中断主流程）。"""
        extractor = LLMMemoryExtractor(_FailingClient())
        entries = await extractor.extract(
            AgentTrace(),
            AgentState(),
            {"messages": _user_messages("请记住：项目代号是蓝鲸计划，很重要。")},
        )
        assert entries == []


def _make_manager(tmp_path: Path, **overrides: Any) -> MemoryManager:
    config = MemoryConfig(enabled=True, **overrides)
    return MemoryManager(
        store=StructuredMemoryStore(tmp_path),
        extractor=RuleMemoryExtractor(),
        config=config,
    )


def _preference_entry(fact: str) -> MemoryEntry:
    return MemoryEntry(
        entry_id=f"test-{abs(hash(fact)) % 100000}",
        category=MemoryCategory.PREFERENCES,
        content={"fact": fact},
        summary=fact,
        tags=["test"],
    )


class TestPreferenceDedup:
    """PREFERENCES 内容规范化去重（去重第二层）。"""

    def test_duplicate_fact_refreshes_instead_of_adding(self, tmp_path: Path) -> None:
        """规范化后相同的事实应刷新旧条目而非新增。"""
        manager = _make_manager(tmp_path)
        manager._save_entry(_preference_entry("告警阈值是 42.7"))
        manager._save_entry(_preference_entry(" 告警阈值是42.7。"))
        entries = manager._store.list_entries(MemoryCategory.PREFERENCES)
        assert len(entries) == 1

    def test_different_facts_both_saved(self, tmp_path: Path) -> None:
        """不同事实应分别保存。"""
        manager = _make_manager(tmp_path)
        manager._save_entry(_preference_entry("告警阈值是 42.7"))
        manager._save_entry(_preference_entry("负责人是林晚"))
        entries = manager._store.list_entries(MemoryCategory.PREFERENCES)
        assert len(entries) == 2


class TestCleanup:
    """max_age_days 定时清理。"""

    def test_none_max_age_never_cleans(self, tmp_path: Path) -> None:
        """max_age_days 为 None（默认）时不清理。"""
        manager = _make_manager(tmp_path)
        manager._save_entry(_preference_entry("告警阈值是 42.7"))
        assert manager.cleanup() == 0
        assert len(manager._store.list_entries(MemoryCategory.PREFERENCES)) == 1

    def test_old_entries_cleaned(self, tmp_path: Path) -> None:
        """超过 max_age_days 的条目应被删除。"""
        manager = _make_manager(tmp_path, max_age_days=30)
        manager._save_entry(_preference_entry("告警阈值是 42.7"))
        store = manager._store
        entry = store.list_entries(MemoryCategory.PREFERENCES)[0]
        # 直接把落盘文件的时间戳改老（模拟 60 天前写入）
        old = entry.updated_at - timedelta(days=60)
        file_path = tmp_path / "preferences" / f"{entry.entry_id}.jsonl"
        data = json.loads(file_path.read_text(encoding="utf-8"))
        data["updated_at"] = old.isoformat()
        file_path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")

        assert manager.cleanup() == 1
        assert store.list_entries(MemoryCategory.PREFERENCES) == []
