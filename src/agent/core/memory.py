"""长期记忆子系统 —— 跨 session 持久化关键知识。

本模块是 Phase 8 长期记忆机制的基础设施，包含：
  - 记忆类别枚举 MemoryCategory
  - 记忆实体 MemoryEntry 与查询请求 MemoryQuery
  - 存储抽象 MemoryStore
  - 默认本地文件存储实现 StructuredMemoryStore

设计要点：
  1. 存储与业务逻辑解耦：MemoryStore 只负责持久化，不感知 Trace/State。
  2. 单实体 + category 区分：不复用多层级抽象，保持 MVP 简洁。
  3. 人类可读：默认存储为 JSONL，方便审计和手动修正。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from agent.config import MemoryConfig
from agent.core.security import PolicyAction, PolicyDecision, PolicyEngine
from agent.core.state import AgentState
from agent.core.trace import AgentTrace

_logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """长期记忆的类别枚举。

    每个类别对应一类不同的跨 session 知识，拥有各自的 content schema。
    """

    ENVIRONMENT = "environment"
    ARTIFACTS = "artifacts"
    FAILURE_PATTERNS = "failure_patterns"
    TASK_SUMMARIES = "task_summaries"
    PREFERENCES = "preferences"


@dataclass
class MemoryEntry:
    """单条长期记忆实体。

    Attributes:
        entry_id: 唯一标识，也是文件名的一部分。
        category: 记忆类别，决定 content 的 schema。
        content: 结构化数据，按 category 有不同 schema。
        summary: 一句话摘要，用于注入 LLM system prompt。
        tags: 检索关键词，通常由 RuleMemoryExtractor 自动生成。
        source_trace_id: 来源 Trace id，可选，用于审计。
        source_run_id: 来源 run id，可选。
        uri: 统一资源标识；为空时自动生成。
        created_at: 创建时间。
        updated_at: 更新时间。
        confidence: 可信度，规则提取默认 1.0，LLM 提取可低于 1.0。
    """

    entry_id: str
    category: MemoryCategory
    content: dict[str, Any]
    summary: str
    tags: list[str] = field(default_factory=list)
    source_trace_id: str | None = None
    source_run_id: str | None = None
    uri: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0

    # 8.4 新增：用户反馈与审计字段
    feedback_score: int | None = None
    feedback_count: int = 0
    last_feedback_at: datetime | None = None
    stale: bool = False
    linked_entry_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """若未提供 uri，按标准格式自动生成。"""
        if not self.uri:
            self.uri = f"hermes://memory/{self.category.value}/{self.entry_id}.jsonl"


@dataclass
class MemoryQuery:
    """长期记忆检索请求。

    Attributes:
        categories: 限定检索类别；None 表示不限制。
        tags: 至少匹配一个标签；None 表示不限制。
        text: 用户输入文本，用于与 summary/tags/content 做重叠打分。
        top_k: 最多返回条目数。
        time_range: 时间范围过滤；对 updated_at 生效。
    """

    categories: list[MemoryCategory] | None = None
    tags: list[str] | None = None
    text: str | None = None
    top_k: int = 5
    time_range: tuple[datetime, datetime] | None = None


class MemoryStore(ABC):
    """长期记忆存储抽象。

    实现类负责 MemoryEntry 的持久化、检索、删除和清理。
    本层不处理业务逻辑（如去重、合并、标签生成）。
    """

    @abstractmethod
    def save(self, entry: MemoryEntry) -> MemoryEntry:
        """保存或覆盖一条记忆。"""

    @abstractmethod
    def get(self, entry_id: str) -> MemoryEntry | None:
        """按 entry_id 读取单条记忆；不存在返回 None。"""

    @abstractmethod
    def query(self, query: MemoryQuery) -> list[MemoryEntry]:
        """按条件检索记忆并返回排序后的列表。"""

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """删除指定 entry_id 的记忆；成功返回 True。"""

    @abstractmethod
    def cleanup(self, max_age: timedelta | None = None) -> int:
        """清理过期记忆，返回删除数量。"""

    @abstractmethod
    def list_entries(
        self, category: MemoryCategory | None = None
    ) -> list[MemoryEntry]:
        """列出记忆条目；可指定类别。"""


class StructuredMemoryStore(MemoryStore):
    """基于本地 JSONL 文件的结构化存储实现。

    目录结构：
        <root_dir>/<category>/<entry_id>.jsonl

    每条记忆独立一个文件，内容为单行 JSON，便于人工查看和追加。
    """

    _ENTRY_ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, root_dir: Path | str) -> None:
        """初始化存储。

        Args:
            root_dir: 记忆文件根目录。
        """
        self._root = Path(root_dir)

    def save(self, entry: MemoryEntry) -> MemoryEntry:
        """保存或覆盖一条记忆。

        会自动生成 uri（若为空），并校验 entry_id 防止路径遍历。
        """
        self._validate_entry_id(entry.entry_id)
        if not entry.uri:
            entry.uri = f"hermes://memory/{entry.category.value}/{entry.entry_id}.jsonl"

        # 覆盖写入时刷新更新时间，使 cleanup / list_entries 排序符合直觉
        entry.updated_at = datetime.now(timezone.utc)

        category_dir = self._root / entry.category.value
        category_dir.mkdir(parents=True, exist_ok=True)

        file_path = category_dir / f"{entry.entry_id}.jsonl"
        file_path.write_text(
            self._entry_to_json(entry) + "\n",
            encoding="utf-8",
        )
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        """按 entry_id 读取单条记忆。

        会在所有 category 目录中查找匹配文件。
        """
        self._validate_entry_id(entry_id)
        for category in MemoryCategory:
            file_path = self._root / category.value / f"{entry_id}.jsonl"
            if file_path.exists():
                return self._entry_from_json(file_path.read_text(encoding="utf-8"))
        return None

    def query(self, query: MemoryQuery) -> list[MemoryEntry]:
        """按条件检索记忆。

        检索流程：
          1. 按 category 过滤
          2. 按 tags 过滤（至少匹配一个）
          3. 按 time_range 过滤（对 updated_at）
          4. 按 text 与 entry 的 summary/tags/content 做 token/字符重叠打分
          5. 按 (score, updated_at) 排序，返回 top_k
        """
        entries = self.list_entries()

        if query.categories:
            entries = [e for e in entries if e.category in query.categories]

        if query.tags:
            query_tag_set = set(query.tags)
            entries = [
                e for e in entries if query_tag_set.intersection(e.tags)
            ]

        if query.time_range is not None:
            start, end = query.time_range
            start = self._ensure_aware(start)
            end = self._ensure_aware(end)
            entries = [
                e for e in entries if start <= e.updated_at <= end
            ]

        text = query.text.strip() if query.text else ""
        if text:
            query_tokens = self._tokenize(text)
            scored: list[tuple[float, MemoryEntry]] = []
            for entry in entries:
                entry_text = self._entry_text(entry)
                entry_tokens = self._tokenize(entry_text)
                score = len(query_tokens.intersection(entry_tokens))
                if score > 0:
                    scored.append((score, entry))
            scored.sort(key=lambda item: (item[0], item[1].updated_at.timestamp()), reverse=True)
            entries = [entry for _, entry in scored]

        return entries[: query.top_k]

    def delete(self, entry_id: str) -> bool:
        """删除指定 entry_id 的记忆文件。"""
        self._validate_entry_id(entry_id)
        for category in MemoryCategory:
            file_path = self._root / category.value / f"{entry_id}.jsonl"
            if file_path.exists():
                file_path.unlink()
                return True
        return False

    def cleanup(self, max_age: timedelta | None = None) -> int:
        """清理超过 max_age 的记忆。

        Args:
            max_age: 最大年龄；为 None 时不清理。

        Returns:
            删除的文件数量。
        """
        if max_age is None:
            return 0

        cutoff = datetime.now(timezone.utc) - max_age
        removed = 0
        for category in MemoryCategory:
            category_dir = self._root / category.value
            if not category_dir.exists():
                continue
            for file_path in category_dir.glob("*.jsonl"):
                entry = self._entry_from_json(
                    file_path.read_text(encoding="utf-8")
                )
                if entry.updated_at < cutoff:
                    file_path.unlink()
                    removed += 1
        return removed

    def list_recent(self, limit: int) -> list[MemoryEntry]:
        """按 updated_at 降序返回最近 limit 条记忆（L0 兜底用）。"""
        return self.list_entries()[:limit]

    def list_entries(
        self, category: MemoryCategory | None = None
    ) -> list[MemoryEntry]:
        """列出记忆条目。

        Args:
            category: 指定类别；None 表示全部类别。

        Returns:
            按 updated_at 降序排列的条目列表。
        """
        categories = [category] if category else list(MemoryCategory)
        entries: list[MemoryEntry] = []
        for cat in categories:
            category_dir = self._root / cat.value
            if not category_dir.exists():
                continue
            for file_path in category_dir.glob("*.jsonl"):
                entries.append(
                    self._entry_from_json(file_path.read_text(encoding="utf-8"))
                )
        entries.sort(key=lambda e: e.updated_at.timestamp(), reverse=True)
        return entries

    def _validate_entry_id(self, entry_id: str) -> None:
        """校验 entry_id 只包含安全字符，防止路径遍历。"""
        if not self._ENTRY_ID_PATTERN.match(entry_id):
            raise ValueError(f"entry_id 包含非法字符：{entry_id}")

    def _entry_to_json(self, entry: MemoryEntry) -> str:
        """将 MemoryEntry 序列化为 JSON 字符串。"""
        data = asdict(entry)
        data["category"] = entry.category.value
        data["created_at"] = entry.created_at.isoformat()
        data["updated_at"] = entry.updated_at.isoformat()
        if entry.last_feedback_at is not None:
            data["last_feedback_at"] = entry.last_feedback_at.isoformat()
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    def _entry_from_json(self, raw: str) -> MemoryEntry:
        """从 JSON 字符串反序列化为 MemoryEntry。"""
        data = json.loads(raw.strip())
        self._validate_entry_id(data["entry_id"])
        data["category"] = MemoryCategory(data["category"])
        data["created_at"] = self._parse_datetime(data["created_at"])
        data["updated_at"] = self._parse_datetime(data["updated_at"])
        if data.get("last_feedback_at"):
            data["last_feedback_at"] = self._parse_datetime(data["last_feedback_at"])
        return MemoryEntry(**data)

    def _entry_text(self, entry: MemoryEntry) -> str:
        """把 entry 的 summary/tags/content 拼成可检索文本。"""
        parts = [entry.summary, " ".join(entry.tags)]
        parts.extend(self._flatten_values(entry.content))
        return " ".join(parts)

    def _flatten_values(self, obj: Any) -> list[str]:
        """把 dict/list 中的值展平为可检索字符串。"""
        result: list[str] = []
        if isinstance(obj, dict):
            for value in obj.values():
                result.extend(self._flatten_values(value))
        elif isinstance(obj, list):
            for item in obj:
                result.extend(self._flatten_values(item))
        elif isinstance(obj, str):
            result.append(obj)
        elif isinstance(obj, int | float | bool):
            result.append(str(obj))
        return result

    def _parse_datetime(self, raw_dt: str) -> datetime:
        """解析 ISO 格式时间，若缺少时区则按 UTC 处理。"""
        dt = datetime.fromisoformat(raw_dt)
        return self._ensure_aware(dt)

    def _ensure_aware(self, dt: datetime) -> datetime:
        """若 datetime 缺少时区，则假设为 UTC。"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _tokenize(self, text: str) -> set[str]:
        """简单分词：英文按单词，中文按单字，都转小写。"""
        lowered = text.lower()
        tokens: set[str] = set(re.findall(r"[a-z0-9]+", lowered))
        tokens.update(re.findall(r"[\u4e00-\u9fff]", lowered))
        return tokens


