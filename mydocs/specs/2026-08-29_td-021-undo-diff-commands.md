# Feature Spec — TD-021：bind 模式会话内 `/diff` / `/undo`

> **层级**：Feature Spec
> **创建**：2026-08-29（SDD-RIPER-ONE）
> **技术债登记**：`.kimi/vibe_specs/technical-debt-spec.md` TD-021
> **当前 phase**：Plan（等待 `Plan Approved`）
> **用户裁决（2026-08-29 澄清轮）**：Q1 回滚要干净（含删除 Agent 新建文件）；Q2 `/diff` 先给摘要+长度，过长写文件经 ref 链接访问；Q3 每次任务前补快照（非仅会话启动）；Q4 一次性 run 模式不做

---

## 1. 目标

把 TD-015 的 git 安全网从"被动保险丝"变成"主动 review/回滚工作台"：bind 模式的 `agent chat` 会话内可用 `/diff`（查看 Agent 改动）与 `/undo`（回滚到任务前快照）。

## 2. 设计

### 2.1 快照栈（裁决 Q3：每次任务前补快照）

- chat 会话内**每次用户提交任务前**调用 `snapshot_workspace(host_dir)`（复用 `cli/workspace_guard.py`，dirty 才提交，clean 跳过）。
- 维护会话级快照栈 `list[TaskSnapshot]`（sha + 任务序号 + Agent 新建文件清单）。新建文件清单来源：快照后 `git status --porcelain` 基线，任务结束后 diff 出的 untracked 文件即 Agent 产物（实现上：任务前记录 untracked 集合，任务后差集 = Agent 新建）。
- 语义：`/undo` = 回滚到**最近一个任务**的快照（栈顶）；栈空时提示无可回滚。
- 已知代价（接受）：用户分支上会累积多个 `litmus: pre-agent snapshot` commit，署名可审计，用户可自行 squash；文档写明。

### 2.2 `/diff`（裁决 Q2：摘要 + 过长外迁）

- 输出顺序：`git diff <快照sha> --stat` 摘要 + 未跟踪文件清单 + 总字节数。
- 若完整 diff 文本 ≤ 8KB：直接渲染（Rich syntax diff / plain 直出）。
- 若 > 8KB：写入宿主临时文件（`tempfile`），输出 ref 链接式路径提示（如 `完整 diff 已写入 <path>`）——参照 ToolResultExternalizer 的外迁哲学，不刷屏。

### 2.3 `/undo`（裁决 Q1：回滚干净）

流程：
1. 栈顶快照 sha；若栈空 → 提示。
2. **HEAD 漂移检测**：若当前 HEAD 的祖先链中不存在快照 sha（用户会话中自己 commit 过）→ 警示"会话中存在你自己的提交，undo 将一并丢弃"，须显式确认。
3. **二次确认**（always，y/n）：提示将丢弃的已跟踪改动文件数 + 将删除的 Agent 新建文件清单。
4. 执行：`git reset --hard <sha>` + **逐个删除** Agent 新建文件清单中的文件（仅限清单内、`Path.unlink`、文件仍在且与快照后内容未被用户修改过——读取清单文件做存在性检查，删除失败逐个 warning 不中断）。**禁止 `git clean`**（AGENTS.md 绝对禁令）。
5. 弹栈，打印回滚结果。

### 2.4 装配

- `workspace_guard.snapshot_workspace` 已有；新增 `cli/workspace_session.py`：`WorkspaceSession` 管理快照栈、任务前后 untracked 差集、undo/diff 执行。
- chat 循环（`cli/chat.py`）：bind 模式时注册 `/diff`、`/undo` 命令处理；非 bind 模式命令提示"仅 bind 工作区模式（sandbox.host_dir）可用"。
- 横幅补充：`/diff` `/undo` 可用提示。

## 3. In / Out

**In**：chat 交互模式的两个命令、快照栈、外迁 diff、undo 二次确认与 HEAD 漂移检测、测试、文档。

