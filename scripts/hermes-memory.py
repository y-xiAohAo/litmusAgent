#!/usr/bin/env python3
"""记忆管理 CLI 入口包装。

直接调用：
    python scripts/hermes-memory.py list
    python scripts/hermes-memory.py show <entry_id>
    python scripts/hermes-memory.py delete <entry_id>
    python scripts/hermes-memory.py feedback <entry_id> --score 1
    python scripts/hermes-memory.py audit
    python scripts/hermes-memory.py export

未来 Phase 10 完整 CLI 可将此脚本并入主入口，或保持独立。
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 终端默认编码可能为 GBK，强制使用 UTF-8 输出中文帮助与结果。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# 将项目 src 目录加入路径，支持脚本独立运行。
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from agent.cli.memory_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
