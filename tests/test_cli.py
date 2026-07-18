"""Agent 主 CLI 测试。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from agent import __version__
from agent.cli.agent_cli import _load_config, main


def _has_ansi(text: str) -> bool:
    """检查文本是否包含 ANSI 转义序列。"""
    return "\x1b[" in text


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    """--version 应输出 agent 与版本号。"""
    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert f"agent {__version__}" in captured.out


def test_cli_module_entry_version() -> None:
    """python -m agent.cli --version 应输出版本号。"""
    result = subprocess.run(
        [sys.executable, "-m", "agent.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"agent {__version__}" in result.stdout


def test_cli_run_echo_plain(capsys: pytest.CaptureFixture[str]) -> None:
    """--plain --echo 模式输出纯文本结果。"""
    assert main(["--plain", "run", "--echo", "hello"]) == 0
    captured = capsys.readouterr()
    assert "You said: hello" in captured.out
    assert not _has_ansi(captured.out)


def test_cli_run_echo_rich(capsys: pytest.CaptureFixture[str]) -> None:
    """Rich 模式下 run --echo 应输出带标题的面板。"""
    assert main(["run", "--echo", "hello"]) == 0
    captured = capsys.readouterr()
    assert "Agent 结果" in captured.out
    assert "You said: hello" in captured.out


def test_cli_run_missing_api_key_plain(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--plain 模式下未提供 API key 时应优雅退出并提示。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    exit_code = main(["--plain", "run", "hello"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "OPENAI_API_KEY" in captured.err
    assert not _has_ansi(captured.err)


def test_cli_run_missing_api_key_rich(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rich 模式下未提供 API key 时应输出错误面板。"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    exit_code = main(["run", "hello"])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "错误" in captured.err
    assert "OPENAI_API_KEY" in captured.err


def test_cli_config_default_plain(capsys: pytest.CaptureFixture[str]) -> None:
    """--plain config 应输出纯文本默认配置摘要。"""
    assert main(["--plain", "config"]) == 0
    captured = capsys.readouterr()
    assert "model:" in captured.out
    assert "gpt-4o" in captured.out
    assert "max_turns:" in captured.out
    assert not _has_ansi(captured.out)


def test_cli_config_default_rich(capsys: pytest.CaptureFixture[str]) -> None:
    """Rich 模式下 config 应输出表格标题与关键配置。"""
    assert main(["config"]) == 0
    captured = capsys.readouterr()
    assert "当前配置摘要" in captured.out
    assert "gpt-4o" in captured.out


def test_cli_config_with_file_plain(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--plain config --config 应正确加载 YAML 并显示其中配置。"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "llm:\n  model: deepseek-chat\nagent:\n  max_turns: 10\n",
        encoding="utf-8",
    )

    assert main(["--plain", "config", "--config", str(config_path)]) == 0
    captured = capsys.readouterr()
    assert "deepseek-chat" in captured.out
    assert "max_turns: 10" in captured.out
    assert not _has_ansi(captured.out)


def test_cli_config_missing_file_plain(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--plain config --config 指向不存在的文件时应返回非 0 并提示。"""
    config_path = tmp_path / "missing.yaml"

    exit_code = main(["--plain", "config", "--config", str(config_path)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "配置加载失败" in captured.err
    assert not _has_ansi(captured.err)


def test_cli_config_missing_file_rich(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Rich 模式下 config 加载失败应输出错误面板。"""
    config_path = tmp_path / "missing.yaml"

    exit_code = main(["config", "--config", str(config_path)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "错误" in captured.err
    assert "配置加载失败" in captured.err


def test_cli_config_malformed_yaml_plain(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """--plain config --config 指向损坏的 YAML 时应返回非 0 并提示。"""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("llm: [unclosed", encoding="utf-8")

    exit_code = main(["--plain", "config", "--config", str(config_path)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "配置加载失败" in captured.err
    assert not _has_ansi(captured.err)


def test_cli_config_malformed_yaml_rich(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Rich 模式下 config 加载损坏 YAML 应输出错误面板。"""
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("llm: [unclosed", encoding="utf-8")

    exit_code = main(["config", "--config", str(config_path)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "错误" in captured.err
    assert "配置加载失败" in captured.err


def test_cli_load_config_override() -> None:
    """CLI 参数应覆盖 YAML 配置默认值。"""
    args = argparse.Namespace(
        config_path=None,
        model="deepseek-chat",
        api_key=None,
        base_url=None,
        temperature=None,
        max_turns=5,
        backend=None,
    )
    config = _load_config(args)
    assert config.llm.model == "deepseek-chat"
    assert config.agent.max_turns == 5


def test_cli_load_config_yaml_override(
    tmp_path: Path,
) -> None:
    """CLI 参数应覆盖 YAML 文件中已指定的值。"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "llm:\n  model: gpt-4o\nagent:\n  max_turns: 20\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        config_path=str(config_path),
        model="deepseek-chat",
        api_key=None,
        base_url=None,
        temperature=None,
        max_turns=5,
        backend=None,
    )
    config = _load_config(args)
    assert config.llm.model == "deepseek-chat"
    assert config.agent.max_turns == 5


class TestLoadConfigEnvPriority:
    """EVAL-012：_load_config 的环境变量优先级。"""

    def test_env_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """环境变量覆盖代码默认值。"""
        import argparse

        from agent.cli.agent_cli import _load_config

        monkeypatch.setenv("OPENAI_MODEL", "deepseek-chat")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        args = argparse.Namespace(config_path=None, model=None, api_key=None,
                                  base_url=None, temperature=None, max_turns=None)
        config = _load_config(args)
        assert config.llm.model == "deepseek-chat"
        assert config.llm.base_url == "https://api.deepseek.com/v1"

    def test_cli_flag_beats_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI 旗标优先级高于环境变量。"""
        import argparse

        from agent.cli.agent_cli import _load_config

        monkeypatch.setenv("OPENAI_MODEL", "deepseek-chat")
        args = argparse.Namespace(config_path=None, model="gpt-4o-mini", api_key=None,
                                  base_url=None, temperature=None, max_turns=None)
        config = _load_config(args)
        assert config.llm.model == "gpt-4o-mini"
