"""验证 docs/evaluation-log.md 的结构完整性。

设计原则：
  1. 评测日志是跨会话维护的“活文档”，不能腐烂。
  2. 测试不检查具体数据，只验证关键章节存在。
  3. 保证新 session 打开文档时能看到约定好的结构。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

LOG_PATH = Path(__file__).parent.parent / "docs" / "evaluation-log.md"


@pytest.fixture
def log_content() -> str:
    """读取评测日志内容。"""
    assert LOG_PATH.exists(), "docs/evaluation-log.md 不存在"
    return LOG_PATH.read_text(encoding="utf-8")


class TestEvaluationLogStructure:
    """测试评测日志结构完整性。"""

    @pytest.mark.parametrize(
        "section",
        [
            "项目基线",
            "测试环境",
            "端到端测试结果",
            "Bug 与问题清单",
            "优化记录",
            "下一步 Action Items",
        ],
    )
    def test_sections_exist(self, log_content: str, section: str) -> None:
        """评测日志必须包含关键章节。"""
        pattern = re.compile(rf"^##\s+{re.escape(section)}", re.MULTILINE)
        assert pattern.search(log_content), f"evaluation-log.md 缺少章节：{section}"
