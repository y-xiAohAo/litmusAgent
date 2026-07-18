"""ContextCache —— 工具结果的本地文件缓存。

Phase 7 上下文压缩的核心组件之一。当工具结果过长时，把完整内容写入本地
Markdown 文件，消息历史中只保留 URI 引用和摘要。缓存按 session/run 组织，
进程结束后默认清理。
"""

from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    """单个缓存条目的元数据。

    Attributes:
        entry_id: 缓存条目唯一标识。
        run_id: 所属 run 的标识。
        session_id: 所属 session 的标识。
        tool_name: 产生该条目的工具名。
        created_at: 创建时间（UTC）。
        file_path: 本地文件路径。
        uri: 外部引用 URI，格式为 hermes://context/<session_id>/<run_id>/<entry_id>.md。
        summary: 可选摘要。
        content_length: 原始内容长度。
    """

    entry_id: str
    run_id: str
    session_id: str
    tool_name: str
    created_at: datetime
    file_path: Path
    uri: str
    summary: str
    content_length: int


class ContextCache:
    """按 session/run 组织的本地文件缓存。

    设计要点：
      - URI 与文件路径解耦：外部只使用 `hermes://context/...`，内部再映射到磁盘路径。
      - 只负责 session 内存储，不跨进程保留。
      - 读取时严格校验 session_id，防止跨 session 访问。
    """

    URI_SCHEME = "hermes://context/"
    _ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, root_dir: Path, session_id: str) -> None:
        """初始化缓存。

        Args:
            root_dir: 缓存根目录，例如 `<project_root>/.hermes/context_cache`。
            session_id: 当前 session 标识，同一个 Agent 实例生命周期内共享。

        Raises:
            ValueError: 如果 session_id 包含非法字符（如 ..、/、空格等）。
        """
        self._validate_id(session_id, "session_id")
        self._root = root_dir
        self._session_id = session_id

    @staticmethod
    def _validate_id(value: str, name: str) -> None:
        """校验 session_id / run_id 只含安全字符，防止路径遍历。"""
        if not value or not ContextCache._ID_PATTERN.match(value):
            raise ValueError(
                f"{name} 只能包含字母、数字、下划线、中划线， got: {value!r}"
            )

    @property
    def session_dir(self) -> Path:
        """当前 session 的缓存目录。"""
        return self._root / self._session_id

    def store(
        self,
        run_id: str,
        tool_name: str,
        content: str,
        summary: str = "",
    ) -> CacheEntry:
        """将内容存入缓存。

        Args:
            run_id: 当前 run 标识。
            tool_name: 产生内容的工具名。
            content: 要缓存的完整内容。
            summary: 可选摘要。

        Returns:
            描述缓存条目的 CacheEntry。

        Raises:
            ValueError: 如果 run_id 包含非法字符。
        """
        self._validate_id(run_id, "run_id")
        entry_id = uuid.uuid4().hex
        dir_path = self._root / self._session_id / run_id
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / f"{entry_id}.md"
        file_path.write_text(content, encoding="utf-8")

        uri = f"{self.URI_SCHEME}{self._session_id}/{run_id}/{entry_id}.md"
        return CacheEntry(
            entry_id=entry_id,
            run_id=run_id,
            session_id=self._session_id,
            tool_name=tool_name,
            created_at=datetime.now(timezone.utc),
            file_path=file_path,
            uri=uri,
            summary=summary,
            content_length=len(content),
        )

    def read(self, uri: str) -> str | None:
        """通过 URI 读取缓存内容。

        Args:
            uri: hermes://context/<session_id>/<run_id>/<entry_id>.md

        Returns:
            缓存内容；如果 URI 无效或文件不存在，返回 None。
        """
        file_path = self._uri_to_path(uri)
        if file_path is None or not file_path.exists():
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def cleanup(self, max_age: timedelta | None = None) -> int:
        """清理当前 session 的缓存文件。

        Args:
            max_age: 如果指定，只删除早于该时间的文件；否则删除整个 session 目录。

        Returns:
            删除的文件数。
        """
        if not self.session_dir.exists():
            return 0

        if max_age is None:
            all_files = list(self.session_dir.rglob("*"))
            shutil.rmtree(self.session_dir)
            return len(all_files)

        cutoff = datetime.now(timezone.utc) - max_age
        removed = 0
        for file_path in self.session_dir.rglob("*.md"):
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    file_path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def _uri_to_path(self, uri: str) -> Path | None:
        """将 URI 映射到本地文件路径，并校验 session_id。"""
        if not uri.startswith(self.URI_SCHEME):
            return None
        relative = uri[len(self.URI_SCHEME) :]
        parts = relative.split("/")
        if len(parts) != 3:
            return None

        session_id, run_id, filename = parts
        if session_id != self._session_id:
            return None
        if not filename.endswith(".md"):
            return None

        return self._root / session_id / run_id / filename

    def to_dict(self) -> dict[str, Any]:
        """导出缓存状态摘要，便于 Trace 记录。"""
        entries: list[dict[str, Any]] = []
        if self.session_dir.exists():
            for file_path in self.session_dir.rglob("*.md"):
                rel = file_path.relative_to(self.session_dir)
                entries.append(
                    {
                        "run_id": rel.parts[0] if rel.parts else "",
                        "entry_id": file_path.stem,
                        "size": file_path.stat().st_size,
                    }
                )
        return {
            "session_id": self._session_id,
            "root_dir": str(self._root),
            "entry_count": len(entries),
            "entries": entries,
        }
