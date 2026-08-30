"""TD-021：bind 模式会话内 `/diff` / `/undo` 工作台的会话状态与执行器。

本模块运行在宿主机上（CLI 装配层调用），与 `workspace_guard` 同属
宿主侧 git 安全网：`workspace_guard` 是会话启动时的被动保险丝，
本模块把同一份快照机制升级为会话内主动 review / 回滚工作台。

设计要点（Spec `mydocs/specs/2026-08-29_td-021-undo-diff-commands.md`）：

  - 快照栈：每次用户提交任务前调用 `snapshot_workspace` 补快照
    （裁决 Q3），栈顶即"最近一个任务"的回滚点；`/undo` 只回滚栈顶，
    多级回滚留后续（Spec §3 Out）；
  - 任务期间新建文件清单：**快照前**用 `git status --porcelain -uall`
    记录 untracked 基线（快照的 `git add -A` 会把全部 untracked 卷进
    commit，快照后再取基线恒为空——评审 R2），任务后差集即新建文件。
    注意口径：差集无法区分 Agent 与用户同时新建，文案统一称
    "任务期间新建文件"（评审 R2 文案诚实化）；`/undo` 仅逐个删除
    清单内文件，**绝不调用 clean 子命令**（AGENTS.md 绝对禁令）；
  - 用户修改保护（Spec §2.3-4，评审 O1）：end_task 对差集文件计算
    内容哈希存栈顶；undo 删除前比对当前哈希，不一致（用户改过了）
    则跳过并进告警清单，绝不静默；
  - `/diff`：先给 `git diff <sha> --stat` 摘要 + 新建清单 + 总字节数；
    完整 diff ≤ 8KB 直接渲染，超长则写入宿主临时文件并提示路径
    （裁决 Q2，参照 ToolResultExternalizer 的外迁哲学）。外迁文件
    登记在会话上，chat 循环退出时由 `cleanup()` 统一清理（评审 O3）；
  - `/undo`：HEAD 漂移检测（快照 sha 不在 HEAD 祖先链 → 显式警示确认）
    + 二次确认（always，y/n），拒绝则不动（裁决 Q1）。

git 调用的写操作（reset --hard）沿用 `workspace_guard` 的
`-c core.hooksPath=/dev/null` 前缀保持同等防护；status/diff/rev-list
等只读调用不执行仓库 hooks，无需前缀。
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent.cli.workspace_guard import _NO_HOOKS_PREFIX, _run_git, snapshot_workspace

logger = logging.getLogger(__name__)

# /diff 内联渲染阈值：完整 diff 文本超过 8KB 时外迁到临时文件。
DIFF_INLINE_LIMIT_BYTES = 8 * 1024

# 确认回调类型：传入问题文本，返回 True 表示用户确认。
ConfirmCallback = Callable[[str], bool]


def _file_hash(path: Path) -> str | None:
    """计算文件内容的 sha256；文件不存在或不可读时返回 None。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


@dataclass
class TaskSnapshot:
    """单个任务的快照栈条目。

    属性：
        task_index: 任务序号（从 1 开始，仅用于展示）。
        sha: 任务前快照点（snapshot_workspace 的 commit sha；
            工作区 clean 时退化为当时的 HEAD）。
        baseline_untracked: **快照前**的未跟踪文件清单（仓库相对路径）。
        new_files: 任务结束后差集出的任务期间新建文件清单。
        new_file_hashes: end_task 时各新建文件的内容哈希（undo 删除前
            比对，防止误删用户后来修改过的文件）。
    """

    task_index: int
    sha: str
    baseline_untracked: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    new_file_hashes: dict[str, str] = field(default_factory=dict)


