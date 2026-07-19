"""pytest 全局夹具：保证测试套件对宿主机 OPENAI_* 环境变量免疫。"""

from __future__ import annotations

import pytest

_OPENAI_ENV_VARS: tuple[str, ...] = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")


@pytest.fixture(autouse=True)
def _clean_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理宿主机 OPENAI_* 环境变量，使测试默认走 EchoClient / 默认配置路径。

    需要真实环境变量的用例可在测试体内自行 monkeypatch.setenv（先清后设，顺序兼容）。
    真实 LLM 联调请使用独立通道 examples/e2e_suite.py（不经本夹具）。
    """
    for var in _OPENAI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
