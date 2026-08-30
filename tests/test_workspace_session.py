"""TD-021：WorkspaceSession 快照栈与 /diff /undo 的测试。

使用 tmp_path + 真实 git CLI（环境无 git 时整模块跳过）。
覆盖 Spec §5 全部条目与同行评审修复（R1/R2/O1/O2/O3）：
  - /diff：stat + 新建文件清单 + 字节数；超长 diff 外迁到文件并提示路径；
    外迁临时文件由 cleanup() 清理（O3）；
  - /undo：已跟踪改动回滚 + 任务期间新建文件删除 + 栈弹出；新建目录
    （含嵌套）完整清理（R1，-uall + 空目录剪枝）；不误伤快照前已存在
    的 untracked 文件；栈空提示；HEAD 漂移警示；二次确认拒绝不动；
  - 基线在快照**之前**采集（R2），差集语义真实成立；任务期间"用户侧"
    新建的文件也进确认清单，文案统一为"任务期间新建文件"（诚实口径）；
  - 用户任务后修改过的新建文件 undo 不删（O1，内容哈希比对）；
  - 确认回调 fail-closed：EOF/中断按拒绝处理（O2）；
  - 代码中 git clean 零调用（grep 断言）；
  - 非 bind 模式命令不可用提示（chat 层）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent.cli.workspace_session import (
    DIFF_INLINE_LIMIT_BYTES,
    WorkspaceSession,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="当前环境无 git 可执行文件"
)


def _git(repo: Path, *args: str) -> str:
    """在 repo 下执行 git 命令并返回 stdout（测试辅助）。"""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
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


def _yes(_: str) -> bool:
    """确认桩：一律同意。"""
    return True


def _no(_: str) -> bool:
    """确认桩：一律拒绝。"""
    return False


def _make_session_with_task(repo: Path) -> WorkspaceSession:
    """构造会话并模拟一次任务：改已跟踪文件 + 新建一个 Agent 文件。"""
    session = WorkspaceSession(str(repo))
    session.begin_task()
    (repo / "README.md").write_text("modified by agent\n", encoding="utf-8")
    (repo / "agent_new.txt").write_text("created by agent\n", encoding="utf-8")
    session.end_task()
    return session


class TestSnapshotStack:
    """begin_task / end_task 的快照栈与 untracked 差集。"""

    def test_begin_task_pushes_snapshot(self, tmp_path: Path) -> None:
        """任务前快照入栈，sha 有效。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = WorkspaceSession(str(repo))
        snap = session.begin_task()
        assert len(session.snapshots) == 1
        assert snap.task_index == 1
        assert _git(repo, "rev-parse", "HEAD") == snap.sha

    def test_begin_task_dirty_commits_snapshot(self, tmp_path: Path) -> None:
        """任务前工作区 dirty → 快照 commit 后工作区 clean。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        (repo / "README.md").write_text("user edit\n", encoding="utf-8")
        session = WorkspaceSession(str(repo))
        session.begin_task()
        assert _git(repo, "status", "--porcelain") == ""

    def test_baseline_captured_before_snapshot(self, tmp_path: Path) -> None:
        """评审 R2：untracked 基线在快照前采集，快照的 add -A 不清空它。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        (repo / "user_scratch.txt").write_text("user\n", encoding="utf-8")
        session = WorkspaceSession(str(repo))
        session.begin_task()
        # 快照把 user_scratch.txt 卷进 commit（add -A），但基线仍记录着它。
        assert _git(repo, "status", "--porcelain") == ""
        assert session.snapshots[-1].baseline_untracked == ["user_scratch.txt"]

    def test_end_task_computes_new_files_real_path(self, tmp_path: Path) -> None:
        """任务后差集（真实路径）：快照前已有文件不计入，任务期间新建计入。

        口径诚实化（评审 R2）：任务期间用户侧新建的文件同样进清单，
        差集无法区分 Agent 与用户。
        """
        repo = tmp_path / "proj"
        _init_repo(repo)
        # 快照前已存在的 untracked 文件 → 进基线，不进差集。
        (repo / "user_scratch.txt").write_text("user\n", encoding="utf-8")
        session = WorkspaceSession(str(repo))
        session.begin_task()
        # 任务期间：Agent 新建 + 用户侧同时新建（不区分，都计入）。
        (repo / "agent_new.txt").write_text("agent\n", encoding="utf-8")
        (repo / "user_mid.txt").write_text("user mid\n", encoding="utf-8")
        session.end_task()
        new_files = session.snapshots[-1].new_files
        assert "agent_new.txt" in new_files
        assert "user_mid.txt" in new_files
        assert "user_scratch.txt" not in new_files
        # end_task 同时记录了内容哈希（O1 用户修改保护的比对基准）。
        assert set(session.snapshots[-1].new_file_hashes) == set(new_files)


