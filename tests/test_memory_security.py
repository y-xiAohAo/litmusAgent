"""记忆读写安全策略测试。"""

from __future__ import annotations

from typing import Any

import pytest

from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryExtractor,
    MemoryManager,
    StructuredMemoryStore,
)
from agent.core.security import PolicyAction, PolicyEngine, PolicyRule
from agent.core.state import AgentState
from agent.core.trace import AgentTrace
from agent.tools.memory_read import memory_read


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


class TestMemoryManagerWritePolicy:
    """验证 record() 中的 memory/category 写策略。"""

    def test_record_skips_denied_category(self, tmp_path: Any) -> None:
        """写策略拒绝的 category 不应被保存。"""
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="memory/category",
                    operation="write",
                    pattern="artifacts",
                    action=PolicyAction.DENY,
                    reason="禁止写入 artifacts",
                    use_regex=False,
                ),
            ],
        )
        store = StructuredMemoryStore(tmp_path)
        entries = [
            MemoryEntry(
                entry_id="env1",
                category=MemoryCategory.ENVIRONMENT,
                content={},
                summary="env",
                tags=[],
            ),
            MemoryEntry(
                entry_id="art1",
                category=MemoryCategory.ARTIFACTS,
                content={},
                summary="artifact",
                tags=[],
            ),
        ]
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor(entries),
            config=_enabled_config(),
            policy=policy,
        )
        saved = manager.record(AgentTrace(), AgentState())

        assert len(saved) == 1
        assert saved[0].entry_id == "env1"
        assert store.get("env1") is not None
        assert store.get("art1") is None

    def test_record_allows_all_when_no_policy(self, tmp_path: Any) -> None:
        """未注入策略时，record 保持原有行为。"""
        store = StructuredMemoryStore(tmp_path)
        entries = [
            MemoryEntry(
                entry_id="env1",
                category=MemoryCategory.ENVIRONMENT,
                content={},
                summary="env",
                tags=[],
            ),
            MemoryEntry(
                entry_id="art1",
                category=MemoryCategory.ARTIFACTS,
                content={},
                summary="artifact",
                tags=[],
            ),
        ]
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor(entries),
            config=_enabled_config(),
        )
        saved = manager.record(AgentTrace(), AgentState())

        assert len(saved) == 2
        assert store.get("env1") is not None
        assert store.get("art1") is not None


class TestMemoryManagerReadPolicy:
    """验证 inject() / read() 中的 memory/category 读策略。"""

    def test_inject_filters_denied_category(self, tmp_path: Any) -> None:
        """读策略拒绝的 category 不应出现在注入片段中。"""
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="memory/category",
                    operation="read",
                    pattern="failure_patterns",
                    action=PolicyAction.DENY,
                    reason="禁止注入失败模式",
                    use_regex=False,
                ),
            ],
        )
        store = StructuredMemoryStore(tmp_path)
        store.save(
            MemoryEntry(
                entry_id="env1",
                category=MemoryCategory.ENVIRONMENT,
                content={},
                summary="pandas env",
                tags=["pandas"],
            )
        )
        store.save(
            MemoryEntry(
                entry_id="fail1",
                category=MemoryCategory.FAILURE_PATTERNS,
                content={},
                summary="pandas failure",
                tags=["pandas"],
            )
        )
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor([]),
            config=_enabled_config(),
            policy=policy,
        )
        fragment = manager.inject("pandas")

        assert "pandas env" in fragment
        assert "pandas failure" not in fragment

    def test_read_denies_unauthorized_category(self, tmp_path: Any) -> None:
        """读策略拒绝的 category 通过 read() 返回 None。"""
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="memory/category",
                    operation="read",
                    pattern="preferences",
                    action=PolicyAction.DENY,
                    reason="禁止读取偏好",
                    use_regex=False,
                ),
            ],
        )
        store = StructuredMemoryStore(tmp_path)
        entry = MemoryEntry(
            entry_id="pref1",
            category=MemoryCategory.PREFERENCES,
            content={"key": "theme", "value": "dark"},
            summary="theme preference",
            tags=["preference"],
        )
        store.save(entry)
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor([]),
            config=_enabled_config(),
            policy=policy,
        )

        assert manager.read(entry.uri) is None

    def test_read_allows_authorized_category(self, tmp_path: Any) -> None:
        """读策略允许的 category 可正常读取。"""
        store = StructuredMemoryStore(tmp_path)
        entry = MemoryEntry(
            entry_id="env1",
            category=MemoryCategory.ENVIRONMENT,
            content={"packages": [{"name": "pandas"}]},
            summary="pandas env",
            tags=["pandas"],
        )
        store.save(entry)
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor([]),
            config=_enabled_config(),
            policy=PolicyEngine.default(),
        )

        content = manager.read(entry.uri)
        assert content is not None
        assert '"category": "environment"' in content

    def test_check_read_policy_returns_decision(self, tmp_path: Any) -> None:
        """check_read_policy 应返回拒绝决策及原因。"""
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="memory/category",
                    operation="read",
                    pattern="preferences",
                    action=PolicyAction.DENY,
                    reason="禁止读取偏好",
                    use_regex=False,
                ),
            ],
        )
        store = StructuredMemoryStore(tmp_path)
        entry = MemoryEntry(
            entry_id="pref1",
            category=MemoryCategory.PREFERENCES,
            content={"key": "theme", "value": "dark"},
            summary="theme preference",
            tags=["preference"],
        )
        store.save(entry)
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor([]),
            config=_enabled_config(),
            policy=policy,
        )

        decision = manager.check_read_policy(entry.uri)
        assert decision is not None
        assert decision.action == PolicyAction.DENY
        assert "禁止读取偏好" in decision.reason

    def test_check_read_policy_invalid_uri_returns_none(
        self, tmp_path: Any
    ) -> None:
        """非法 URI 无法解析 category，应返回 None。"""
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="memory/category",
                    operation="read",
                    pattern=".*",
                    action=PolicyAction.DENY,
                    reason="全部禁止",
                ),
            ],
        )
        manager = MemoryManager(
            store=StructuredMemoryStore(tmp_path),
            extractor=_FakeExtractor([]),
            config=_enabled_config(),
            policy=policy,
        )

        assert manager.check_read_policy("invalid-uri") is None


class TestMemoryReadTool:
    """验证 memory_read 工具能把策略拒绝原因返回给 LLM。"""

    @pytest.mark.asyncio
    async def test_memory_read_tool_returns_policy_reason(
        self, tmp_path: Any
    ) -> None:
        """读策略拒绝时，工具返回的 content 应包含策略原因。"""
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="memory/category",
                    operation="read",
                    pattern="preferences",
                    action=PolicyAction.DENY,
                    reason="禁止读取偏好",
                    use_regex=False,
                ),
            ],
        )
        store = StructuredMemoryStore(tmp_path)
        entry = MemoryEntry(
            entry_id="pref1",
            category=MemoryCategory.PREFERENCES,
            content={"key": "theme", "value": "dark"},
            summary="theme preference",
            tags=["preference"],
        )
        store.save(entry)
        manager = MemoryManager(
            store=store,
            extractor=_FakeExtractor([]),
            config=_enabled_config(),
            policy=policy,
        )

        result = await memory_read(entry.uri, manager)
        assert result.success is False
        assert "策略拒绝" in result.content
        assert "禁止读取偏好" in result.content
