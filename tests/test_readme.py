"""验证 README.md 的结构与代码示例。

设计原则：
  1. README 是用户的第一份指南，不能腐烂。
  2. 测试不执行代码示例（避免调用真实 API / Docker），只做语法检查。
  3. 关键章节缺失时测试失败，提醒维护者同步更新。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

README_PATH = Path(__file__).parent.parent / "README.md"


@pytest.fixture
def readme_content() -> str:
    """读取 README.md 内容。"""
    assert README_PATH.exists(), "README.md 不存在"
    return README_PATH.read_text(encoding="utf-8")


class TestReadmeStructure:
    """测试 README 结构完整性。"""

    @pytest.mark.parametrize(
        "section",
        [
            "核心特性",
            "前置条件",
            "安装",
            "快速开始",
            "项目结构",
            "开发",
            "许可证",
        ],
    )
    def test_key_sections_exist(self, readme_content: str, section: str) -> None:
        """README 必须包含关键章节标题。"""
        pattern = re.compile(rf"^##\s+{re.escape(section)}", re.MULTILINE)
        assert pattern.search(readme_content), f"缺少章节：{section}"


class TestReadmeCodeBlocks:
    """测试 README 中 Python 代码示例的语法正确性。"""

    def _extract_python_blocks(self, content: str) -> list[str]:
        """从 Markdown 内容中提取 ```python ... ``` 代码块。"""
        pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
        return pattern.findall(content)

    def test_python_blocks_are_valid_syntax(self, readme_content: str) -> None:
        """所有 Python 代码块都必须能被 ast.parse 解析。"""
        blocks = self._extract_python_blocks(readme_content)
        assert blocks, "README 中至少应有一个 Python 代码示例"

        for index, block in enumerate(blocks, start=1):
            try:
                ast.parse(block)
            except SyntaxError as exc:
                pytest.fail(f"第 {index} 个 Python 代码块语法错误：{exc}")
