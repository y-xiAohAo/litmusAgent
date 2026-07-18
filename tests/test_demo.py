"""验证 Phase 10.9 Demo 脚本的可运行性。

设计原则：
  1. Demo 脚本默认依赖真实 API Key，CI 不能因此失败。
  2. 测试覆盖 --help、--echo 以及无 Key 时的友好提示。
  3. 不依赖真实 Docker 或真实 LLM。
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from unittest import mock

import pytest

DEMO_PATH = Path(__file__).parent.parent / "examples" / "demo_real_llm.py"


@pytest.fixture
def demo_module():
    """以 runpy 加载 demo 脚本，返回模块对象。"""
    assert DEMO_PATH.exists(), "examples/demo_real_llm.py 不存在"
    return runpy.run_path(str(DEMO_PATH))


class TestDemoScriptHelp:
    """测试 Demo 脚本的帮助信息。"""

    def test_help_exits_cleanly(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--help 应正常退出，不抛 SystemExit 异常。"""
        with pytest.raises(SystemExit) as exc_info:
            sys.argv = [str(DEMO_PATH), "--help"]
            runpy.run_path(str(DEMO_PATH), run_name="__main__")
        assert exc_info.value.code == 0


class TestDemoScriptEchoMode:
    """测试 --echo 模式，无需 API Key 即可运行。"""

    def test_echo_runs_without_api_key(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--echo 模式在无 Key 时也能跑通。"""
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            sys.argv = [
                str(DEMO_PATH),
                "--echo",
                "--prompt",
                "计算 1 + 1",
            ]
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_path(str(DEMO_PATH), run_name="__main__")
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "计算 1 + 1" in captured.out or "You said" in captured.out


class TestDemoScriptNoKey:
    """测试无 API Key 且无 --echo 时的友好提示。"""

    def test_no_key_prints_instructions(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """未提供 API Key 时应提示用户如何配置，而不是崩溃。"""
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=True):
            sys.argv = [
                str(DEMO_PATH),
                "--prompt",
                "hello",
            ]
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_path(str(DEMO_PATH), run_name="__main__")
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "OPENAI_API_KEY" in captured.out or "API Key" in captured.out
