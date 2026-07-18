"""验证 examples/ 目录下的示例脚本可导入、可运行。

设计原则：
  1. 示例是用户学习的第一入口，不能腐烂。
  2. 测试只验证示例能正常导入和运行，不严格断言 LLM 输出内容
     （因为 EchoClient 的输出可能随实现变化）。
  3. 不依赖真实 Docker 或真实 LLM API key。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from agent.config import AgentConfig, load_config

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _import_example(module_name: str) -> ModuleType:
    """按模块名导入 examples/ 下的脚本。

    参数：
        module_name: 示例脚本文件名（不含 .py）。

    返回：
        导入后的模块对象。
    """
    file_path = EXAMPLES_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader = spec.loader
    assert loader is not None
    loader.exec_module(module)
    return module


@pytest.mark.parametrize("module_name", ["simple_agent", "run_once", "with_config"])
def test_example_imports(module_name: str) -> None:
    """每个示例脚本都能被正常导入，不抛异常。"""
    module = _import_example(module_name)
    assert hasattr(module, "main")


@pytest.mark.asyncio
async def test_simple_agent_runs() -> None:
    """simple_agent 的 main() 可运行并返回回复。"""
    module = _import_example("simple_agent")
    result = await module.main()
    # main 没有返回值，重点是不抛异常。
    assert result is None


@pytest.mark.asyncio
async def test_run_once_runs() -> None:
    """run_once 的 main() 可运行并返回回复。"""
    module = _import_example("run_once")
    result = await module.main()
    assert result is None


@pytest.mark.asyncio
async def test_with_config_runs() -> None:
    """with_config 的 main() 可运行并正确加载配置。"""
    module = _import_example("with_config")
    result = await module.main()
    assert result is None


def test_example_config_loads() -> None:
    """examples/config.yaml 能被 load_config 正确解析。"""
    config_path = EXAMPLES_DIR / "config.yaml"
    config = load_config(config_path)
    assert isinstance(config, AgentConfig)
    assert config.llm.provider == "openai"
    assert config.llm.model == "gpt-4o"
    assert config.agent.max_turns == 10
    assert config.sandbox.backend == "docker"
    assert config.tools.enabled == ["sandbox_exec", "finish"]
