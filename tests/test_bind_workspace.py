"""TD-015 单元 C：host_dir（bind）工作区模式测试。

覆盖 §4.6 可自动化条目：
  - 工厂接线：docker + host_dir → workspace_bind 挂载参数；Docker 不可用
    时明确报错不降级；subprocess + host_dir → workspace_root 透传；
  - DockerSandboxBackend bind 模式容器参数：bind 挂载、uid 双模、HOME=/tmp、
    跳过 chown、加固维持（read_only/tmpfs/network=none）；
  - 装配层 _prepare_bind_workspace：git 快照调用、审批/安全件默认生效、
    显式关闭 warning、启动横幅；
  - 敏感文件 read deny（优先级 90）注入与拦截；
  - 非交互（无 TTY）审批回调默认拒写；
  - Web 入口 host_dir + 审批未显式关闭 → 拒绝启动并报错引导。

Docker 相关路径全部 mock，不依赖真实 Docker daemon。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent.cli import agent_cli
from agent.config import AgentConfig, SandboxConfig
from agent.core.types import ToolCall
from agent.llm import EchoClient
from agent.sandbox import create_sandbox_backend
from agent.sandbox.docker_backend import DockerSandboxBackend
from agent.sandbox.subprocess_backend import SubprocessSandboxBackend


def _bind_config(host_dir: str, backend: str = "docker") -> AgentConfig:
    """构造 bind 模式的 AgentConfig（测试辅助）。"""
    config = AgentConfig()
    config.sandbox.backend = backend
    config.sandbox.host_dir = host_dir
    return config


class TestFactoryBindWiring:
    """create_sandbox_backend 的 bind 模式接线。"""

    def test_docker_host_dir_creates_bind_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """docker + host_dir → workspace_bind 透传且不清理宿主目录。"""
        monkeypatch.setattr("agent.sandbox._docker_available", lambda backend: True)
        backend = create_sandbox_backend(SandboxConfig(backend="docker", host_dir="D:/proj"))

        assert isinstance(backend, DockerSandboxBackend)
        assert backend.workspace_bind == "D:/proj"
        assert backend.cleanup_workspace is False
        backend.close()

    def test_docker_host_dir_unavailable_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Docker 不可用 + host_dir → 明确报错，不降级 subprocess。"""
        monkeypatch.setattr("agent.sandbox._docker_available", lambda backend: False)
        with pytest.raises(ValueError, match="Docker"):
            create_sandbox_backend(SandboxConfig(backend="docker", host_dir="D:/proj"))

    def test_subprocess_host_dir_uses_workspace_root(self, tmp_path: Path) -> None:
        """subprocess + host_dir（显式 opt-in）→ workspace_root 指向宿主目录。"""
        backend = create_sandbox_backend(
            SandboxConfig(backend="subprocess", host_dir=str(tmp_path))
        )

        assert isinstance(backend, SubprocessSandboxBackend)
        assert backend.workspace == str(tmp_path)
        backend.close()
        # 外部目录不属于后端资产，close 不删除。
        assert tmp_path.exists()


class _FakeContainer:
    """记录 exec_run 调用的 Mock 容器。"""

    def __init__(self) -> None:
        self.exec_calls: list[dict[str, Any]] = []
        self.id = "fake-container-id"

    def start(self) -> None:
        """no-op。"""

    def exec_run(self, cmd: str, user: str | None = None) -> tuple[int, bytes]:
        """记录调用并返回成功。"""
        self.exec_calls.append({"cmd": cmd, "user": user})
        return 0, b""


def _make_bind_backend(host_dir: str) -> tuple[DockerSandboxBackend, MagicMock, _FakeContainer]:
    """构造 client/container 均被 mock 的 bind 模式后端（测试辅助）。"""
    backend = DockerSandboxBackend(workspace_bind=host_dir, cleanup_workspace=False)
    client = MagicMock()
    container = _FakeContainer()
    client.containers.create.return_value = container
    backend._client = client
    return backend, client, container


