"""验证 docs/usage.md 与 docs/configuration.md 的结构与代码示例。

设计原则：
  1. 使用文档是用户从入门到熟练的桥梁，不能腐烂。
  2. 测试不执行代码示例，只做语法检查。
  3. 验证关键章节存在，避免文档退化。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).parent.parent / "docs"
USAGE_PATH = DOCS_DIR / "usage.md"
CONFIG_PATH = DOCS_DIR / "configuration.md"


@pytest.fixture
def usage_content() -> str:
    """读取 usage.md 内容。"""
    assert USAGE_PATH.exists(), "docs/usage.md 不存在"
    return USAGE_PATH.read_text(encoding="utf-8")


@pytest.fixture
def config_content() -> str:
    """读取 configuration.md 内容。"""
    assert CONFIG_PATH.exists(), "docs/configuration.md 不存在"
    return CONFIG_PATH.read_text(encoding="utf-8")


class TestUsageDocsStructure:
    """测试使用文档结构完整性。"""

    @pytest.mark.parametrize(
        "section",
        [
            "CLI 使用",
            "Python API 使用",
            "常见问题",
        ],
    )
    def test_usage_sections_exist(self, usage_content: str, section: str) -> None:
        """usage.md 必须包含关键章节。"""
        pattern = re.compile(rf"^##\s+{re.escape(section)}", re.MULTILINE)
        assert pattern.search(usage_content), f"usage.md 缺少章节：{section}"

    @pytest.mark.parametrize(
        "section",
        [
            "配置文件结构",
            "llm",
            "agent",
            "sandbox",
            "完整示例",
        ],
    )
    def test_config_sections_exist(self, config_content: str, section: str) -> None:
        """configuration.md 必须包含关键章节。"""
        pattern = re.compile(rf"^##\s+{re.escape(section)}", re.MULTILINE)
        assert pattern.search(config_content), f"configuration.md 缺少章节：{section}"


class TestUsageDocsCodeBlocks:
    """测试文档中 Python 代码示例的语法正确性。"""

    def _extract_python_blocks(self, content: str) -> list[str]:
        """从 Markdown 内容中提取 ```python ... ``` 代码块。"""
        pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
        return pattern.findall(content)

    def _assert_blocks_valid(self, content: str, doc_name: str) -> None:
        """验证指定文档中所有 Python 代码块语法正确。"""
        blocks = self._extract_python_blocks(content)
        assert blocks, f"{doc_name} 中至少应有一个 Python 代码示例"

        for index, block in enumerate(blocks, start=1):
            try:
                ast.parse(block)
            except SyntaxError as exc:
                pytest.fail(f"{doc_name} 第 {index} 个 Python 代码块语法错误：{exc}")

    def test_usage_python_blocks_are_valid(self, usage_content: str) -> None:
        """usage.md 中 Python 代码块语法正确。"""
        self._assert_blocks_valid(usage_content, "docs/usage.md")

    def test_config_python_blocks_are_valid(self, config_content: str) -> None:
        """configuration.md 中 Python 代码块语法正确。"""
        self._assert_blocks_valid(config_content, "docs/configuration.md")
