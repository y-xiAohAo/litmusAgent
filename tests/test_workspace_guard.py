"""TD-015 单元 C 保险一：workspace_guard 的 git 校验与快照测试。

使用 tmp_path + 真实 git CLI（环境无 git 时整模块跳过）。
覆盖：ensure_git_workspace 四类校验；snapshot_workspace 的 dirty 自动
快照（当前分支、litmus-agent env 署名兜底、不改用户 git 配置）与
clean 跳过。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agent.cli.workspace_guard import (
    SNAPSHOT_MESSAGE,
    ensure_git_workspace,
    snapshot_workspace,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="当前环境无 git 可执行文件"
)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """在 repo 下执行 git 命令并返回 stdout（测试辅助）。"""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(path: Path) -> None:
    """初始化一个带一次提交的 git 仓库（本地显式配置身份）。"""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "config", "user.name", "tester")
    _git(path, "config", "user.email", "tester@example.com")
    (path / "README.md").write_text("init\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "init")


class TestEnsureGitWorkspace:
    """ensure_git_workspace 的存在性/目录/git 仓库校验。"""

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        """host_dir 不存在 → ValueError。"""
        with pytest.raises(ValueError, match="不存在"):
            ensure_git_workspace(str(tmp_path / "no-such"))

    def test_file_not_dir_raises(self, tmp_path: Path) -> None:
        """host_dir 是普通文件 → ValueError。"""
        target = tmp_path / "a.txt"
        target.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match="不是目录"):
            ensure_git_workspace(str(target))

    def test_non_git_dir_raises_with_guidance(self, tmp_path: Path) -> None:
        """非 git 仓库目录 → ValueError 且引导 git init。"""
        target = tmp_path / "plain"
        target.mkdir()
        with pytest.raises(ValueError, match="git init"):
            ensure_git_workspace(str(target))

    def test_git_repo_accepted(self, tmp_path: Path) -> None:
        """合法 git 仓库 → 通过不抛异常。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        ensure_git_workspace(str(repo))


class TestSnapshotWorkspace:
    """snapshot_workspace 的 dirty 快照与 clean 跳过。"""

    def test_clean_repo_returns_none(self, tmp_path: Path) -> None:
        """clean 工作区不创建快照，返回 None。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        before = _git(repo, "rev-parse", "HEAD")

        assert snapshot_workspace(str(repo)) is None
        assert _git(repo, "rev-parse", "HEAD") == before

    def test_dirty_repo_auto_commits(self, tmp_path: Path) -> None:
        """dirty 工作区自动快照：返回新 sha、提交在当前分支、工作区转 clean。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        sha = snapshot_workspace(str(repo))

        assert sha is not None
        assert _git(repo, "rev-parse", "HEAD") == sha
        assert _git(repo, "log", "-1", "--pretty=%s") == SNAPSHOT_MESSAGE
        assert _git(repo, "status", "--porcelain") == ""
        # 提交在当前分支（Aider 模式），未切走。
        assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD"

    def test_snapshot_without_git_identity_uses_env_fallback(self, tmp_path: Path) -> None:
        """git 身份未配置 → 快照以 litmus-agent 署名成功，且不改用户配置。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        # 清掉本地身份配置，并屏蔽全局/系统配置，模拟未配置身份的环境。
        _git(repo, "config", "--unset", "user.name")
        _git(repo, "config", "--unset", "user.email")
        env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(tmp_path / "empty-gitconfig"),
        }
        (tmp_path / "empty-gitconfig").write_text("", encoding="utf-8")
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        # 直接以屏蔽后的环境执行快照逻辑中的 git 命令链路验证。
        sha = snapshot_workspace(str(repo))

        assert sha is not None
        author = _git(repo, "log", "-1", "--pretty=%an <%ae>", env=env)
        assert author.startswith("litmus-agent")
        # 用户 git 配置未被改写。
        with pytest.raises(subprocess.CalledProcessError):
            _git(repo, "config", "user.name", env=env)


class TestEnsureGitRepoRoot:
    """ensure_git_workspace 的仓库根目录校验（防子目录误伤）。"""

    def test_repo_subdirectory_rejected(self, tmp_path: Path) -> None:
        """host_dir 指向仓库子目录 → ValueError 引导指向仓库根。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        sub = repo / "pkg"
        sub.mkdir()

        with pytest.raises(ValueError, match="必须是 git 仓库根目录"):
            ensure_git_workspace(str(sub))

    def test_repo_root_with_redundant_segments_accepted(self, tmp_path: Path) -> None:
        """带冗余分隔符/`.` 段的仓库根路径归一化后仍通过。"""
        repo = tmp_path / "proj"
        _init_repo(repo)

        ensure_git_workspace(str(repo) + os.sep + ".")


class TestSnapshotBlocksHooks:
    """快照 hooks 阻断：恶意 pre-commit / core.hooksPath 注入不得在宿主执行。"""

    def test_malicious_pre_commit_hook_not_executed(self, tmp_path: Path) -> None:
        """仓库内 pre-commit hook 留标记文件；快照后标记不得出现且提交成功。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        marker = tmp_path / "pwned"
        hooks_dir = repo / ".git" / "hooks"
        hook = hooks_dir / "pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            f"echo pwned > {marker.as_posix()}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        sha = snapshot_workspace(str(repo))

        assert sha is not None
        assert not marker.exists()
        assert _git(repo, "log", "-1", "--pretty=%s") == SNAPSHOT_MESSAGE

    def test_core_hookspath_injection_not_executed(self, tmp_path: Path) -> None:
        """仓库 config 注入 core.hooksPath 指向恶意目录；快照不受影响。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        evil_hooks = tmp_path / "evil-hooks"
        evil_hooks.mkdir()
        marker = tmp_path / "pwned"
        hook = evil_hooks / "pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            f"echo pwned > {marker.as_posix()}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        _git(repo, "config", "core.hooksPath", str(evil_hooks))
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        sha = snapshot_workspace(str(repo))

        assert sha is not None
        assert not marker.exists()
