"""TD-015 单元 C 保险一：host_dir 工作区的 git 强制快照（宿主侧）。

本模块运行在宿主机上（CLI 装配层调用），不属于沙箱抽象，因此放在
cli 层而非 sandbox 层。设计要点（2026-08-22 澄清轮裁决）：

  - host_dir 必须是已存在的 git 仓库，否则拒绝启动（引导 git init）；
  - dirty 工作区自动做一次快照 commit（信息 'litmus: pre-agent snapshot'，
    提交在当前分支，Aider 模式）；clean 则跳过；
  - 宿主 git 未配置 user.name/user.email 时，用 env 级
    GIT_AUTHOR_NAME/GIT_COMMITTER_NAME=litmus-agent 兜底，
    绝不修改用户的 git 配置；
  - 回滚方式（文档化）：`git reset --hard <sha>` 或 `git diff <sha>`；
  - docker 与 subprocess 后端 + host_dir 同样强制本保险。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.config import AgentConfig

logger = logging.getLogger(__name__)

SNAPSHOT_MESSAGE = "litmus: pre-agent snapshot"

# 快照 commit 的 env 级署名兜底（不改用户 git 配置）。
_SNAPSHOT_ENV: dict[str, str] = {
    "GIT_AUTHOR_NAME": "litmus-agent",
    "GIT_AUTHOR_EMAIL": "litmus-agent@localhost",
    "GIT_COMMITTER_NAME": "litmus-agent",
    "GIT_COMMITTER_EMAIL": "litmus-agent@localhost",
}

# 阻断仓库 hooks 的命令行前缀（安全动机见 snapshot_workspace docstring）。
# 恶意仓库可通过 .git/hooks/ 或 core.hooksPath 注入 pre-commit 等 hook，
# 快照时的 git add/commit 若在宿主执行这些脚本即构成 RCE。
# `-c core.hooksPath=/dev/null` 让 git 找不到任何 hooks 目录
# （命令行 -c 优先级高于仓库 config，可同时压制 core.hooksPath 注入；
# /dev/null 不是目录，Git for Windows 亦按"无 hooks"处理，跨平台有效）。
_NO_HOOKS_PREFIX: list[str] = ["-c", "core.hooksPath=/dev/null"]


def _run_git(host_dir: Path, args: list[str], env_extra: dict[str, str] | None = None) -> str:
    """在 host_dir 下执行 git 命令并返回 stdout。

    参数：
        host_dir: 目标 git 仓库目录。
        args: git 子命令与参数列表。
        env_extra: 追加的环境变量（如快照署名兜底）。

    返回：
        命令 stdout（去除首尾空白）。

    抛出：
        ValueError: git 命令执行失败（非零退出码），stderr 并入错误信息。
    """
    env = {**os.environ, **(env_extra or {})}
    proc = subprocess.run(
        ["git", *args],
        cwd=str(host_dir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(
            f"git {' '.join(args)} 执行失败（exit={proc.returncode}）："
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def ensure_git_workspace(host_dir: str) -> None:
    """校验 host_dir 可作为 bind 工作区：存在、是目录、git 可用、是 git 仓库。

    参数：
        host_dir: 宿主机目录路径。

    抛出：
        ValueError: 任一校验失败，错误信息含引导（如提示 git init）。
    """
    path = Path(host_dir)
    if not path.exists():
        raise ValueError(f"host_dir 不存在：{host_dir}（bind 模式要求已存在的项目目录）")
    if not path.is_dir():
        raise ValueError(f"host_dir 不是目录：{host_dir}（bind 模式要求挂载一个目录）")
    if shutil.which("git") is None:
        raise ValueError(
            "未找到 git 可执行文件。host_dir（bind 模式）强制要求 git 快照保险，"
            "请先安装 git 或改用默认/持久卷工作区。"
        )
    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        raise ValueError(
            f"host_dir 不是 git 仓库：{host_dir}。bind 模式强制要求 git 快照保险"
            "（用于误写回滚），请先在目录内执行 `git init && git add -A && "
            "git commit -m init`，或改用默认/持久卷工作区。"
        )
    # 必须挂仓库根目录而非其子目录：否则快照只覆盖 host_dir 内的路径，
    # 仓库其余部分不受 git 快照保险保护（误伤仓库且回滚语义混乱）。
    # 比较前用 realpath + normcase 归一化，消除符号链接、Windows 大小写
    # 与路径分隔符差异。
    toplevel = _run_git(path, ["rev-parse", "--show-toplevel"])
    if os.path.normcase(os.path.realpath(toplevel)) != os.path.normcase(
        os.path.realpath(path)
    ):
        raise ValueError(
            f"host_dir 必须是 git 仓库根目录：{host_dir}（实际仓库根：{toplevel}）。"
            "请把 host_dir 指向仓库根，或对子目录单独 git init。"
        )


def snapshot_workspace(host_dir: str) -> str | None:
    """对 dirty 工作区自动做一次快照 commit；clean 则跳过。

    快照提交在当前分支（Aider 模式），作者署名使用 env 级 litmus-agent
    兜底（不改用户 git 配置），保证未配置 user.name/user.email 的环境
    也能成功提交。

    安全动机（hooks 阻断）：host_dir 可能是不可信/被注入的仓库——恶意
    pre-commit hook 或 `core.hooksPath` 指向的脚本会在快照 commit 时于
    宿主机执行，构成 RCE。因此 `git add` / `git commit` 统一带
    `-c core.hooksPath=/dev/null`（压过仓库 config，Git for Windows 下
    /dev/null 非目录同样无 hooks 可执行），commit 另加 `--no-verify`
    双保险跳过 pre-commit/commit-msg。

    参数：
        host_dir: 宿主机 git 仓库目录（应先通过 ensure_git_workspace 校验）。

    返回：
        dirty 时返回快照 commit 的 sha；clean 时返回 None。

    抛出：
        ValueError: git 操作失败。
    """
    path = Path(host_dir)
    status = _run_git(path, ["status", "--porcelain"])
    if not status:
        return None
    # -A：把未跟踪文件一并纳入快照，保证 reset --hard 后可完整回到快照点
    # 之前的状态范围可见（未跟踪文件本身不受 reset 影响，但纳入快照后
    # Agent 改动可通过 git status/diff 完整审计）。
    _run_git(path, [*_NO_HOOKS_PREFIX, "add", "-A"])
    _run_git(
        path,
        [*_NO_HOOKS_PREFIX, "commit", "--no-verify", "-m", SNAPSHOT_MESSAGE],
        env_extra=_SNAPSHOT_ENV,
    )
    return _run_git(path, ["rev-parse", "HEAD"])


def apply_bind_safeguards(config: AgentConfig) -> str | None:
    """bind（host_dir）模式安全件装配：git 校验 + 快照 + 默认推导。

    TD-015 单元 C 同行评审回炉：CLI 与 Web 共用本函数，避免两份实现漂移。
    依次执行保险一/二/三（横幅属 CLI 专属，由调用方自行处理）：

      1. 保险一：ensure_git_workspace + snapshot_workspace（git 强制快照）；
      2. 保险二：human_approval 未显式配置时按 True 生效；显式关闭打 warning；
      3. 保险三：security 未显式配置时按 True 生效并注入敏感文件 read deny；
         显式关闭打 warning。

    参数：
        config: 已合并的最终配置（要求 sandbox.host_dir 非 None）。

    返回：
        快照 commit 的 sha；工作区 clean 时返回 None。

    抛出：
        ValueError: git 校验或快照失败（由调用方走友好报错路径）。
    """
    host_dir = config.sandbox.host_dir
    assert host_dir is not None  # 调用方保证仅 bind 模式进入

    # 保险一：git 强制快照（宿主侧）。
    ensure_git_workspace(host_dir)
    snapshot_sha = snapshot_workspace(host_dir)

    # 保险二：写操作人工确认——bind 模式未显式配置时默认开启。
    approval_cfg = config.agent.human_approval
    approval_cfg.enabled = config.sandbox.resolve_human_approval(approval_cfg)
    if approval_cfg.enabled is False:
        logger.warning(
            "host_dir 模式下 human_approval 被显式关闭：Agent 写宿主文件"
            "将不再逐次确认，风险自担"
        )

    # 保险三：安全策略默认开启 + 敏感文件 read deny。
    if config.sandbox.resolve_security_enabled(config.security):
        config.security.enabled = True
        config.security.bind_read_deny = True
    else:
        logger.warning(
            "host_dir 模式下 security 被显式关闭：敏感文件 read deny 与写边界"
            "将不生效，风险自担"
        )

    return snapshot_sha