class TestDockerBackendBindContainer:
    """bind 模式容器创建参数。"""

    def test_bind_volume_replaces_named_volume(self) -> None:
        """bind 模式用宿主路径挂载 /workspace，替代命名卷。"""
        backend, client, _ = _make_bind_backend("/host/proj")

        asyncio.run(backend._do_create_container())

        kwargs = client.containers.create.call_args.kwargs
        assert kwargs["volumes"] == {"/host/proj": {"bind": "/workspace", "mode": "rw"}}
        assert kwargs["network_mode"] == "none"
        assert kwargs["read_only"] is True
        assert kwargs["tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=64m"}
        assert "privileged" not in kwargs
        assert kwargs["environment"] == {"HOME": "/tmp"}

    def test_bind_skips_chown(self) -> None:
        """bind 模式跳过 chown 65534（不篡改宿主文件属主）。"""
        backend, _, container = _make_bind_backend("/host/proj")

        asyncio.run(backend._do_create_container())

        assert container.exec_calls == []

    def test_bind_user_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POSIX → 宿主 uid:gid；Windows → 维持 nobody。"""
        import types

        backend, client, _ = _make_bind_backend("/host/proj")
        fake_posix_os = types.SimpleNamespace(
            name="posix", getuid=lambda: 1000, getgid=lambda: 1001
        )
        monkeypatch.setattr("agent.sandbox.docker_backend.os", fake_posix_os)

        asyncio.run(backend._do_create_container())
        assert client.containers.create.call_args.kwargs["user"] == "1000:1001"

        backend2, client2, _ = _make_bind_backend("/host/proj")
        monkeypatch.setattr(
            "agent.sandbox.docker_backend.os", types.SimpleNamespace(name="nt")
        )

        asyncio.run(backend2._do_create_container())
        assert client2.containers.create.call_args.kwargs["user"] == "nobody"

    def test_named_volume_mode_unchanged(self) -> None:
        """非 bind 模式维持原语义：命名卷 + chown 65534。"""
        backend = DockerSandboxBackend(workspace_volume="litmus-ws-x")
        client = MagicMock()
        container = _FakeContainer()
        client.containers.create.return_value = container
        backend._client = client

        asyncio.run(backend._do_create_container())

        kwargs = client.containers.create.call_args.kwargs
        assert kwargs["volumes"] == {"litmus-ws-x": {"bind": "/workspace", "mode": "rw"}}
        assert kwargs["user"] == "nobody"
        assert "environment" not in kwargs
        assert any("chown" in c["cmd"] for c in container.exec_calls)
        backend.close()


class TestPrepareBindWorkspace:
    """装配层 _prepare_bind_workspace 的安全件推导与横幅。"""

    def _patch_guard(self, monkeypatch: pytest.MonkeyPatch, sha: str | None) -> list[str]:
        """mock git 校验与快照（打在 workspace_guard 源模块上，共享装配仍真实执行），
        返回调用记录。"""
        calls: list[str] = []
        monkeypatch.setattr(
            "agent.cli.workspace_guard.ensure_git_workspace",
            lambda d: calls.append(f"ensure:{d}"),
        )
        monkeypatch.setattr(
            "agent.cli.workspace_guard.snapshot_workspace",
            lambda d: calls.append(f"snap:{d}") or sha,
        )
        return calls

    def test_defaults_turn_on_approval_and_security(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """bind 模式未显式配置时：快照执行、审批与安全件按 True 生效、横幅含 sha。"""
        calls = self._patch_guard(monkeypatch, sha="abc123")
        config = _bind_config("D:/proj")

        agent_cli._prepare_bind_workspace(config, plain=True)

        assert calls == ["ensure:D:/proj", "snap:D:/proj"]
        assert config.agent.human_approval.enabled is True
        assert config.agent.human_approval.tools == ["file_write", "file_edit"]
        assert config.security.enabled is True
        assert config.security.bind_read_deny is True
        banner = capsys.readouterr().out
        assert "D:/proj" in banner
        assert "abc123" in banner
        assert "reset --hard abc123" in banner

    def test_explicit_approval_off_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """显式 human_approval.enabled: false → 尊重配置并打 warning。"""
        self._patch_guard(monkeypatch, sha=None)
        config = _bind_config("D:/proj")
        config.agent.human_approval.enabled = False

        with caplog.at_level(logging.WARNING, logger="agent.cli.agent_cli"):
            agent_cli._prepare_bind_workspace(config, plain=True)

        assert config.agent.human_approval.enabled is False
        assert any("human_approval" in r.message for r in caplog.records)

    def test_explicit_security_off_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """显式 security.enabled: false → 尊重配置并打 warning，不注入 read deny。"""
        self._patch_guard(monkeypatch, sha=None)
        config = _bind_config("D:/proj")
        config.security.enabled = False

        with caplog.at_level(logging.WARNING, logger="agent.cli.agent_cli"):
            agent_cli._prepare_bind_workspace(config, plain=True)

        assert config.security.bind_read_deny is False
        assert any("security" in r.message for r in caplog.records)

    def test_guard_failure_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """git 校验失败的 ValueError 原样上抛（CLI 走友好报错）。"""
        monkeypatch.setattr(
            "agent.cli.workspace_guard.ensure_git_workspace",
            lambda d: (_ for _ in ()).throw(ValueError("不是 git 仓库")),
        )
        config = _bind_config("D:/proj")

        with pytest.raises(ValueError, match="不是 git 仓库"):
            agent_cli._prepare_bind_workspace(config, plain=True)


class TestBindReadDeny:
    """保险三：bind 模式敏感文件 read deny（优先级 90）。"""

    def _engine(self) -> Any:
        """构建 bind 模式默认规则集引擎。"""
        config = AgentConfig()
        config.security.enabled = True
        config.security.bind_read_deny = True
        engine = config.security.build_policy_engine()
        assert engine is not None
        return engine

    @pytest.mark.parametrize(
        "path",
        [
            "/workspace/.env",
            "/workspace/config/.env.local",
            "/workspace/.ssh/id_rsa",
            "/workspace/certs/server.pem",
            "/workspace/certs/server.key",
            "/workspace/.git/config",
            "/workspace/sub/id_rsa_backup",
        ],
    )
    def test_sensitive_paths_denied(self, path: str) -> None:
        """敏感路径 read 被 deny。"""
        decision = self._engine().evaluate("file/path", "read", path.lower())
        assert decision.action.value == "deny", path

    def test_normal_project_file_readable(self) -> None:
        """普通项目文件 read 不被拦截（read 无 catch-all）。"""
        decision = self._engine().evaluate("file/path", "read", "/workspace/src/main.py")
        assert decision.action.value == "allow"

    def test_bind_deny_not_injected_without_flag(self) -> None:
        """未开启 bind_read_deny 时 .env 等不被默认规则集拦截。"""
        config = AgentConfig()
        config.security.enabled = True
        engine = config.security.build_policy_engine()
        assert engine is not None
        decision = engine.evaluate("file/path", "read", "/workspace/.env")
        assert decision.action.value == "allow"


class TestNonInteractiveDeny:
    """保险二：非交互（无 TTY）场景审批回调默认拒写。"""

    def test_non_tty_approval_denies_write(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """无 TTY 时 file_write 被默认拒绝，拒绝原因回传 LLM（ToolResult）。"""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        config = _bind_config(str(tmp_path), backend="subprocess")
        config.agent.human_approval.enabled = True

        agent = agent_cli._build_agent(config, EchoClient())

        result = asyncio.run(
            agent.tools.execute(
                ToolCall(id="t1", name="file_write", arguments={"path": "/workspace/a.txt"})
            )
        )

        assert result.success is False
        assert "拒绝" in result.content
        agent.close()

    def test_tty_approval_callback_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """交互 TTY 下使用 y/n/a 确认回调（'a' 后会话内免确认）。"""
        from agent.cli.chat import make_cli_approval_callback

        callback = make_cli_approval_callback({"file_write"}, plain=True)
        monkeypatch.setattr("builtins.input", lambda prompt="": "a")

        assert callback("file_write", {"path": "/workspace/a"}) is True
        # 'a' 后同工具免确认。
        assert callback("file_write", {"path": "/workspace/b"}) is True


class TestCliBindEntry:
    """CLI run 入口的 bind 校验失败友好报错。"""

    def test_run_bind_guard_failure_friendly_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """host_dir 校验失败 → 退出码 1 且走 render_error，不裸 traceback。"""
        monkeypatch.setattr(
            "agent.cli.workspace_guard.ensure_git_workspace",
            lambda d: (_ for _ in ()).throw(ValueError("host_dir 不是 git 仓库")),
        )
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"sandbox:\n  backend: subprocess\n  host_dir: {tmp_path}\n",
            encoding="utf-8",
        )

        exit_code = agent_cli.main(
            ["--plain", "run", "--config", str(config_file), "--echo", "hi"]
        )
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "bind 工作区校验失败" in captured.err
        assert "Traceback" not in captured.out + captured.err


class TestWebBindRefusal:
    """保险二 Web 侧：host_dir + 审批未显式关闭 → 拒绝启动并报错引导。"""

    def test_web_refuses_bind_without_explicit_approval_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Web + host_dir + 审批未显式关闭 → /api/chat 返回 400 与引导信息。"""
        from fastapi.testclient import TestClient

        from agent.web import app as web_app

        monkeypatch.setattr(web_app, "_load_web_config", lambda: _bind_config("D:/proj"))
        web_app._sessions.clear()

        with TestClient(web_app.app) as client:
            resp = client.post("/api/chat/s1", json={"message": "hi"})

        assert resp.status_code == 400
        assert "human_approval" in resp.json()["detail"]

    def test_web_allows_bind_with_explicit_approval_off(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """显式 human_approval.enabled: false → Web 放行（风险自担），
        且放行路径同样强制执行 git 校验/快照与 security 默认推导。"""
        from fastapi.testclient import TestClient

        from agent.web import app as web_app

        guard_calls: list[str] = []
        monkeypatch.setattr(
            "agent.cli.workspace_guard.ensure_git_workspace",
            lambda d: guard_calls.append(f"ensure:{d}"),
        )
        monkeypatch.setattr(
            "agent.cli.workspace_guard.snapshot_workspace",
            lambda d: guard_calls.append(f"snap:{d}") or "websha",
        )
        config = _bind_config(str(tmp_path), backend="subprocess")
        config.agent.human_approval.enabled = False
        monkeypatch.setattr(web_app, "_load_web_config", lambda: config)
        web_app._sessions.clear()

        with TestClient(web_app.app, raise_server_exceptions=False) as client:
            resp = client.post("/api/chat/s2", json={"message": "hi"})

        assert resp.status_code == 200
        # 回炉修复：Web 放行路径与 CLI 同一份 apply_bind_safeguards。
        assert guard_calls == [f"ensure:{tmp_path}", f"snap:{tmp_path}"]
        assert config.security.enabled is True
        assert config.security.bind_read_deny is True

    def test_web_bind_guard_failure_returns_400(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Web 放行路径 git 校验失败 → 400 且报错含原因，不裸 500。"""
        from fastapi.testclient import TestClient

        from agent.web import app as web_app

        monkeypatch.setattr(
            "agent.cli.workspace_guard.ensure_git_workspace",
            lambda d: (_ for _ in ()).throw(ValueError("host_dir 必须是 git 仓库根目录")),
        )
        config = _bind_config(str(tmp_path), backend="subprocess")
        config.agent.human_approval.enabled = False
        monkeypatch.setattr(web_app, "_load_web_config", lambda: config)
        web_app._sessions.clear()

        with TestClient(web_app.app) as client:
            resp = client.post("/api/chat/s3", json={"message": "hi"})

        assert resp.status_code == 400
        assert "git 仓库根目录" in resp.json()["detail"]


class TestBindBannerNonTTY:
    """保险四横幅：非 TTY 时如实标注"写操作默认拒绝"，不展示 y/n/a。"""

    def test_non_tty_banner_says_deny_by_default(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """非 TTY（管道）→ 文案为"非交互：写操作默认拒绝"。"""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        agent_cli._render_bind_banner("D:/proj", "abc123", approval_on=True, plain=True)

        banner = capsys.readouterr().out
        assert "非交互：写操作默认拒绝" in banner
        assert "y/n/a" not in banner

    def test_tty_banner_shows_interaction_hint(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """交互 TTY → 文案保留 y/n/a 提示。"""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        agent_cli._render_bind_banner("D:/proj", None, approval_on=True, plain=True)

        banner = capsys.readouterr().out
        assert "y/n/a" in banner


class TestReadDenyNormalizationChain:
    """归一化链路：未归一化输入（反斜杠/大写）走完整 _evaluate_parametric_policy。"""

    def _registry(self) -> Any:
        """构建 bind 模式默认规则集引擎并装配 ToolRegistry。"""
        from agent.core.engine import ToolRegistry

        config = AgentConfig()
        config.security.enabled = True
        config.security.bind_read_deny = True
        engine = config.security.build_policy_engine()
        assert engine is not None
        return ToolRegistry(policy=engine)

    @pytest.mark.parametrize(
        "path",
        [
            "/workspace\\.ENV",
            "/workspace\\config\\.Env.Local",
            "/workspace/CONFIG/.ENV",
            "/workspace\\.SSH\\id_rsa",
            "/workspace/certs/SERVER.PEM",
            "/workspace/.GIT/CONFIG",
            "/workspace\\Sub\\ID_RSA_backup",
        ],
    )
    def test_unnormalized_sensitive_paths_denied(self, path: str) -> None:
        """反斜杠/大写等未归一化输入在完整链路内仍被 read deny。"""
        registry = self._registry()
        call = ToolCall(id="t1", name="file_read", arguments={"path": path})

        decision = registry._evaluate_parametric_policy(call)

        assert decision is not None
        assert decision.action.value == "deny", path

    def test_unnormalized_normal_file_allowed(self) -> None:
        """未归一化的普通项目文件不误伤。"""
        registry = self._registry()
        call = ToolCall(
            id="t1", name="file_read", arguments={"path": "/workspace\\SRC\\Main.PY"}
        )

        decision = registry._evaluate_parametric_policy(call)

        assert decision is not None
        assert decision.action.value == "allow"


class TestSearchToolsSensitiveFilter:
    """defense-in-depth：grep/glob 内嵌脚本硬编码跳过敏感文件。

    策略层只能看到工具的 path 参数，看不到遍历枚举出的每个文件，因此
    脚本内再按与 read deny 同口径的 5 类模式过滤。用真实 subprocess
    后端 + tmp_path 文件树验证（不依赖 Docker/git）。
    """

    def _populate(self, root: Path) -> None:
        """构造含敏感文件与正常文件的目录树。"""
        (root / ".env").write_text("API_TOKEN=topsecret\n", encoding="utf-8")
        (root / "config").mkdir()
        (root / "config" / ".env.local").write_text("TOKEN=topsecret\n", encoding="utf-8")
        (root / ".ssh").mkdir()
        (root / ".ssh" / "id_rsa").write_text("PRIVATE topsecret\n", encoding="utf-8")
        (root / "certs").mkdir()
        (root / "certs" / "server.pem").write_text("CERT topsecret\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("[core] topsecret\n", encoding="utf-8")
        (root / "id_rsa_backup").write_text("topsecret\n", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("token = 1\n", encoding="utf-8")

    def test_grep_skips_sensitive_files(self, tmp_path: Path) -> None:
        """grep 命中内容时敏感文件不出现在结果中，正常文件不受影响。"""
        from agent.tools.grep import grep

        self._populate(tmp_path)
        backend = SubprocessSandboxBackend(workspace_root=str(tmp_path))

        result = asyncio.run(
            grep("topsecret", str(tmp_path), backend=backend)
        )

        assert result.success
        # 敏感文件（.env/.ssh/pem/id_rsa/.git）不出现在匹配结果中。
        # 注：不断言 "topsecret" 不出现——subprocess 后端的 _exec_*.py
        # 脚本本身含 pattern 字符串，会被遍历命中（属测试环境噪音，非泄露）。
        for sensitive in (".env", ".ssh", "server.pem", "id_rsa", ".git"):
            assert sensitive not in result.content
        normal = asyncio.run(grep("token = 1", str(tmp_path), backend=backend))
        assert normal.success
        assert "main.py" in normal.content
        backend.close()

    def test_grep_single_sensitive_file_returns_no_match(self, tmp_path: Path) -> None:
        """path 直指敏感文件（策略层会拦截，此为脚本内兜底）时不泄露内容。"""
        from agent.tools.grep import grep

        self._populate(tmp_path)
        backend = SubprocessSandboxBackend(workspace_root=str(tmp_path))

        result = asyncio.run(
            grep("topsecret", str(tmp_path / ".env"), backend=backend)
        )

        assert result.success
        assert "topsecret" not in result.content
        backend.close()

    def test_glob_filters_sensitive_files(self, tmp_path: Path) -> None:
        """glob 递归枚举时敏感文件被过滤，正常文件保留。"""
        from agent.tools.glob import glob

        self._populate(tmp_path)
        backend = SubprocessSandboxBackend(workspace_root=str(tmp_path))

        result = asyncio.run(glob("**/*", str(tmp_path), backend=backend))

        assert result.success
        assert "main.py" in result.content
        for sensitive in (".env", ".ssh", ".pem", "id_rsa", ".git"):
            assert sensitive not in result.content
        backend.close()
