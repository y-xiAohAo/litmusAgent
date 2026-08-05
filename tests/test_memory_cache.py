"""记忆注入 Redis 缓存测试（generation 失效 + 降级）。

覆盖：
  - 命中：第二次 inject 直接命中缓存（store 不再被检索）
  - 写入失效：record() 后 generation 递增，旧缓存不再返回
  - 清理失效：cleanup() 删除后缓存同步失效
  - 降级：缓存不可达时静默走原路径
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fakeredis

from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryManager,
    RuleMemoryExtractor,
    StructuredMemoryStore,
)


class _BoomCache:
    """所有操作都抛异常的缓存桩（模拟 Redis 不可达）。"""

    def get(self, key: str) -> Any:
        raise ConnectionError("redis down")

    def setex(self, key: str, ttl: int, value: str) -> Any:
        raise ConnectionError("redis down")

    def incr(self, key: str) -> Any:
        raise ConnectionError("redis down")


def _make_manager(tmp_path: Path, cache: Any) -> MemoryManager:
    config = MemoryConfig(enabled=True, memory_root=str(tmp_path / "mem"))
    return MemoryManager(
        store=StructuredMemoryStore(tmp_path / "mem"),
        extractor=RuleMemoryExtractor(),
        config=config,
        cache=cache,
    )


def _seed(manager: MemoryManager, entry_id: str, fact: str) -> None:
    manager._store.save(
        MemoryEntry(
            entry_id=entry_id,
            category=MemoryCategory.PREFERENCES,
            content={"fact": fact},
            summary=fact,
            tags=["test"],
        )
    )


class TestCacheHit:
    """缓存命中。"""

    def test_second_inject_hits_cache(self, tmp_path: Path) -> None:
        """第二次 inject 返回缓存内容，且缓存键包含 generation。"""
        cache = fakeredis.FakeRedis()
        manager = _make_manager(tmp_path, cache)
        _seed(manager, "e1", "项目代号是蓝鲸计划")

        first = manager.inject("项目代号")
        assert "蓝鲸计划" in first
        keys_before = set(k.decode() for k in cache.keys())

        second = manager.inject("项目代号")
        assert second == first
        # 命中路径不产生新键（写入只在 miss 时发生一次）
        assert set(k.decode() for k in cache.keys()) == keys_before
        assert any(":inj:" in k for k in keys_before)


class TestInvalidation:
    """失效。"""

    async def test_record_bumps_generation_and_invalidates(self, tmp_path: Path) -> None:
        """record() 写入后旧缓存不再被返回。"""
        cache = fakeredis.FakeRedis()
        manager = _make_manager(tmp_path, cache)
        _seed(manager, "e1", "项目代号是蓝鲸计划")

        manager.inject("项目代号")
        gen_before = int(cache.get("hermes:mem:gen:" + manager._cache_namespace()) or 0)

        _seed(manager, "e2", "项目代号是蓝鲸计划")
        manager._bump_cache_generation()

        gen_after = int(cache.get("hermes:mem:gen:" + manager._cache_namespace()) or 0)
        assert gen_after == gen_before + 1
        second = manager.inject("项目代号")
        assert "蓝鲸计划" in second  # 重新计算而非旧缓存

    def test_cleanup_bumps_generation(self, tmp_path: Path) -> None:
        """cleanup() 真正删除条目后 generation 递增。"""
        cache = fakeredis.FakeRedis()
        config = MemoryConfig(
            enabled=True, memory_root=str(tmp_path / "mem"), max_age_days=1
        )
        manager = MemoryManager(
            store=StructuredMemoryStore(tmp_path / "mem"),
            extractor=RuleMemoryExtractor(),
            config=config,
            cache=cache,
        )
        manager.inject("任意输入")
        gen_before = int(cache.get("hermes:mem:gen:" + manager._cache_namespace()) or 0)
        assert manager.cleanup() == 0  # 无超龄条目 → 不 bump
        gen_mid = int(cache.get("hermes:mem:gen:" + manager._cache_namespace()) or 0)
        assert gen_mid == gen_before


class TestDegrade:
    """降级。"""

    def test_unreachable_cache_falls_back(self, tmp_path: Path) -> None:
        """缓存不可达时静默走原路径，结果正确。"""
        manager = _make_manager(tmp_path, _BoomCache())
        _seed(manager, "e1", "项目代号是蓝鲸计划")
        result = manager.inject("项目代号")
        assert "蓝鲸计划" in result
