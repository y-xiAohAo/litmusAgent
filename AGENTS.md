# AGENTS.md — Hermes Agent 项目规则（最小路由版）

> 本文件只写路由、底线、禁止项和恢复规则，不复制完整 Skill / Spec。
> 完整协议见全局 skill：`sdd-riper-one` / `sdd-riper-one-light`（`~/.kimi/skills/`）。

## AI Coding Harness 路由

- **复杂 / 高风险 / 跨模块 / 长链路任务** → 默认使用 `sdd-riper-one`（完整阶段门禁）。
- **边界清晰的日常小任务 / 熟练高频迭代** → 日常使用 `sdd-riper-one-light`。
- **琐碎单点修改** → 允许 FAST 通道（`>>` 前缀），但事后必须回写 Spec。

## 底线（不可削弱）

1. `No Spec, No Code`：活跃 Spec 落盘前，不进入代码实现。
2. `No Approval, No Execute`：未收到精确字样 `Plan Approved`，禁止 Execute。
3. `Spec is Truth`：聊天决议必须回源 Spec；冲突时以 Spec 为准。
4. `Done by Evidence`：完成由 pytest / mypy / ruff / 日志 / 人工验收证明。
5. `Restate First` + `Checkpoint Before Execute`：关键节点先复述目标、阶段、批准状态、风险与验证方式。

## 产物落点约定

| 产物 | 路径 |
|---|---|
| 活跃 Spec（唯一真相源） | `mydocs/specs/` |
| Codemap（代码地形索引） | `mydocs/codemap/`（根 `CODEMAP.md` 为历史版本） |
| Context bundle / Archive | `mydocs/context/` / `mydocs/archive/` |
| 历史任务 spec | `.kimi/vibe_specs/`（旧体系，只读参考） |
| 技术债总表 | `.kimi/vibe_specs/technical-debt-spec.md` |

- `mydocs/` 默认**不入 git**（隐私边界）；需提交时须用户明确要求并脱敏确认。

## 工程规范

- 质量门禁（提交前必过）：`python -m pytest tests/ -q`、`python -m mypy src/`、`python -m ruff check src/ tests/`
- venv：`C:\Users\msn\AppData\Local\hermes\hermes-agent\venv\`
- 注释与文档用中文；public 函数/类需类型标注 + 中文 docstring；行宽 100。
- Commit 格式：`type: description`（feat/fix/docs/test/chore/refactor），一个 task 一个 commit。
- **禁止**：静默或提议执行 `git clean`（任何参数）；未经用户明确指示执行 `git commit/push/reset/rebase`；提交密钥、trace、记忆数据、隐私路径。
