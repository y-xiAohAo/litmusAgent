"""记忆 CLI 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.cli.memory_cli import (
    build_parser,
    cmd_audit,
    cmd_delete,
    cmd_export,
    cmd_feedback,
    cmd_list,
    cmd_show,
)
from agent.config import MemoryConfig
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryManager,
    RuleMemoryExtractor,
    StructuredMemoryStore,
)


def _enabled_config(tmp_path: Path, **overrides: Any) -> MemoryConfig:
    """构造启用状态的 MemoryConfig，memory_root 指向测试目录。"""
    defaults: dict[str, Any] = {
        "enabled": True,
        "memory_root": str(tmp_path),
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


def _store_with_entries(tmp_path: Path) -> StructuredMemoryStore:
    """构造包含两条测试记忆的 store。"""
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="e1",
            category=MemoryCategory.ENVIRONMENT,
            content={"packages": [{"name": "pandas"}]},
            summary="pandas env",
            tags=["pandas"],
        )
    )
    store.save(
        MemoryEntry(
            entry_id="e2",
            category=MemoryCategory.ARTIFACTS,
            content={"path": "/workspace/report.md"},
            summary="report artifact",
            tags=["report"],
        )
    )
    return store


def _manager(store: StructuredMemoryStore, config: MemoryConfig | None = None) -> MemoryManager:
    """构造用于 CLI 测试的 MemoryManager。"""
    return MemoryManager(
        store=store,
        extractor=RuleMemoryExtractor(),
        config=config or _enabled_config(store._root),
    )


# ---------------------------------------------------------------------------
# 参数解析测试
# ---------------------------------------------------------------------------


def test_parser_list() -> None:
    parser = build_parser()
    args = parser.parse_args(["list", "--category", "environment", "--limit", "10"])
    assert args.command == "list"
    assert args.category == "environment"
    assert args.limit == 10


def test_parser_show() -> None:
    parser = build_parser()
    args = parser.parse_args(["show", "e1", "--raw"])
    assert args.command == "show"
    assert args.entry_id == "e1"
    assert args.raw is True


def test_parser_delete() -> None:
    parser = build_parser()
    args = parser.parse_args(["delete", "e1"])
    assert args.command == "delete"
    assert args.entry_id == "e1"


def test_parser_feedback() -> None:
    parser = build_parser()
    args = parser.parse_args(["feedback", "e1", "--score", "1"])
    assert args.command == "feedback"
    assert args.entry_id == "e1"
    assert args.score == 1


def test_parser_audit() -> None:
    parser = build_parser()
    args = parser.parse_args(["audit", "--category", "environment"])
    assert args.command == "audit"
    assert args.category == "environment"


def test_parser_export() -> None:
    parser = build_parser()
    args = parser.parse_args(["export", "--output-dir", ".hermes/bank"])
    assert args.command == "export"
    assert args.output_dir == ".hermes/bank"


# ---------------------------------------------------------------------------
# 命令执行测试
# ---------------------------------------------------------------------------


def test_cmd_list(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = _store_with_entries(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert cmd_list(store, args) == 0
    captured = capsys.readouterr()
    assert "e1" in captured.out
    assert "e2" in captured.out
    assert "pandas env" in captured.out
    assert "environment" in captured.out
    assert "artifacts" in captured.out


def test_cmd_list_category_filter(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = _store_with_entries(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["list", "--category", "environment"])
    assert cmd_list(store, args) == 0
    captured = capsys.readouterr()
    assert "e1" in captured.out
    assert "e2" not in captured.out


def test_cmd_show(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = _store_with_entries(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["show", "e1"])
    assert cmd_show(store, MemoryConfig(memory_root=str(tmp_path)), args) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["entry_id"] == "e1"
    assert data["category"] == "environment"


def test_cmd_show_filters_sensitive_by_default(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="secret",
            category=MemoryCategory.ENVIRONMENT,
            content={"api_key": "sk-12345"},
            summary="key summary",
            tags=["api_key"],
        )
    )
    parser = build_parser()
    args = parser.parse_args(["show", "secret"])
    assert cmd_show(store, MemoryConfig(memory_root=str(tmp_path)), args) == 0
    captured = capsys.readouterr()
    assert "[REDACTED]" in captured.out
    assert "sk-12345" not in captured.out


def test_cmd_show_raw_shows_sensitive(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="secret",
            category=MemoryCategory.ENVIRONMENT,
            content={"api_key": "sk-12345"},
            summary="key summary",
            tags=["api_key"],
        )
    )
    parser = build_parser()
    args = parser.parse_args(["show", "secret", "--raw"])
    assert cmd_show(store, MemoryConfig(memory_root=str(tmp_path)), args) == 0
    captured = capsys.readouterr()
    assert "sk-12345" in captured.out


def test_cmd_show_missing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = StructuredMemoryStore(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["show", "missing"])
    assert cmd_show(store, MemoryConfig(memory_root=str(tmp_path)), args) == 1
    captured = capsys.readouterr()
    assert "不存在" in captured.err


def test_cmd_delete(tmp_path: Path) -> None:
    store = _store_with_entries(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["delete", "e1"])
    assert cmd_delete(store, args) == 0
    assert store.get("e1") is None
    assert store.get("e2") is not None


def test_cmd_delete_missing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = StructuredMemoryStore(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["delete", "missing"])
    assert cmd_delete(store, args) == 1
    captured = capsys.readouterr()
    assert "不存在" in captured.err


def test_cmd_feedback(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = _store_with_entries(tmp_path)
    manager = _manager(store)
    parser = build_parser()
    args = parser.parse_args(["feedback", "e1", "--score", "1"])
    assert cmd_feedback(manager, args) == 0
    captured = capsys.readouterr()
    assert "已记录反馈" in captured.out

    fetched = store.get("e1")
    assert fetched is not None
    assert fetched.feedback_score == 1


def test_cmd_feedback_missing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = StructuredMemoryStore(tmp_path)
    manager = _manager(store)
    parser = build_parser()
    args = parser.parse_args(["feedback", "missing", "--score", "-1"])
    assert cmd_feedback(manager, args) == 1
    captured = capsys.readouterr()
    assert "反馈失败" in captured.err


def test_cmd_audit(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="old_env",
            category=MemoryCategory.ENVIRONMENT,
            content={},
            summary="old env",
        )
    )
    # 让 environment 条目超过半衰期：直接写 JSONL 绕过 save 刷新 updated_at。
    from datetime import datetime, timedelta, timezone

    ten_days_ago = datetime.now(timezone.utc) - timedelta(days=10)
    env_dir = tmp_path / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "old_env.jsonl").write_text(
        f'{{"entry_id":"old_env","category":"environment","content":{{}},'
        f'"summary":"old env","tags":[],"uri":"",'
        f'"created_at":"{ten_days_ago.isoformat()}",'
        f'"updated_at":"{ten_days_ago.isoformat()}",'
        f'"confidence":1.0,"stale":false}}\n',
        encoding="utf-8",
    )

    manager = _manager(store)
    parser = build_parser()
    args = parser.parse_args(["audit"])
    assert cmd_audit(manager, args) == 0
    captured = capsys.readouterr()
    assert "old_env" in captured.out


def test_cmd_export(tmp_path: Path) -> None:
    store = _store_with_entries(tmp_path)
    parser = build_parser()
    output_dir = tmp_path / "bank"
    args = parser.parse_args(["export", "--output-dir", str(output_dir)])
    assert cmd_export(store, MemoryConfig(memory_root=str(tmp_path)), args) == 0
    assert (output_dir / "environment.md").exists()
    assert (output_dir / "artifacts.md").exists()
    env_md = (output_dir / "environment.md").read_text(encoding="utf-8")
    assert "pandas env" in env_md
    assert "e1" in env_md


def test_cmd_export_filters_sensitive(tmp_path: Path) -> None:
    store = StructuredMemoryStore(tmp_path)
    store.save(
        MemoryEntry(
            entry_id="secret",
            category=MemoryCategory.ENVIRONMENT,
            content={"api_key": "sk-12345"},
            summary="secret summary",
            tags=["secret"],
        )
    )
    parser = build_parser()
    output_dir = tmp_path / "bank"
    args = parser.parse_args(["export", "--output-dir", str(output_dir)])
    assert cmd_export(store, MemoryConfig(memory_root=str(tmp_path)), args) == 0
    env_md = (output_dir / "environment.md").read_text(encoding="utf-8")
    assert "[REDACTED]" in env_md
    assert "sk-12345" not in env_md


def test_cmd_export_empty(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    store = StructuredMemoryStore(tmp_path)
    parser = build_parser()
    output_dir = tmp_path / "bank"
    args = parser.parse_args(["export", "--output-dir", str(output_dir)])
    assert cmd_export(store, MemoryConfig(memory_root=str(tmp_path)), args) == 0
    captured = capsys.readouterr()
    assert "没有可导出" in captured.out