# ---------------------------------------------------------------------------
# 提取层：从 Trace/State 生成 MemoryEntry
# ---------------------------------------------------------------------------

class MemoryExtractor(ABC):
    """记忆提取器抽象。

    实现类从一次 Agent 运行的 Trace 与 State 中抽取值得长期保存的记忆条目。
    """

    @abstractmethod
    def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """提取记忆条目。"""


class RuleMemoryExtractor(MemoryExtractor):
    """基于规则的默认记忆提取器，不调用 LLM。

    覆盖场景：
      - environment：检测到 `pip install` 成功安装的包
      - artifacts：工具输出中的产物路径（/workspace/... 等）
      - failure_patterns：error_classification + reflection 事件组合
    """

    _PIP_INSTALL_RE: re.Pattern[str] = re.compile(r"\bpip(?:3)?\s+install\b")
    _WORKSPACE_PATH_RE: re.Pattern[str] = re.compile(
        r"(?:/workspace|/tmp|/home|/app|/data|/mnt)(?:/[A-Za-z0-9._-]+)+"
    )
    _GENERIC_FILE_RE: re.Pattern[str] = re.compile(
        r"/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.[A-Za-z0-9._-]+"
    )

    def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """从 Trace/State 中规则化提取记忆。"""
        trace_dict = trace.to_dict()
        entries: list[MemoryEntry] = []
        for step in trace_dict.get("steps", []):
            events = step.get("events", [])
            entries.extend(self._extract_environment(events, run_metadata))
            entries.extend(self._extract_artifacts(events, run_metadata))
            entries.extend(self._extract_failure_patterns(events, run_metadata))
        entries.extend(self._extract_artifacts_from_state(state, run_metadata))
        return entries

    def _extract_environment(
        self,
        events: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """提取环境状态：pip install 安装的包。"""
        entries: list[MemoryEntry] = []
        for event in events:
            if event.get("event_type") != "tool_execution":
                continue
            payload = event.get("payload", {})
            if not payload.get("success", False):
                continue
            if payload.get("tool") != "sandbox_exec":
                continue
            packages = self._extract_pip_packages(payload)
            if not packages:
                continue
            entries.append(
                self._build_entry(
                    category=MemoryCategory.ENVIRONMENT,
                    content={
                        "packages": [
                            {"name": name, "version": None} for name in packages
                        ],
                    },
                    summary=f"检测到已安装 Python 包：{', '.join(packages)}",
                    tags=["pip", "environment"] + packages,
                    run_metadata=run_metadata,
                )
            )
        return entries

    def _extract_artifacts(
        self,
        events: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """提取产物元数据：工具输出中的文件路径。"""
        entries: list[MemoryEntry] = []
        seen: set[str] = set()
        for event in events:
            if event.get("event_type") != "tool_execution":
                continue
            payload = event.get("payload", {})
            if not payload.get("success", False):
                continue
            text = f"{self._get_command(payload)}\n{payload.get('content', '')}"
            # 内容快照：file_write 写入的内容（截断 200 字），
            # 让“文件里写了什么”类问题可以通过记忆回答。
            preview = ""
            arguments = payload.get("arguments", {})
            if payload.get("tool") == "file_write":
                preview = str(arguments.get("content", ""))[:200]
            for path in self._extract_file_paths(text):
                if path in seen:
                    continue
                seen.add(path)
                entries.append(
                    self._build_artifact_entry(
                        path, run_metadata, content_preview=preview
                    )
                )
        return entries

    def _extract_artifacts_from_state(
        self,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """提取 State 中显式记录的产物。"""
        if state is None:
            return []
        entries: list[MemoryEntry] = []
        for name, metadata in (state.artifacts or {}).items():
            path = metadata.get("path") or name
            entries.append(
                self._build_entry(
                    category=MemoryCategory.ARTIFACTS,
                    content={
                        "path": path,
                        "type": metadata.get("type", self._guess_file_type(path)),
                        "description": metadata.get("description", ""),
                        "source_task": metadata.get("source_task", ""),
                    },
                    summary=f"State 记录产物：{path}",
                    tags=["artifact", self._guess_file_type(path)]
                    + [str(k) for k in metadata.keys()],
                    run_metadata=run_metadata,
                )
            )
        return entries

    def _extract_failure_patterns(
        self,
        events: list[dict[str, Any]],
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """提取失败模式：同一 step 内 error_classification + reflection 组合。"""
        entries: list[MemoryEntry] = []
        last_error: dict[str, Any] | None = None
        for event in events:
            etype = event.get("event_type")
            payload = event.get("payload", {})
            if etype == "error_classification":
                last_error = payload
                continue
            if etype == "reflection":
                exc_type = payload.get("exc_type", "UnknownError")
                tool_name = payload.get("tool_name", "unknown")
                signature = payload.get("signature")
                recovery = payload.get("action", "REWRITE_CODE")
                occurrences = payload.get("count", 1)
                hint = payload.get("hint", "")
                resolved = False
                if last_error and last_error.get("action") == recovery:
                    resolved = last_error.get("severity") not in {"FATAL"}
                summary = f"失败模式：{exc_type}（{tool_name}）"
                if hint:
                    summary += f" — {hint[:60]}"
                entries.append(
                    self._build_entry(
                        category=MemoryCategory.FAILURE_PATTERNS,
                        content={
                            "tool": tool_name,
                            "exc_type": exc_type,
                            "error_signature": signature,
                            "signature_detail": self._parse_signature_detail(
                                exc_type, signature
                            ),
                            "recovery": recovery,
                            "resolved": resolved,
                            "occurrences": occurrences,
                        },
                        summary=summary,
                        tags=["failure", exc_type, tool_name]
                        + ([signature] if signature else []),
                        run_metadata=run_metadata,
                    )
                )
                last_error = None
        return entries

    def _build_artifact_entry(
        self,
        path: str,
        run_metadata: dict[str, Any],
        content_preview: str = "",
    ) -> MemoryEntry:
        """构造一条 artifacts 记忆（可选携带内容快照）。"""
        file_type = self._guess_file_type(path)
        return self._build_entry(
            category=MemoryCategory.ARTIFACTS,
            content={
                "path": path,
                "type": file_type,
                "description": "",
                "source_task": "",
                "content_preview": content_preview,
            },
            summary=f"生成产物：{path}",
            tags=["artifact", file_type],
            run_metadata=run_metadata,
        )

    def _build_entry(
        self,
        category: MemoryCategory,
        content: dict[str, Any],
        summary: str,
        tags: list[str],
        run_metadata: dict[str, Any],
    ) -> MemoryEntry:
        """构造 MemoryEntry，自动分配 UUID 作为 entry_id。"""
        return MemoryEntry(
            entry_id=uuid.uuid4().hex,
            category=category,
            content=content,
            summary=summary,
            tags=tags,
            source_run_id=run_metadata.get("run_id"),
        )

    @classmethod
    def _get_command(cls, payload: dict[str, Any]) -> str:
        """从 tool_execution payload 中尽量获取命令字符串。"""
        arguments = payload.get("arguments") or {}
        command = arguments.get("command", "")
        return str(command)

    @classmethod
    def _parse_pip_packages(cls, command: str) -> list[str]:
        """解析 pip install 后面的包名列表。"""
        match = cls._PIP_INSTALL_RE.search(command)
        if not match:
            return []
        rest = command[match.end():]
        raw_tokens = rest.split()
        packages: list[str] = []
        for token in raw_tokens:
            token = token.strip("'\"\\,;")
            if not token or token.startswith("-") or token in {"pip", "install"}:
                continue
            # 去掉版本限定符，只保留包名
            name = re.split(r"[=<>!~@#]+", token)[0].strip()
            if name:
                packages.append(name)
        return packages

    @classmethod
    def _extract_pip_packages(cls, payload: dict[str, Any]) -> list[str]:
        """从 command/code/content 中提取 pip 安装的包名。

        当前覆盖两类输出：
          1. 命令/代码中显式包含 `pip install ...`。
          2. stdout 中出现 `Successfully installed pkg1 pkg2 ...`。
        对于 `Requirement already satisfied`、多行换行等复杂场景，MVP 暂不解析。
        """
        arguments = payload.get("arguments") or {}
        command = arguments.get("command", "")
        code = arguments.get("code", "")
        content = payload.get("content", "")

        # 优先从显式的 pip install 命令/代码中解析
        for text in (command, code):
            if text and cls._PIP_INSTALL_RE.search(text):
                packages = cls._parse_pip_packages(text)
                if packages:
                    return packages

        # 回退：从 stdout 中的 "Successfully installed ..." 解析
        return cls._parse_successfully_installed(content)

    @staticmethod
    def _parse_successfully_installed(content: str) -> list[str]:
        """从 pip 成功安装输出中提取包名。"""
        if not content:
            return []
        marker = "Successfully installed"
        for line in content.splitlines():
            idx = line.find(marker)
            if idx == -1:
                continue
            rest = line[idx + len(marker):]
            packages: list[str] = []
            for token in rest.split():
                token = token.strip("'\"\\,;")
                if not token or token.startswith("-"):
                    continue
                name = re.split(r"[=<>!~@#]+", token)[0].strip()
                if name:
                    packages.append(name)
            return packages
        return []

    @classmethod
    def _extract_file_paths(cls, text: str) -> set[str]:
        """从文本中识别潜在文件路径。"""
        paths: set[str] = set()
        for match in cls._WORKSPACE_PATH_RE.finditer(text):
            paths.add(cls._clean_path(match.group(0)))
        for match in cls._GENERIC_FILE_RE.finditer(text):
            paths.add(cls._clean_path(match.group(0)))
        return paths

    @staticmethod
    def _clean_path(path: str) -> str:
        """去除路径尾部常见标点。"""
        return path.rstrip(".,;:!?)]}\'\"")

    @staticmethod
    def _guess_file_type(path: str) -> str:
        """根据扩展名猜测文件类型。"""
        suffix = Path(path).suffix.lower().lstrip(".")
        mapping = {
            "py": "python",
            "md": "markdown",
            "txt": "text",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "csv": "csv",
            "png": "image",
            "jpg": "image",
            "jpeg": "image",
            "svg": "image",
            "html": "html",
            "pdf": "pdf",
        }
        return mapping.get(suffix, "file")

    @staticmethod
    def _parse_signature_detail(
        exc_type: str,
        signature: str | None,
    ) -> dict[str, Any]:
        """根据异常类型把签名解析为结构化 detail。"""
        if not signature:
            return {}
        detail_map = {
            "ModuleNotFoundError": ("missing_module", signature),
            "NameError": ("missing_variable", signature),
            "KeyError": ("missing_key", signature),
            "AttributeError": ("missing_attribute", signature),
            "SyntaxError": ("line_hint", signature),
        }
        key, value = detail_map.get(exc_type, ("first_line", signature))
        return {key: value}


# ---------------------------------------------------------------------------
# 注入层：把检索到的记忆格式化为 LLM 上下文片段
# ---------------------------------------------------------------------------

class MemoryInjector:
    """把 MemoryEntry 列表格式化为 system prompt 可追加的文本块。"""

    # 保守估算：1 token ≈ 3 个字符（中英混排）
    _CHARS_PER_TOKEN_APPROX: int = 3

    @classmethod
    def format(cls, entries: list[MemoryEntry], config: MemoryConfig) -> str:
        """按配置限制格式化记忆片段。

        Args:
            entries: 检索到的记忆条目。
            config: 记忆配置。

        Returns:
            可直接追加到 system prompt 的文本；无内容时返回空字符串。
        """
        if not entries:
            return ""

        max_entries = max(0, config.inject_max_entries)
        max_chars = max(0, config.inject_max_tokens) * cls._CHARS_PER_TOKEN_APPROX

        header = "[历史记忆]"
        lines: list[str] = [header]
        used_chars = len(header) + 1

        for entry in entries[:max_entries]:
            line = f"- [{entry.category.value}] {entry.summary}"
            # 内容快照：artifact 记忆携带 preview 时附上，
            # 让“文件里写了什么”类问题可以直接通过注入回答。
            preview = entry.content.get("content_preview") if entry.content else None
            if preview:
                line += f"（内容：{preview}）"
            if entry.tags:
                line += f" (tags: {', '.join(entry.tags)})"

            # 首条也超长时直接截断，避免完全无法注入
            if len(line) > max_chars and len(lines) == 1:
                line = line[:max_chars]

            if used_chars + len(line) + 1 > max_chars and len(lines) > 1:
                break

            lines.append(line)
            used_chars += len(line) + 1

        if len(lines) == 1:
            return ""
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 冲突检测层：发现同类记忆之间的矛盾
# ---------------------------------------------------------------------------

@dataclass
class MemoryConflict:
    """单条记忆冲突描述。

    Attributes:
        conflict_type: 冲突类型，如 version_mismatch / duplicate / contradiction。
        entry_ids: 涉及冲突的条目 id 列表。
        reason: 人类可读的原因说明。
        suggested_action: 建议操作，如 keep_latest / downgrade / manual_review。
    """

    conflict_type: str
    entry_ids: list[str]
    reason: str
    suggested_action: str


class MemoryConflictDetector:
    """基于规则检测记忆存储中的冲突。

    当前覆盖：
      - environment: 同名包多个版本
      - artifacts: 相同路径多条记录
      - preferences: 相同 key 不同 value
      - failure_patterns: 相同 (tool, exc_type) 不同 recovery
    """

    def detect(self, store: MemoryStore) -> list[MemoryConflict]:
        """扫描 store 中所有条目，返回冲突列表。"""
        entries = store.list_entries()
        conflicts: list[MemoryConflict] = []
        conflicts.extend(self._detect_environment_conflicts(entries))
        conflicts.extend(self._detect_artifact_conflicts(entries))
        conflicts.extend(self._detect_preference_conflicts(entries))
        conflicts.extend(self._detect_failure_pattern_conflicts(entries))
        return conflicts

    def _detect_environment_conflicts(
        self, entries: list[MemoryEntry]
    ) -> list[MemoryConflict]:
        """检测 environment 类别中同名包的不同版本。"""
        conflicts: list[MemoryConflict] = []
        packages: dict[str, list[tuple[str | None, MemoryEntry]]] = {}
        for entry in entries:
            if entry.category != MemoryCategory.ENVIRONMENT:
                continue
            for pkg in entry.content.get("packages", []):
                name = pkg.get("name")
                version = pkg.get("version")
                if not name:
                    continue
                packages.setdefault(name, []).append((version, entry))

        for name, versions in packages.items():
            seen_versions: set[str | None] = set()
            conflicting: list[MemoryEntry] = []
            for version, entry in versions:
                if version not in seen_versions:
                    seen_versions.add(version)
                    if len(seen_versions) > 1:
                        conflicting.append(entry)
            if len(seen_versions) > 1:
                conflicting.extend([e for v, e in versions if e not in conflicting])
                conflicts.append(
                    MemoryConflict(
                        conflict_type="version_mismatch",
                        entry_ids=[e.entry_id for e in conflicting],
                        reason=f"包 {name} 存在多个不同版本",
                        suggested_action="manual_review",
                    )
                )
        return conflicts

    def _detect_artifact_conflicts(
        self, entries: list[MemoryEntry]
    ) -> list[MemoryConflict]:
        """检测 artifacts 类别中相同 path 的多条记录。"""
        conflicts: list[MemoryConflict] = []
        paths: dict[str, list[MemoryEntry]] = {}
        for entry in entries:
            if entry.category != MemoryCategory.ARTIFACTS:
                continue
            path = entry.content.get("path")
            if not path:
                continue
            paths.setdefault(path, []).append(entry)

        for path, entry_list in paths.items():
            if len(entry_list) > 1:
                conflicts.append(
                    MemoryConflict(
                        conflict_type="duplicate",
                        entry_ids=[e.entry_id for e in entry_list],
                        reason=f"产物路径 {path} 存在多条记录",
                        suggested_action="keep_latest",
                    )
                )
        return conflicts

    def _detect_preference_conflicts(
        self, entries: list[MemoryEntry]
    ) -> list[MemoryConflict]:
        """检测 preferences 类别中相同 key 的不同 value。"""
        conflicts: list[MemoryConflict] = []
        prefs: dict[str, list[tuple[Any, MemoryEntry]]] = {}
        for entry in entries:
            if entry.category != MemoryCategory.PREFERENCES:
                continue
            key = entry.content.get("key")
            value = entry.content.get("value")
            if key is None:
                continue
            prefs.setdefault(key, []).append((value, entry))

        for key, values in prefs.items():
            distinct_values = {v for v, _ in values}
            if len(distinct_values) > 1:
                conflicts.append(
                    MemoryConflict(
                        conflict_type="contradiction",
                        entry_ids=[e.entry_id for _, e in values],
                        reason=f"偏好 {key} 存在矛盾值：{distinct_values}",
                        suggested_action="manual_review",
                    )
                )
        return conflicts

    def _detect_failure_pattern_conflicts(
        self, entries: list[MemoryEntry]
    ) -> list[MemoryConflict]:
        """检测 failure_patterns 类别中相同 (tool, exc_type) 的不同 recovery。"""
        conflicts: list[MemoryConflict] = []
        patterns: dict[tuple[str, str], list[tuple[str, MemoryEntry]]] = {}
        for entry in entries:
            if entry.category != MemoryCategory.FAILURE_PATTERNS:
                continue
            tool = entry.content.get("tool", "unknown")
            exc_type = entry.content.get("exc_type", "UnknownError")
            recovery = entry.content.get("recovery", "")
            patterns.setdefault((tool, exc_type), []).append((recovery, entry))

        for (tool, exc_type), recoveries in patterns.items():
            distinct_recoveries = {r for r, _ in recoveries}
            if len(distinct_recoveries) > 1:
                conflicts.append(
                    MemoryConflict(
                        conflict_type="recovery_conflict",
                        entry_ids=[e.entry_id for _, e in recoveries],
                        reason=f"失败模式 ({tool}, {exc_type}) 存在不同恢复策略",
                        suggested_action="manual_review",
                    )
                )
        return conflicts


# ---------------------------------------------------------------------------
# 管理层：编排提取、检索、注入、清理
# ---------------------------------------------------------------------------

class MemoryManager:
    """长期记忆管理器，负责注入、记录、清理的生命周期。"""

    def __init__(
        self,
        store: MemoryStore,
        extractor: MemoryExtractor,
        config: MemoryConfig,
        llm_extractor: MemoryExtractor | None = None,
        policy: PolicyEngine | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """初始化管理器。

        Args:
            store: 持久化存储后端。
            extractor: 默认规则提取器。
            config: 记忆配置。
            llm_extractor: 可选的 LLM 提取器；失败时不影响规则提取。
            policy: 可选的安全策略引擎；未注入时不做读写权限检查。
            llm_client: 可选的 LLM 客户端，用于 L2 语义重排（分层检索）。
        """
        self._store = store
        self._extractor = extractor
        self._config = config
        self._llm_extractor = llm_extractor
        self._policy = policy
        self._llm_client = llm_client

    def inject(self, user_input: str) -> str:
        """根据用户输入检索相关记忆并返回注入片段。

        检索流程：
          1. L1：按字符/token 重叠召回 retrieval_top_k * 2 条候选并排序；
          2. L0：未命中且 recency_fallback 开启时，兜底注入最近 N 条。
          3. 交给 MemoryInjector 按 token/条目数限制格式化。

        Args:
            user_input: 当前用户输入。

        Returns:
            要追加到 system prompt 的文本；未启用或无匹配时返回空字符串。
        """
        if not self._config.enabled:
            return ""

        text = (user_input or "").strip()
        if not text:
            return ""

        try:
            ranked = self._retrieve_l1(text)
            if not ranked and self._config.recency_fallback:
                # L0：字面检索零命中时兜底注入最近 N 条，避免 Agent “失忆”。
                ranked = self._recency_fallback()
            return MemoryInjector.format(ranked, self._config)
        except Exception:
            _logger.exception("记忆注入失败")
            return ""

    def _retrieve_l1(self, text: str) -> list[MemoryEntry]:
        """L1 字面检索 + 二次排序（不含任何兜底）。"""
        candidates = self._store.query(
            MemoryQuery(
                text=text, top_k=max(1, self._config.retrieval_top_k) * 2
            )
        )
        candidates = self._filter_readable_entries(candidates)
        return self._rank_entries(candidates, text)

    def _recency_fallback(self) -> list[MemoryEntry]:
        """L0 recency 兜底：返回经读策略过滤的最近 top_k 条记忆。"""
        if hasattr(self._store, "list_recent"):
            recent = self._store.list_recent(max(1, self._config.retrieval_top_k))
        else:
            recent = self._store.list_entries()[
                : max(1, self._config.retrieval_top_k)
            ]
        return self._filter_readable_entries(recent)

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """按自然语言搜索记忆（search-then-read 的发现层）。

        复用分层检索：L1 字面命中直接返回；未命中按配置走 L2/L0。
        空库/无命中/未启用均返回空列表（非错误）。

        Args:
            query: 自然语言查询（如“项目代号”“之前创建的文件”）。
            limit: 最大返回条数。

        Returns:
            结构化候选列表 [{entry_id, category, summary, content_preview, uri}]，
            按相关性排序，最多 limit 条。uri 可传给 memory_read 精读。
        """
        if not self._config.enabled:
            return []
        text = (query or "").strip()
        if not text:
            return []
        try:
            ranked = self._retrieve_l1(text)
            if (
                not ranked
                and self._config.semantic_retrieval
                and self._llm_client is not None
            ):
                try:
                    ranked = await self._semantic_rank(text, self._recency_fallback())
                except Exception:
                    _logger.exception("memory_search 语义重排失败")
            if not ranked and self._config.recency_fallback:
                ranked = self._recency_fallback()
            return [
                {
                    "entry_id": entry.entry_id,
                    "category": entry.category.value,
                    "summary": entry.summary,
                    "content_preview": (
                        entry.content.get("content_preview", "")
                        if entry.content
                        else ""
                    ),
                    "uri": entry.uri,
                }
                for entry in ranked[: max(1, limit)]
            ]
        except Exception:
            _logger.exception("memory_search 检索失败")
            return []

    async def inject_async(self, user_input: str) -> str:
        """异步注入入口（分层检索）：L1 字面 → L2 语义重排 → L0 兜底。

        流程：
          1. L1 字面检索命中 → 直接返回；
          2. 未命中且 semantic_retrieval 开启且有 LLM client →
             L2 语义重排（失败/为空 → 继续走 3）；
          3. L0 recency 兜底（recency_fallback 开启时）。
        """
        if not self._config.enabled:
            return ""
        text = (user_input or "").strip()
        if not text:
            return ""
        try:
            ranked = self._retrieve_l1(text)
            if (
                not ranked
                and self._config.semantic_retrieval
                and self._llm_client is not None
            ):
                try:
                    ranked = await self._semantic_rank(text, self._recency_fallback())
                except Exception:
                    _logger.exception("L2 语义重排失败")
            if not ranked and self._config.recency_fallback:
                ranked = self._recency_fallback()
            return MemoryInjector.format(ranked, self._config)
        except Exception:
            _logger.exception("记忆注入失败")
            return ""

    async def _semantic_rank(
        self, query: str, candidates: list[MemoryEntry]
    ) -> list[MemoryEntry]:
        """L2：用 LLM 对候选记忆按与 query 的相关性排序。

        LLM 输出 JSON：{"ranking": ["entry_id", ...]}。
        解析失败或调用异常时返回空列表（调用方降级 L0）。
        """
        if not candidates:
            return []
        client = self._llm_client
        if client is None:
            return []
        listing = "\n".join(
            f"- id={e.entry_id} | {e.summary}" for e in candidates
        )
        prompt = (
            "请根据用户问题与以下记忆条目的相关性，按相关程度降序输出条目 id。"
            "只输出 JSON：{\"ranking\": [\"id1\", \"id2\"]}，不相关的可以不包含。\n\n"
            f"用户问题：{query}\n\n记忆条目：\n{listing}"
        )
        response = await client.chat(
            [{"role": "user", "content": prompt}], tools=None
        )
        text = response.get("content", "") if isinstance(response, dict) else str(response)
        ranked_ids = self._parse_ranking_json(text)
        by_id = {e.entry_id: e for e in candidates}
        return [by_id[i] for i in ranked_ids if i in by_id]

    @staticmethod
    def _parse_ranking_json(text: str) -> list[str]:
        """从 LLM 输出解析排序 id 列表（宽容：找第一个 JSON 对象）。"""
        import json as _json

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return []
        try:
            data = _json.loads(match.group(0))
        except ValueError:
            return []
        ranking = data.get("ranking")
        if not isinstance(ranking, list):
            return []
        return [str(i) for i in ranking]

    def _filter_writable_entries(
        self, entries: list[MemoryEntry]
    ) -> list[MemoryEntry]:
        """按 memory/category 写策略过滤条目；未注入策略时全部放行。"""
        if self._policy is None:
            return entries

        allowed: list[MemoryEntry] = []
        for entry in entries:
            decision = self._policy.evaluate(
                resource="memory/category",
                operation="write",
                subject=entry.category.value,
            )
            if decision.action == PolicyAction.DENY:
                _logger.warning(
                    "策略拒绝写入记忆：category=%s, reason=%s",
                    entry.category.value,
                    decision.reason,
                )
                continue
            allowed.append(entry)
        return allowed

    def _filter_readable_entries(
        self, entries: list[MemoryEntry]
    ) -> list[MemoryEntry]:
        """按 memory/category 读策略过滤条目；未注入策略时全部放行。"""
        if self._policy is None:
            return entries

        allowed: list[MemoryEntry] = []
        for entry in entries:
            decision = self._policy.evaluate(
                resource="memory/category",
                operation="read",
                subject=entry.category.value,
            )
            if decision.action == PolicyAction.DENY:
                _logger.warning(
                    "策略拒绝注入记忆：category=%s, reason=%s",
                    entry.category.value,
                    decision.reason,
                )
                continue
            allowed.append(entry)
        return allowed

    def _rank_entries(
        self, entries: list[MemoryEntry], query_text: str
    ) -> list[MemoryEntry]:
        """对候选记忆做二次排序。

        排序公式：effective_score = overlap_score × confidence × feedback × stale。
        其中 stale 按 category 半衰期连续指数衰减。
        """
        now = datetime.now(timezone.utc)
        query_tokens = self._tokenize(query_text)
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in entries:
            overlap_score = self._overlap_score(query_tokens, entry)
            feedback_multiplier = self._feedback_multiplier(entry)
            stale_multiplier = self._stale_multiplier(entry, now)
            effective_score = (
                overlap_score
                * entry.confidence
                * feedback_multiplier
                * stale_multiplier
            )
            scored.append((effective_score, entry))

        scored.sort(
            key=lambda item: (item[0], item[1].updated_at.timestamp()),
            reverse=True,
        )
        return [entry for _, entry in scored]

    def _overlap_score(
        self, query_tokens: set[str], entry: MemoryEntry
    ) -> float:
        """计算查询与 entry 的 token 重叠分。"""
        entry_text = self._entry_text(entry)
        entry_tokens = self._tokenize(entry_text)
        if not query_tokens or not entry_tokens:
            return 0.0
        intersection = query_tokens.intersection(entry_tokens)
        return float(len(intersection))

    def _entry_text(self, entry: MemoryEntry) -> str:
        """把 entry 的 summary/tags/content 拼成可检索文本。"""
        parts = [entry.summary, " ".join(entry.tags)]
        parts.extend(self._flatten_values(entry.content))
        return " ".join(parts)

    @staticmethod
    def _flatten_values(obj: Any) -> list[str]:
        """把 dict/list 中的值展平为可检索字符串。"""
        result: list[str] = []
        if isinstance(obj, dict):
            for value in obj.values():
                result.extend(MemoryManager._flatten_values(value))
        elif isinstance(obj, list):
            for item in obj:
                result.extend(MemoryManager._flatten_values(item))
        elif isinstance(obj, str):
            result.append(obj)
        elif isinstance(obj, int | float | bool):
            result.append(str(obj))
        return result

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """简单分词：英文按单词，中文按单字，都转小写。"""
        lowered = text.lower()
        tokens: set[str] = set(re.findall(r"[a-z0-9]+", lowered))
        tokens.update(re.findall(r"[\u4e00-\u9fff]", lowered))
        return tokens

    @staticmethod
    def _feedback_multiplier(entry: MemoryEntry) -> float:
        """根据反馈分数返回排序乘数。"""
        if entry.feedback_score == 1:
            return 1.5
        if entry.feedback_score == -1:
            return 0.3
        return 1.0

    def _stale_multiplier(self, entry: MemoryEntry, now: datetime) -> float:
        """根据 category 半衰期计算时间衰减乘数。"""
        half_life = (
            self._config.environment_stale_days
            if entry.category == MemoryCategory.ENVIRONMENT
            else self._config.stale_threshold_days
        )
        if half_life <= 0:
            return 1.0
        age_days = (now - entry.updated_at).total_seconds() / 86400.0
        return float(0.5 ** (age_days / half_life))

    def record(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        """从 Trace/State 提取记忆并持久化。

        Args:
            trace: 本次运行的 Trace。
            state: 本次运行的 State。
            run_metadata: 可选的运行元数据，如 run_id。

        Returns:
            成功保存的记忆条目列表；失败返回空列表。
        """
        if not self._config.enabled:
            return []

        run_metadata = run_metadata or {}
        try:
            entries = self._extractor.extract(trace, state, run_metadata)
            if self._llm_extractor is not None:
                try:
                    entries.extend(
                        self._llm_extractor.extract(trace, state, run_metadata)
                    )
                except Exception:
                    _logger.exception("LLM 记忆提取失败")

            allowed_entries = self._filter_writable_entries(entries)

            saved: list[MemoryEntry] = []
            for entry in allowed_entries:
                saved.append(self._save_entry(entry))
            return saved
        except Exception:
            _logger.exception("记忆记录失败")
            return []

    def record_feedback(self, entry_id: str, score: int) -> bool:
        """记录用户对某条记忆的反馈。

        多次反馈时只保留最新一次的 score，feedback_count 递增。

        Args:
            entry_id: 记忆 id。
            score: -1 踩 / 0 中性 / 1 赞。

        Returns:
            是否成功更新。
        """
        if not self._config.enabled:
            return False

        if score not in {-1, 0, 1}:
            _logger.warning("反馈分数非法：%s", score)
            return False

        try:
            entry = self._store.get(entry_id)
            if entry is None:
                return False

            entry.feedback_score = score
            entry.feedback_count += 1
            entry.last_feedback_at = datetime.now(timezone.utc)
            entry.updated_at = entry.last_feedback_at
            self._store.save(entry)
            return True
        except Exception:
            _logger.exception("记录记忆反馈失败：%s", entry_id)
            return False

    def audit(
        self, category: MemoryCategory | None = None
    ) -> tuple[list[MemoryEntry], list[MemoryConflict]]:
        """手动审计记忆：标灰陈旧条目并检测冲突。

        Args:
            category: 限定审计类别；None 表示全部。

        Returns:
            (被标灰的条目列表, 检测到的冲突列表)。
        """
        if not self._config.enabled:
            return [], []

        try:
            now = datetime.now(timezone.utc)
            entries = self._store.list_entries(category=category)
            stale_marked: list[MemoryEntry] = []

            for entry in entries:
                half_life = (
                    self._config.environment_stale_days
                    if entry.category == MemoryCategory.ENVIRONMENT
                    else self._config.stale_threshold_days
                )
                if half_life <= 0:
                    continue
                age_days = (now - entry.updated_at).total_seconds() / 86400.0
                if age_days >= half_life and not entry.stale:
                    entry.stale = True
                    self._store.save(entry)
                    stale_marked.append(entry)

            detector = MemoryConflictDetector()
            conflicts = detector.detect(self._store)
            self._apply_conflict_links(conflicts)

            return stale_marked, conflicts
        except Exception:
            _logger.exception("记忆审计失败")
            return [], []

    def _apply_conflict_links(self, conflicts: list[MemoryConflict]) -> None:
        """把冲突中的新条目单向链接到旧条目并保存。"""
        for conflict in conflicts:
            try:
                entries: list[MemoryEntry] = []
                for eid in conflict.entry_ids:
                    entry = self._store.get(eid)
                    if entry is not None:
                        entries.append(entry)
                if len(entries) < 2:
                    continue
                entries.sort(key=lambda e: e.updated_at.timestamp(), reverse=True)
                newest = entries[0]
                older_ids = [e.entry_id for e in entries[1:]]
                updated_links = list(newest.linked_entry_ids)
                for oid in older_ids:
                    if oid not in updated_links:
                        updated_links.append(oid)
                if updated_links != newest.linked_entry_ids:
                    newest.linked_entry_ids = updated_links
                    self._store.save(newest)
            except Exception:
                _logger.exception("建立冲突链接失败：%s", conflict)

    def cleanup(self) -> int:
        """清理过期记忆。

        Returns:
            删除的条目数量。
        """
        if not self._config.enabled:
            return 0
        try:
            return self._store.cleanup(None)
        except Exception:
            _logger.exception("记忆清理失败")
            return 0

    def read(self, uri: str) -> str | None:
        """读取指定 URI 的记忆内容。

        支持 `hermes://memory/<category>/<entry_id>.jsonl` 格式。
        返回完整 entry 的 JSON 字符串，便于 `memory_read` 工具使用。

        Args:
            uri: 记忆 URI。

        Returns:
            JSON 字符串；URI 非法或条目不存在时返回 None。
        """
        if not self._config.enabled:
            return None

        try:
            entry = self._resolve_uri(uri)
            if entry is None:
                return None
            if self._policy is not None:
                decision = self._policy.evaluate(
                    resource="memory/category",
                    operation="read",
                    subject=entry.category.value,
                )
                if decision.action == PolicyAction.DENY:
                    _logger.warning(
                        "策略拒绝读取记忆：uri=%s, category=%s, reason=%s",
                        uri,
                        entry.category.value,
                        decision.reason,
                    )
                    return None
            return json.dumps(_entry_to_dict(entry), ensure_ascii=False)
        except Exception:
            _logger.exception("记忆读取失败：%s", uri)
            return None

    def check_read_policy(self, uri: str) -> PolicyDecision | None:
        """检查给定 URI 的记忆是否允许读取。

        供 `memory_read` 等上层调用方在读取前显式获取策略决策，
        从而把拒绝原因返回给 LLM。

        Args:
            uri: 记忆 URI。

        Returns:
            策略决策；无策略、URI 非法或允许时返回 None。
        """
        if self._policy is None:
            return None

        entry = self._resolve_uri(uri)
        if entry is None:
            return None

        return self._policy.evaluate(
            resource="memory/category",
            operation="read",
            subject=entry.category.value,
        )

    def _resolve_uri(self, uri: str) -> MemoryEntry | None:
        """把 hermes://memory/<category>/<entry_id>.jsonl 解析为 MemoryEntry。"""
        prefix = "hermes://memory/"
        if not uri.startswith(prefix):
            return None
        rest = uri[len(prefix):]
        parts = rest.split("/")
        if len(parts) != 2 or not parts[1].endswith(".jsonl"):
            return None
        category_value, filename = parts
        try:
            MemoryCategory(category_value)
        except ValueError:
            return None
        entry_id = filename.removesuffix(".jsonl")
        return self._store.get(entry_id)

    def _save_entry(self, entry: MemoryEntry) -> MemoryEntry:
        """单条保存：过滤敏感信息、实施数量淘汰、写入 store。"""
        if self._config.filter_sensitive:
            entry = self._apply_sensitive_filter(entry)
        self._enforce_category_limit(entry.category)
        return self._store.save(entry)

    def _enforce_category_limit(self, category: MemoryCategory) -> None:
        """按 max_entries_per_category 淘汰最旧条目。"""
        limit = self._config.max_entries_per_category
        if limit <= 0:
            return

        existing = self._store.list_entries(category=category)
        while len(existing) >= limit:
            oldest = min(existing, key=lambda e: e.updated_at)
            self._store.delete(oldest.entry_id)
            existing.remove(oldest)

    def _apply_sensitive_filter(self, entry: MemoryEntry) -> MemoryEntry:
        """对 entry 的 content/summary/tags 做敏感信息过滤。"""
        patterns = self._config.sensitive_patterns
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


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------

def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    """把 MemoryEntry 转为可 JSON 序列化的字典。"""
    data = asdict(entry)
    data["category"] = entry.category.value
    data["created_at"] = entry.created_at.isoformat()
    data["updated_at"] = entry.updated_at.isoformat()
    return data


# ---------------------------------------------------------------------------
# 敏感信息过滤辅助函数
# ---------------------------------------------------------------------------

def _filter_sensitive_data(obj: Any, patterns: list[str]) -> Any:
    """递归扫描对象，对命中敏感模式的内容进行红码替换。"""
    if not patterns:
        return obj
    lowered_patterns = [p.lower() for p in patterns]

    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if any(p in key.lower() for p in lowered_patterns):
                result[key] = "[REDACTED]"
            else:
                result[key] = _filter_sensitive_data(value, patterns)
        return result

    if isinstance(obj, list):
        return [_filter_sensitive_data(item, patterns) for item in obj]

    if isinstance(obj, str):
        return _filter_sensitive_value(obj, patterns)

    return obj


def _filter_sensitive_value(value: str, patterns: list[str]) -> str:
    """若字符串命中任一敏感模式，则整体替换为 [REDACTED]。"""
    if not patterns:
        return value
    lowered = value.lower()
    if any(p.lower() in lowered for p in patterns):
        return "[REDACTED]"
    return value
