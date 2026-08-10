# Feature Spec — 亮点叙事测试（记忆/压缩/反思，真实 LLM）

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-18 16:20 | **Phase**：`EXECUTE`（Plan 已于会话中批准） | **Status**：`[ACTIVE]`
> **Approval Status**：✅ `Plan Approved`（2026-07-18，含两项确认点默认决策）

---

## 0. 任务复述

- **目标**：为三个差异化模块建真实 LLM 叙事测试，数据全部落盘，服务简历亮点。
- **场景**：
  - **S6-M1 记忆叙事**：Session A 创建 `/workspace/notes.md`（内容含代号）→ 新 Agent 实例（同 memory_root）→ Session B 问"我之前创建过什么文件"。证据：B 答案含 notes.md；A trace 含 `memory_recorded`。
  - **S7-C1 压缩叙事**：小 context_window（600/预留 100）强制快速压缩 → 第 1 轮告知幸运数字 → 多轮大输出填充 → 末轮提问。证据：trace 含 `context_compression` 事件；答案含幸运数字（首条 user 消息受 protect_first_n 保护）。
  - **S8-R1 反思叙事**：让 Agent 读不存在的文件（有限轮数内反复失败）。证据：trace 含 `error_classification` + `reflection` 事件；最终如实报告（接受"承认失败"为正确行为——已确认）。
- **M1 跨会话语义（已确认）**：两个 Agent 实例共享 memory_root（模拟跨会话，足够证明持久化）。
- **Done Contract**：① 3 场景真实执行，证据断言如实记录（失败也记录）；② 结果 + 既有 3 项（Auto-Planner/双后端/安全）整理为"亮点验证矩阵"进 evaluation-log；③ 全量门禁不回归。

## 1. 技术设计

- `Scenario` 增补字段：`config_overrides: dict[str, Any]`（点分路径应用配置）、`two_phase: bool`、`prompt_b: str`。
- S6 专用两阶段 runner：Agent A（memory.enabled，共享临时 memory_root）执行 prompt → close → Agent B（同 root）执行 prompt_b。
- S7 经 `config_overrides` 启用压缩并缩小窗口；S8 为普通场景。
- 离线测试：config_overrides 应用、两阶段 runner 结构（脚本化客户端）。

## 2. File Changes

| 操作 | 路径 |
|---|---|
| 修改 | `examples/e2e_suite.py`（Scenario 扩展 + 3 场景 + 两阶段 runner） |
| 修改 | `tests/test_e2e_suite.py`（离线测试增补） |
| 修改 | `docs/evaluation-log.md`（3 条 E2E 记录 + 亮点验证矩阵） |
| 修改 | `docs/progress-spec.md`、`docs/session-context.md` |

## 3. Checklist

- [ ] 1. RED：离线测试（config_overrides / 两阶段结构）→ 失败确认
- [ ] 2. GREEN：套件扩展实现 → 离线通过 + 门禁
- [ ] 3. 真实执行 S6/S7/S8（DeepSeek + Docker）→ 如实记录
- [ ] 4. evaluation-log 亮点验证矩阵 + 文档同步
- [ ] 5. 双 commit + Spec 回写

## 4. 风险

| 风险 | 缓解 |
|---|---|
| S8 反思事件未触发（阈值高于轮数内错误数） | max_turns 15 提高错误积累机会；如实记录实际行为 |
| S7 关键信息被压缩掉 | 首条 user 消息受 protect_first_n 保护；幸运数字放第 1 轮 |
| M1 artifact 提取规则未命中 | 已核实 RuleMemoryExtractor 覆盖 /workspace 路径产物 |

---

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-18 16:20 | 用户批准会话计划（6 模块全做/真实 LLM 优先/数据落盘；M1 双实例跨会话；R1 接受如实失败），Spec 落盘进入 EXECUTE |