class WorkspaceSession:
    """bind 模式 chat 会话的快照栈与 /diff /undo 执行器。

    生命周期：bind 装配时创建并传入 chat 循环；每次任务前 `begin_task`，
    任务结束（含异常）后 `end_task`；`/diff`、`/undo` 命令由 chat 循环
    转调本类方法；chat 循环退出时调用 `cleanup()` 清理外迁临时文件。
    """

    def __init__(self, host_dir: str) -> None:
        """初始化会话。

        参数：
            host_dir: 宿主机 git 仓库根目录（bind 装配时已校验）。
        """
        self._host_dir = Path(host_dir)
        self._snapshots: list[TaskSnapshot] = []
        # /diff 外迁的临时文件登记处，会话结束由 cleanup() 清理。
        self._temp_files: list[Path] = []

    @property
    def snapshots(self) -> list[TaskSnapshot]:
        """快照栈（只读视图，栈顶为最后一个元素）。"""
        return list(self._snapshots)

    def _untracked_files(self) -> list[str]:
        """当前工作区的未跟踪文件清单（-uall 递归列出全部文件）。

        必须用 `-uall`：默认模式下 git 对未跟踪目录只报 `?? dir/`，
        会漏掉目录内的具体文件，导致 /undo 无法完整清理（评审 R1）。
        """
        out = _run_git(self._host_dir, ["status", "--porcelain", "-uall"])
        files: list[str] = []
        for line in out.splitlines():
            if line.startswith("?? "):
                files.append(line[3:].strip().strip('"'))
        return files

    def begin_task(self) -> TaskSnapshot:
        """任务前钩子：先取 untracked 基线，再补快照并入栈。

        基线必须在快照**之前**采集：snapshot_workspace 的 `git add -A`
        会把全部 untracked 卷进快照 commit，快照后再取基线恒为空，
        差集语义不成立（评审 R2）。

        返回：
            新入栈的 TaskSnapshot。
        """
        baseline = self._untracked_files()
        sha = snapshot_workspace(str(self._host_dir))
        if sha is None:
            # 工作区 clean：回滚点即当前 HEAD。
            sha = _run_git(self._host_dir, ["rev-parse", "HEAD"])
        snap = TaskSnapshot(
            task_index=len(self._snapshots) + 1,
            sha=sha,
            baseline_untracked=baseline,
        )
        self._snapshots.append(snap)
        return snap

    def end_task(self) -> None:
        """任务后钩子：差集出新建文件清单并记录内容哈希（栈顶条目）。"""
        if not self._snapshots:
            return
        top = self._snapshots[-1]
        baseline = set(top.baseline_untracked)
        top.new_files = [p for p in self._untracked_files() if p not in baseline]
        top.new_file_hashes = {
            rel: h for rel in top.new_files if (h := _file_hash(self._host_dir / rel))
        }

    def cleanup(self) -> None:
        """会话结束清理：删除 /diff 外迁的临时文件（失败仅告警）。

        口径：外迁文件是"避免刷屏"的临时产物（评审 O3），与仓库内容
        无关，会话退出即清理；用户若在会话期间已自行打开/移动该文件，
        删除失败仅记 warning，不影响退出。
        """
        for path in self._temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("清理外迁 diff 临时文件失败：%s（%s）", path, exc)
        self._temp_files.clear()

    # ------------------------------------------------------------------
    # /diff
    # ------------------------------------------------------------------

    def diff_report(self) -> str:
        """生成 /diff 报告：stat 摘要 + 新建文件清单 + 完整 diff（或外迁）。

        本方法只产出文本，Rich/plain 渲染归 chat 层，保持可测试性。

        返回：
            报告文本。栈空时返回提示文本。
        """
        if not self._snapshots:
            return "尚无可对比的任务快照（提交过任务后 /diff 才可用）。"
        top = self._snapshots[-1]
        stat = _run_git(self._host_dir, ["diff", top.sha, "--stat"])
        full_diff = _run_git(self._host_dir, ["diff", top.sha])
        lines = [
            f"自任务 #{top.task_index} 快照（{top.sha[:12]}）以来的改动：",
            "",
            stat or "（已跟踪文件无改动）",
        ]
        if top.new_files:
            lines.append("")
            lines.append("任务期间新建（未跟踪）文件：")
            lines.extend(f"  {p}" for p in top.new_files)
        diff_bytes = len(full_diff.encode("utf-8"))
        lines.append("")
        lines.append(f"完整 diff 大小：{diff_bytes} 字节")
        if not full_diff:
            return "\n".join(lines)
        if diff_bytes <= DIFF_INLINE_LIMIT_BYTES:
            lines.append("")
            lines.append(full_diff)
            return "\n".join(lines)
        # 超长外迁：写入宿主临时文件，提示 ref 链接式路径，不刷屏；
        # 登记到会话，chat 循环退出时由 cleanup() 清理。
        fd, tmp_path = tempfile.mkstemp(
            prefix="litmus-diff-", suffix=".diff", text=True
        )
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(full_diff)
        self._temp_files.append(Path(tmp_path))
        lines.append(f"完整 diff 已写入 {tmp_path}（超过 8KB，外迁避免刷屏）")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # /undo
    # ------------------------------------------------------------------

    def head_drifted(self, sha: str) -> bool:
        """HEAD 漂移检测：快照 sha 不在当前 HEAD 祖先链中返回 True。

        语义：sha 是 HEAD 祖先（含等于）→ 未漂移；否则说明用户会话中
        重写过历史（amend/rebase 等），undo 会把这些提交一并丢弃。
        用 `rev-list HEAD` 成员判断实现，只读、无需额外 git 辅助函数。
        """
        ancestors = _run_git(self._host_dir, ["rev-list", "HEAD"]).splitlines()
        return sha not in ancestors

    def undo_preview(self) -> tuple[list[str], list[str]] | None:
        """/undo 二次确认前的预览：将丢弃的已跟踪改动 + 将删除的新建清单。

        返回：
            (已跟踪改动文件清单, 任务期间新建文件清单)；栈空时返回 None。
        """
        if not self._snapshots:
            return None
        top = self._snapshots[-1]
        out = _run_git(self._host_dir, ["status", "--porcelain"])
        tracked = [
            line[3:].strip().strip('"')
            for line in out.splitlines()
            if line and not line.startswith("?? ")
        ]
        return tracked, list(top.new_files)

    def _delete_new_file(self, rel: str, top: TaskSnapshot) -> str | None:
        """删除清单内单个新建文件；返回 None 表示成功，否则返回告警原因。

        保护规则（评审 R1/O1）：
          - 文件已不存在（如被 reset --hard 一并移除）→ 告警，不静默；
          - 当前内容哈希与 end_task 记录不一致（用户后来改过）→ 跳过；
          - 目录用 shutil.rmtree（仅限清单内），文件用 unlink；
          - 任何 OSError → 告警，不中断。
        """
        target = self._host_dir / rel
        if not target.exists():
            return "已不存在（可能已被回滚移除），未删除"
        expected = top.new_file_hashes.get(rel)
        if target.is_file() and expected is not None and _file_hash(target) != expected:
            return "内容与任务结束时不一致（可能被你修改过），未删除"
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            logger.warning("删除任务期间新建文件失败：%s（%s）", target, exc)
            return f"删除失败：{exc}"
        self._prune_empty_parents(target.parent)
        return None

    def _prune_empty_parents(self, path: Path) -> None:
        """自底向上清理空父目录（止于仓库根；非空即停，误删不可能）。"""
        current = path
        while current != self._host_dir and current.is_dir():
            try:
                current.rmdir()  # 仅当目录为空才成功
            except OSError:
                break
            current = current.parent

    def undo(self, confirm: ConfirmCallback) -> str:
        """执行 /undo：HEAD 漂移检测 → 二次确认 → reset --hard + 删新建文件。

        参数：
            confirm: 确认回调（chat 层注入交互式 y/n，fail-closed；
                测试注入桩）。

        返回：
            结果描述文本（含拒绝 / 栈空 / 成功路径）。
        """
        preview = self.undo_preview()
        if preview is None:
            return "无可回滚的任务快照（快照栈为空）。"
        top = self._snapshots[-1]
        tracked, new_files = preview

        # HEAD 漂移检测：用户会话中重写过历史时显式警示。
        if self.head_drifted(top.sha):
            if not confirm(
                "警示：会话中存在你自己的提交，undo 将一并丢弃。仍要继续？"
            ):
                return "已取消 /undo（HEAD 漂移，用户拒绝丢弃自有提交）。"

        # 二次确认（always）：列出将丢弃的改动与将删除的文件。
        # 口径：差集无法区分 Agent 与用户同时新建，统称"任务期间新建"。
        lines = [
            f"将回滚到任务 #{top.task_index} 快照（{top.sha[:12]}）：",
            f"  丢弃已跟踪改动 {len(tracked)} 个文件",
        ]
        if new_files:
            lines.append(f"  删除任务期间新建文件 {len(new_files)} 个：")
            lines.extend(f"    {p}" for p in new_files)
        if not confirm("\n".join(lines) + "\n确认执行 /undo？"):
            return "已取消 /undo（用户拒绝二次确认）。"

        # 执行：reset --hard 回滚已跟踪改动（带 hooks 阻断前缀，同等防护；
        # 绝不使用 clean 子命令），再逐个删除清单内的新建文件。
        _run_git(self._host_dir, [*_NO_HOOKS_PREFIX, "reset", "--hard", top.sha])
        deleted: list[str] = []
        failed: list[tuple[str, str]] = []
        for rel in new_files:
            reason = self._delete_new_file(rel, top)
            if reason is None:
                deleted.append(rel)
            else:
                failed.append((rel, reason))
        self._snapshots.pop()

        result = [
            f"已回滚到任务 #{top.task_index} 快照（{top.sha[:12]}）。",
            f"  已删除任务期间新建文件 {len(deleted)} 个",
        ]
        for rel, reason in failed:
            result.append(f"  [WARN] {rel}：{reason}")
        return "\n".join(result)