**Out**：run 模式（裁决 Q4）；多级回滚选择（/undo N 或交互选择，留后续）；`/undo` 后 redo；非 git 状态异常（会话中 .git 被动）只做到友好报错。

## 4. 涉及文件

| 文件 | 改动 |
|---|---|
| `src/agent/cli/workspace_session.py`（新） | WorkspaceSession：快照栈 + diff/undo 实现 |
| `src/agent/cli/chat.py` | 命令注册与接入、任务前快照钩子 |
| `src/agent/cli/agent_cli.py` | bind 装配时创建 WorkspaceSession 传入 chat |
| `tests/test_workspace_session.py`（新） | 见 §5 |
| `docs/usage.md` bind 章节 | 两个命令说明 |

## 5. 验收

- 真实 git 仓库（tmp_path）：任务后 `/diff` 显示 stat + 新文件清单；超长 diff 外迁到文件并提示路径。
- `/undo`：已跟踪改动回滚 + Agent 新建文件被删除 + 栈弹出；栈空提示；HEAD 漂移警示确认；二次确认拒绝则不动。
- 确认 `git clean` 零调用（grep 断言/审查）。
- 用户会话中修改过 Agent 新建文件时的删除行为符合 §2.3-4（仅清单内）。
- 非 bind 模式命令不可用提示。
- 门禁：全量 pytest（基线 973）+ mypy + ruff 绿。

## 6. 风险

| 风险 | 缓解 |
|---|---|
| /undo 误删 | 二次确认 + 仅删任务差集清单内文件 + 删除失败逐个告警 |
| 用户会话中改动被卷进快照 | 快照 commit 语义即如此（照 Aider 先例），文档写明；HEAD 漂移检测兜底 |
| 快照 commit 噪音 | 署名可审计 + 文档教 squash |
| 任务期间用户自建文件被误删（评审 R2） | 差集无法区分 Agent 与用户同时新建——基线在快照**之前**采集保证差集真实成立；确认文案统一诚实化为"任务期间新建文件"；end_task 记录内容哈希，undo 删除前比对，用户改过的文件跳过并告警 |
| 新建目录漏删（评审 R1） | untracked 采集用 `git status --porcelain -uall` 精确到文件；删除后自底向上剪枝空父目录；任何跳过/失败进 [WARN] 告警，不静默 |

## 7. Resume / Handoff

- **状态**：✅ Execute 完成（2026-08-29，当日 `Plan Approved`），待独立 CR
- **改动**：`cli/workspace_session.py`（新建：WorkspaceSession 快照栈 + diff/undo）、`chat.py`（命令注册 + begin/end_task 钩子）、`agent_cli.py`（bind 装配 + 横幅）、`tests/test_workspace_session.py`（14 例，真实 git）、usage.md。
- **Validation（复核实测）**：987 passed, 1 skipped（+14）；mypy 53 文件零错误；ruff 全绿。
- **偏差**：HEAD 漂移检测按字面条件（sha 不在祖先链）实现——普通 commit 不触发，amend/rebase 类历史重写才触发（更准确的语义）。
- **CR 修复轮（2026-08-30，2🔴+3🟠 全修）**：R1 -uall + 空目录剪枝 + 失败必告警；R2 基线移至快照前采集 + 文案诚实化（"任务期间新建文件"）；O1 落地 §2.3-4（end_task 记内容哈希，undo 删除前比对，不一致跳过告警"未删除"）；O2 确认回调 fail-closed（EOF/Ctrl+C/异常均拒绝）；O3 外迁临时文件登记会话、chat 退出 cleanup() 清理。顺手：head_drifted docstring 语义方向修正、diff_report 去掉 dead 参数 plain、`_run_git_allow_fail` 合并为 rev-list 成员判断（subprocess 辅助函数移除）。
- **O1 落地口径**：哈希以 end_task 时点为基准，保护"任务结束后、undo 执行前"窗口内用户对新文件的修改；任务进行中的改动不在保护范围。
- **Validation（修复后实测）**：pytest 全量绿、mypy 零错误、ruff 全绿（数值见当轮报告）。
