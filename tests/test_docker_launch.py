"""验证 Docker 一键启动脚本的功能。

设计原则：
  1. 不依赖真实 Docker daemon，所有 Docker 调用使用 Mock。
  2. 测试覆盖正常路径与异常路径。
  3. 验证 docker-compose.yml 是合法 YAML。
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


def _import_setup_docker() -> ModuleType:
    """动态导入 setup-docker.py 脚本。

    返回：
        导入后的模块对象。
    """
    import importlib.util

    file_path = Path(__file__).parent.parent / "scripts" / "setup-docker.py"
    spec = importlib.util.spec_from_file_location("setup_docker", file_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    loader.exec_module(module)
    return module


@pytest.fixture
def setup_docker() -> ModuleType:
    """提供已导入的 setup-docker 模块。"""
    return _import_setup_docker()


class TestCheckDockerAvailable:
    """测试 Docker daemon 可达性检查。"""

    def test_returns_true_when_ping_succeeds(self, setup_docker: ModuleType) -> None:
        """Docker daemon 可达时返回 True。"""
        client = MagicMock()
        client.ping.return_value = True
        assert setup_docker.check_docker_available(client) is True

    def test_returns_false_when_ping_fails(self, setup_docker: ModuleType) -> None:
        """Docker daemon 不可达时返回 False。"""
        client = MagicMock()
        client.ping.side_effect = Exception("connection refused")
        assert setup_docker.check_docker_available(client) is False


class TestEnsureImage:
    """测试镜像检查与拉取。"""

    def test_returns_success_when_image_exists(self, setup_docker: ModuleType) -> None:
        """镜像已存在时直接返回成功。"""
        client = MagicMock()
        client.images.list.return_value = [MagicMock(tags=["python:3.11-slim"])]

        success, message = setup_docker.ensure_image("python:3.11-slim", client)
        assert success is True
        assert "已存在" in message
        client.images.pull.assert_not_called()

    def test_pulls_image_when_missing(self, setup_docker: ModuleType) -> None:
        """镜像不存在时尝试拉取并返回成功。"""
        client = MagicMock()
        client.images.list.return_value = []

        success, message = setup_docker.ensure_image("python:3.11-slim", client)
        assert success is True
        assert "拉取完成" in message
        client.images.pull.assert_called_once_with("python:3.11-slim")

    def test_returns_failure_when_pull_fails(self, setup_docker: ModuleType) -> None:
        """拉取失败时返回失败信息。"""
        client = MagicMock()
        client.images.list.return_value = []
        client.images.pull.side_effect = Exception("network error")

        success, message = setup_docker.ensure_image("python:3.11-slim", client)
        assert success is False
        assert "拉取失败" in message


class TestMain:
    """测试 CLI 入口 main()。"""

    def test_returns_zero_when_docker_ready(
        self, setup_docker: ModuleType, capsys: Any
    ) -> None:
        """Docker 就绪且镜像已存在时返回 0。"""
        client = MagicMock()
        client.ping.return_value = True
        client.images.list.return_value = [MagicMock(tags=["python:3.11-slim"])]

        with patch("docker.from_env", return_value=client):
            result = setup_docker.main([])

        assert result == 0
        captured = capsys.readouterr()
        assert "Docker daemon 已连接" in captured.out

    def test_returns_one_when_docker_unavailable(
        self, setup_docker: ModuleType, capsys: Any
    ) -> None:
        """Docker 不可达时返回 1 并提示。"""
        client = MagicMock()
        client.ping.side_effect = Exception("connection refused")

        with patch("docker.from_env", return_value=client):
            result = setup_docker.main([])

        assert result == 1
        captured = capsys.readouterr()
        assert "Docker daemon 未启动" in captured.err


class TestDockerCompose:
    """测试 docker-compose.yml 配置。"""

    def test_compose_file_is_valid_yaml(self) -> None:
        """docker-compose.yml 能被 yaml.safe_load 正确解析。"""
        compose_path = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_path.exists()

        with open(compose_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict)
        assert "services" in data
        assert "hermes" in data["services"]

        hermes = data["services"]["hermes"]
        assert hermes.get("image") == "python:3.11-slim"
        assert "volumes" in hermes
        assert hermes.get("working_dir") == "/app"
        assert "command" in hermes
        # 确保启动命令中包含 editable 安装
        command = hermes["command"]
        command_str = " ".join(command) if isinstance(command, list) else str(command)
        assert "pip install" in command_str and "-e" in command_str