class TestDiff:
    """/diff 报告。"""

    def test_empty_stack_hint(self, tmp_path: Path) -> None:
        """栈空 → 提示文本。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = WorkspaceSession(str(repo))
        assert "尚无可对比" in session.diff_report()

    def test_diff_shows_stat_and_new_files(self, tmp_path: Path) -> None:
        """任务后 /diff：含 stat、新建清单与字节数，短 diff 内联。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        report = session.diff_report()
        assert "README.md" in report  # stat 摘要
        assert "agent_new.txt" in report  # 新建清单
        assert "字节" in report
        assert "modified by agent" in report  # 短 diff 直接内联

    def test_long_diff_externalized(self, tmp_path: Path) -> None:
        """超长 diff（>8KB）外迁到临时文件并提示路径，不内联刷屏。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = WorkspaceSession(str(repo))
        session.begin_task()
        # 写入超过阈值的内容制造超长 diff。
        big = "x" * (DIFF_INLINE_LIMIT_BYTES + 1024)
        (repo / "README.md").write_text(big, encoding="utf-8")
        session.end_task()
        report = session.diff_report()
        assert "完整 diff 已写入" in report
        assert big not in report
        # 提示中的路径指向真实存在的文件，内容即完整 diff。
        marker = "完整 diff 已写入 "
        path_str = report.split(marker, 1)[1].split("（", 1)[0].strip()
        out_path = Path(path_str)
        assert out_path.is_file()
        assert big in out_path.read_text(encoding="utf-8")
        # 评审 O3：外迁文件已登记，cleanup() 后删除。
        assert out_path in session._temp_files
        session.cleanup()
        assert not out_path.exists()
        assert session._temp_files == []


class TestUndo:
    """/undo 回滚。"""

    def test_empty_stack_hint(self, tmp_path: Path) -> None:
        """栈空 → 提示无可回滚。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = WorkspaceSession(str(repo))
        assert "无可回滚" in session.undo(_yes)

    def test_undo_reverts_tracked_and_deletes_new_files(self, tmp_path: Path) -> None:
        """确认后：已跟踪改动回滚、新建文件删除、栈弹出。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        result = session.undo(_yes)
        assert "已回滚" in result
        assert (repo / "README.md").read_text(encoding="utf-8") == "init\n"
        assert not (repo / "agent_new.txt").exists()
        assert session.snapshots == []

    def test_undo_deletes_new_directories(self, tmp_path: Path) -> None:
        """评审 R1：新建目录（含嵌套路径）undo 后目录与文件都被删除。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        (repo / "src").mkdir()  # 已存在但未跟踪的父目录
        session = WorkspaceSession(str(repo))
        session.begin_task()
        # Agent 新建嵌套文件：src/feature/x.py（feature/ 是新目录）。
        new_file = repo / "src" / "feature" / "x.py"
        new_file.parent.mkdir(parents=True)
        new_file.write_text("print('hi')\n", encoding="utf-8")
        session.end_task()
        # -uall 使差集精确到文件而非 `?? src/` 目录条目。
        assert "src/feature/x.py" in session.snapshots[-1].new_files
        result = session.undo(_yes)
        assert "已回滚" in result
        assert not new_file.exists()
        assert not (repo / "src" / "feature").exists()  # 空父目录被剪枝
        assert not (repo / "src").exists()  # src 整个变空，同样清掉

    def test_undo_keeps_pre_snapshot_untracked(self, tmp_path: Path) -> None:
        """不误伤快照前已存在的 untracked 文件（真实基线路径，评审 R2）。

        快照前存在的 user_keep.txt 进基线并被快照 commit；undo 的
        reset --hard 回到快照后它仍在，且不在删除清单内。
        """
        repo = tmp_path / "proj"
        _init_repo(repo)
        (repo / "user_keep.txt").write_text("keep\n", encoding="utf-8")
        session = WorkspaceSession(str(repo))
        session.begin_task()
        (repo / "agent_new.txt").write_text("agent\n", encoding="utf-8")
        session.end_task()
        assert session.snapshots[-1].new_files == ["agent_new.txt"]
        session.undo(_yes)
        assert (repo / "user_keep.txt").read_text(encoding="utf-8") == "keep\n"
        assert not (repo / "agent_new.txt").exists()

    def test_undo_warns_on_missing_file_no_silent_skip(self, tmp_path: Path) -> None:
        """评审 R1：清单内文件已不存在时不静默跳过，进 [WARN] 告警清单。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        (repo / "agent_new.txt").unlink()  # 用户任务后自己删了
        result = session.undo(_yes)
        assert "已回滚" in result
        assert "[WARN]" in result
        assert "agent_new.txt" in result
        assert "已不存在" in result

    def test_undo_skips_user_modified_file(self, tmp_path: Path) -> None:
        """评审 O1（Spec §2.3-4）：任务后被用户修改的新建文件不删除。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        # 用户在任务结束后修改了 Agent 新建文件 → 哈希不一致 → 跳过。
        (repo / "agent_new.txt").write_text("user edited\n", encoding="utf-8")
        result = session.undo(_yes)
        assert "已回滚" in result
        assert (repo / "agent_new.txt").read_text(encoding="utf-8") == "user edited\n"
        assert "[WARN]" in result
        assert "未删除" in result

    def test_undo_second_confirm_reject_keeps_everything(self, tmp_path: Path) -> None:
        """二次确认拒绝 → 不做任何改动、不弹栈。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        result = session.undo(_no)
        assert "已取消" in result
        assert (repo / "README.md").read_text(encoding="utf-8") == "modified by agent\n"
        assert (repo / "agent_new.txt").exists()
        assert len(session.snapshots) == 1

    def test_undo_confirm_text_uses_honest_wording(self, tmp_path: Path) -> None:
        """评审 R2 文案：任务期间用户侧新建文件也进清单，称"任务期间新建"。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = WorkspaceSession(str(repo))
        session.begin_task()
        (repo / "user_mid.txt").write_text("user mid\n", encoding="utf-8")
        session.end_task()
        questions: list[str] = []

        def confirm(q: str) -> bool:
            questions.append(q)
            return False

        session.undo(confirm)
        assert len(questions) == 1  # 未漂移，只有二次确认
        assert "任务期间新建文件" in questions[0]
        assert "user_mid.txt" in questions[0]
        assert "Agent 新建" not in questions[0]  # 不做无法兑现的归因

    def test_undo_head_drift_requires_explicit_confirm(self, tmp_path: Path) -> None:
        """HEAD 漂移（用户会话中重写历史）→ 先警示；拒绝则不动。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        # 用户普通 commit：快照 sha 仍是 HEAD 祖先 → 未漂移。
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "user commit")
        sha = session.snapshots[-1].sha
        assert session.head_drifted(sha) is False
        # 重写历史（amend 快照 commit 本身）：旧 sha 不在 HEAD 祖先链 → 漂移。
        _git(repo, "reset", "--hard", sha)
        _git(repo, "commit", "--amend", "--allow-empty", "-m", "user rewrite")
        assert session.head_drifted(sha) is True
        # 漂移警示阶段即拒绝 → 不动。
        questions: list[str] = []

        def confirm(q: str) -> bool:
            questions.append(q)
            return False

        result = session.undo(confirm)
        assert "已取消" in result
        assert "你自己的提交" in questions[0]
        assert len(session.snapshots) == 1

    def test_undo_head_drift_confirmed_proceeds(self, tmp_path: Path) -> None:
        """HEAD 漂移警示确认 + 二次确认 → 正常回滚并弹栈。"""
        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        sha = session.snapshots[-1].sha
        # amend 重写快照 commit 制造真实漂移，两个确认都同意 → 正常回滚。
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "user commit")
        _git(repo, "reset", "--hard", sha)
        _git(repo, "commit", "--amend", "--allow-empty", "-m", "diverged")
        result = session.undo(_yes)
        assert "已回滚" in result
        assert _git(repo, "rev-parse", "HEAD") == sha
        assert session.snapshots == []


class TestConfirmFailClosed:
    """评审 O2：确认回调 fail-closed，EOF/中断/异常一律按拒绝处理。"""

    def test_eof_during_confirm_aborts_undo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """plain 模式 input() 遇 EOFError → 拒绝，/undo 不执行。"""
        from agent.cli.chat import _make_confirm_callback

        def _raise_eof(_: str = "") -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", _raise_eof)
        confirm = _make_confirm_callback(plain=True)
        assert confirm("问题") is False

        repo = tmp_path / "proj"
        _init_repo(repo)
        session = _make_session_with_task(repo)
        result = session.undo(confirm)
        assert "已取消" in result
        assert (repo / "agent_new.txt").exists()
        assert len(session.snapshots) == 1

    def test_keyboard_interrupt_during_confirm_rejects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ctrl+C（KeyboardInterrupt）→ 拒绝，不向上抛。"""
        from agent.cli.chat import _make_confirm_callback

        def _raise_kbd(_: str = "") -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", _raise_kbd)
        assert _make_confirm_callback(plain=True)("问题") is False


class TestNoGitClean:
    """绝对禁令断言：实现代码中不得出现 git clean 调用。"""

    def test_no_git_clean_invocation(self) -> None:
        """grep 断言 workspace_session/chat 源码无 git clean。"""
        import agent.cli.chat as chat_mod
        import agent.cli.workspace_session as ws_mod

        for mod in (ws_mod, chat_mod):
            src = Path(mod.__file__ or "").read_text(encoding="utf-8")
            assert "git clean" not in src
            assert '"clean"' not in src


class TestNonBindUnavailable:
    """非 bind 模式 /diff /undo 不可用提示（chat 层）。"""

    def test_commands_rejected_without_session(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """workspace_session=None 时命令提示仅 bind 模式可用。"""
        from agent.cli.chat import _handle_command

        for cmd in ("/diff", "/undo"):
            assert _handle_command(cmd, plain=True, workspace_session=None) is True
            out = capsys.readouterr().out
            assert "仅 bind 工作区模式" in out
