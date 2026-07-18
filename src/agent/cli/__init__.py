"""Hermes CLI 子包。

- `agent_cli.main`: Agent 主 CLI（Phase 10.1）
- `memory_cli.main`: 记忆管理 CLI（Phase 8.4）
"""

from __future__ import annotations

from agent.cli.agent_cli import main
from agent.cli.memory_cli import main as memory_main

__all__ = ["main", "memory_main"]
