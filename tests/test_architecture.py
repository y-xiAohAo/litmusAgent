"""验证 docs/architecture.md 的结构与 ASCII 图。

设计原则：
  1. 架构文档是面试和 onboarding 的重要材料，不能腐烂。
  2. 测试不评价 ASCII 图的艺术性，只验证关键章节和图的数量。
  3. 保持轻量，不依赖外部工具解析 Mermaid 等格式。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ARCHITECTURE_PATH = Path(__file__).parent.parent / "docs" / "architecture.md"


@pytest.fixture
def architecture_content() -> str:
    """读取 architecture.md 内容。"""
    assert ARCHITECTURE_PATH.exists(), "docs/architecture.md 不存在"
    return ARCHITECTURE_PATH.read_text(encoding="utf-8")


class TestArchitectureStructure:
    """测试架构文档结构完整性。"""

    @pytest.mark.parametrize(
        "section",
        [
            "组件架构",
            "数据流",
            "执行序列",
        ],
    )
    def test_key_sections_exist(self, architecture_content: str, section: str) -> None:
        """架构文档必须包含关键章节标题。"""
        pattern = re.compile(rf"^##\s+{re.escape(section)}", re.MULTILINE)
        assert pattern.search(architecture_content), f"缺少章节：{section}"


class TestArchitectureDiagrams:
    """测试 ASCII 图数量与基本结构。"""

    def test_contains_at_least_three_ascii_diagrams(self, architecture_content: str) -> None:
        """至少包含 3 个 ASCII 图代码块。"""
        # 统计被 ``` 包裹的代码块，假设 ASCII 图使用纯文本代码块。
        code_blocks = re.findall(r"```\n(.*?)\n```", architecture_content, re.DOTALL)
        assert len(code_blocks) >= 3, f"ASCII 图数量不足：期望至少 3 个，实际 {len(code_blocks)} 个"

    def test_diagrams_contain_box_drawing_characters(self, architecture_content: str) -> None:
        """ASCII 图中包含制表符/框线字符，说明不是普通文本。"""
        code_blocks = re.findall(r"```\n(.*?)\n```", architecture_content, re.DOTALL)
        box_chars = {"┌", "┐", "└", "┘", "│", "─", "├", "┤", "┬", "┴", "┼", "►", "▲", "▼"}

        found_box = any(
            any(char in block for char in box_chars)
            for block in code_blocks
        )
        assert found_box, "ASCII 图中未找到框线字符"
