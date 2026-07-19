"""记忆管理 CLI。

纯 argparse 实现，无外部依赖。支持列出、查看、删除、反馈、审计、导出记忆。

设计约束：
  - 不引入新依赖（仅用标准库 + 项目已有 yaml/pydantic）。
  - 不修改 engine.py 或现有 Tool 签名。
  - list/show/delete/export 直接操作 MemoryStore，即使 MemoryConfig.enabled=False 也可用；
    feedback/audit 通过 MemoryManager 执行，受其 enabled 检查约束。
  - 敏感信息默认过滤，与 Agent 保存时的过滤规则保持一致。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.config import MemoryConfig, load_config
from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    MemoryManager,
    MemoryStore,
    StructuredMemoryStore,
    _filter_sensitive_data,
    _filter_sensitive_value,
)

PROG = "hermes-memory"


def build_parser() -> argparse.ArgumentParser:
    """构造 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="管理 Litmus 长期记忆（JSONL 文件目录）。",
    )
    parser.add_argument(
        "--config",
        help="YAML 配置文件路径；不提供则使用默认 MemoryConfig()",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出记忆条目")
    list_parser.add_argument(
        "--category",
        choices=[c.value for c in MemoryCategory],
        help="按类别过滤",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="最多显示条数（默认 50）",
    )

    show_parser = subparsers.add_parser("show", help="显示单条记忆 JSON")
    show_parser.add_argument("entry_id", help="记忆条目 ID")
    show_parser.add_argument(
        "--raw",
        action="store_true",
        help="不过滤敏感信息（谨慎使用）",
    )

    delete_parser = subparsers.add_parser("delete", help="删除记忆条目")
    delete_parser.add_argument("entry_id", help="记忆条目 ID")

    feedback_parser = subparsers.add_parser("feedback", help="给记忆条目打分")
    feedback_parser.add_argument("entry_id", help="记忆条目 ID")
    feedback_parser.add_argument(
        "--score",
        type=int,
        required=True,
        choices=[-1, 0, 1],
        help="反馈分数：-1 踩 / 0 中性 / 1 赞",
    )

    audit_parser = subparsers.add_parser("audit", help="审计记忆冲突与陈旧条目")
    audit_parser.add_argument(
        "--category",
        choices=[c.value for c in MemoryCategory],
        help="按类别审计",
    )

    export_parser = subparsers.add_parser("export", help="导出 Markdown memory-bank")
    export_parser.add_argument(
        "--output-dir",
        default=".hermes/memory-bank",
        help="输出目录（默认 .hermes/memory-bank）",
    )

    return parser


def _load_config(args: argparse.Namespace) -> MemoryConfig:
    """根据 --config 加载 MemoryConfig，否则返回默认值。"""
    if args.config:
        return load_config(args.config).agent.memory
    return MemoryConfig()


def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    """把 MemoryEntry 转为可 JSON 序列化的字典。"""
    data = dataclasses.asdict(entry)
    data["category"] = entry.category.value
    data["created_at"] = entry.created_at.isoformat()
    data["updated_at"] = entry.updated_at.isoformat()
    if entry.last_feedback_at is not None:
        data["last_feedback_at"] = entry.last_feedback_at.isoformat()
    return data


def _apply_filter(entry: MemoryEntry, patterns: list[str]) -> MemoryEntry:
    """对 entry 做敏感信息过滤，返回新对象。"""
    return MemoryEntry(
        entry_id=entry.entry_id,
        category=entry.category,
        content=_filter_sensitive_data(entry.content, patterns),
        summary=_filter_sensitive_value(entry.summary, patterns),
        tags=[_filter_sensitive_value(tag, patterns) for tag in entry.tags],
        source_trace_id=entry.source_trace_id,
        source_run_id=entry.source_run_id,
        uri=entry.uri,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        confidence=entry.confidence,
        feedback_score=entry.feedback_score,
        feedback_count=entry.feedback_count,
        last_feedback_at=entry.last_feedback_at,
        stale=entry.stale,
        linked_entry_ids=list(entry.linked_entry_ids),
    )


def _format_datetime(dt: datetime) -> str:
    """统一时间格式化。"""
    return dt.isoformat()


def cmd_list(store: MemoryStore, args: argparse.Namespace) -> int:
    """执行 list 子命令。"""
    category: MemoryCategory | None = None
    if args.category:
        category = MemoryCategory(args.category)

    entries = store.list_entries(category=category)
    entries.sort(key=lambda e: e.updated_at, reverse=True)
    entries = entries[: args.limit]

    if not entries:
        print("未找到记忆条目。")
        return 0

    print(f"{'entry_id':<20} {'category':<18} {'stale':<6} {'summary'}")
    print("-" * 80)
    for entry in entries:
        stale_flag = "yes" if entry.stale else "no"
        summary = entry.summary
        if len(summary) > 40:
            summary = summary[:37] + "..."
        print(
            f"{entry.entry_id:<20} "
            f"{entry.category.value:<18} "
            f"{stale_flag:<6} "
            f"{summary}"
        )
    return 0


def cmd_show(store: MemoryStore, config: MemoryConfig, args: argparse.Namespace) -> int:
    """执行 show 子命令。"""
    entry = store.get(args.entry_id)
    if entry is None:
        print(f"条目不存在：{args.entry_id}", file=sys.stderr)
        return 1

    if not args.raw and config.filter_sensitive:
        entry = _apply_filter(entry, config.sensitive_patterns)

    print(json.dumps(_entry_to_dict(entry), ensure_ascii=False, indent=2))
    return 0


def cmd_delete(store: MemoryStore, args: argparse.Namespace) -> int:
    """执行 delete 子命令。"""
    if store.delete(args.entry_id):
        print(f"已删除：{args.entry_id}")
        return 0
    print(f"条目不存在：{args.entry_id}", file=sys.stderr)
    return 1


def cmd_feedback(manager: MemoryManager, args: argparse.Namespace) -> int:
    """执行 feedback 子命令。"""
    if manager.record_feedback(args.entry_id, args.score):
        print(f"已记录反馈：{args.entry_id} → {args.score}")
        return 0
    print(f"反馈失败：{args.entry_id}", file=sys.stderr)
    return 1


def cmd_audit(manager: MemoryManager, args: argparse.Namespace) -> int:
    """执行 audit 子命令。"""
    category: MemoryCategory | None = None
    if args.category:
        category = MemoryCategory(args.category)

    stale_marked, conflicts = manager.audit(category=category)

    print(f"标灰陈旧条目：{len(stale_marked)} 条")
    for entry in stale_marked:
        print(f"  - {entry.entry_id} ({entry.category.value})")

    print(f"检测到冲突：{len(conflicts)} 条")
    for conflict in conflicts:
        print(f"  - [{conflict.conflict_type}] {conflict.reason}")
        print(f"    entries: {', '.join(conflict.entry_ids)}")
        print(f"    action:  {conflict.suggested_action}")

    return 0


def cmd_export(
    store: MemoryStore, config: MemoryConfig, args: argparse.Namespace
) -> int:
    """执行 export 子命令，按 category 导出 Markdown。"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = store.list_entries()
    by_category: dict[MemoryCategory, list[MemoryEntry]] = {}
    for entry in entries:
        by_category.setdefault(entry.category, []).append(entry)

    if not by_category:
        print("没有可导出的记忆条目。")
        return 0

    for category, cat_entries in by_category.items():
        cat_entries.sort(key=lambda e: e.updated_at, reverse=True)
        md_path = output_dir / f"{category.value}.md"
        lines = [f"# Memory Bank: {category.value}", ""]

        for entry in cat_entries:
            content = entry.content
            summary = entry.summary
            tags = entry.tags
            if config.filter_sensitive:
                content = _filter_sensitive_data(content, config.sensitive_patterns)
                summary = _filter_sensitive_value(summary, config.sensitive_patterns)
                tags = [
                    _filter_sensitive_value(tag, config.sensitive_patterns)
                    for tag in tags
                ]

            lines.append(f"## {entry.entry_id}")
            lines.append(f"- **summary**: {summary}")
            lines.append(f"- **tags**: {', '.join(tags) if tags else 'none'}")
            lines.append(f"- **confidence**: {entry.confidence}")
            lines.append(f"- **stale**: {'yes' if entry.stale else 'no'}")
            lines.append(
                f"- **feedback**: {entry.feedback_score} "
                f"(count: {entry.feedback_count})"
            )
            lines.append(f"- **updated_at**: {_format_datetime(entry.updated_at)}")
            lines.append("- **content**:")
            lines.append("```json")
            lines.append(json.dumps(content, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

        md_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"已导出：{md_path}")

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    Args:
        argv: 命令行参数列表；None 时使用 sys.argv。

    Returns:
        退出码：0 成功，1 业务错误，2 参数错误（argparse 自动处理）。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _load_config(args)
    store = StructuredMemoryStore(Path(config.memory_root))

    try:
        if args.command == "list":
            return cmd_list(store, args)
        if args.command == "show":
            return cmd_show(store, config, args)
        if args.command == "delete":
            return cmd_delete(store, args)
        if args.command == "export":
            return cmd_export(store, config, args)

        # feedback / audit 需要 MemoryManager。
        # 用户显式调用 CLI，即使配置中 enabled=False 也应允许管理操作。
        from agent.core.memory import RuleMemoryExtractor

        if not config.enabled:
            config = config.model_copy(update={"enabled": True})
        extractor = RuleMemoryExtractor()
        manager = MemoryManager(
            store=store,
            extractor=extractor,
            config=config,
        )
        if args.command == "feedback":
            return cmd_feedback(manager, args)
        if args.command == "audit":
            return cmd_audit(manager, args)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
