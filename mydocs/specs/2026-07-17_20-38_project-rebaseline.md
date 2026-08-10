# Feature Spec — Hermes Agent 项目结构重基线（SDD-RIPER-ONE Re-baseline）

> **Spec 层级**：Feature Spec（本任务）；Project Sync Candidate 见 §9
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-17 20:38 | **Phase**：`CLOSED`（本单元目标已达成） | **Status**：`[LOCKED]`
> **Approval Status**：`N/A — 本单元无代码实现，仅文档/git 操作（git commit 已获用户明确授权）`

---

## 0. 任务复述（Restate First）

- **最终目标（待用户确认）**：将 Hermes Agent 项目的开发工作切换到 SDD-RIPER-ONE 协议下运行——重建标准产物区（codemap / spec / context / archive），摸清当前真实代码状态，为后续任务单元（技术债修复 / Web UI 收尾 / 功能增强）建立可审计的真相源与门禁。
- **当前任务单元（最小混沌单元）**：Pre-Research 收口 + Research 第一阶段——生成项目总图 codemap、落盘本 Spec、明确未提交工作区处置与下一任务单元选择。**本单元不涉及任何代码实现。**
- **已知边界**：单项目（非 multi-project）；中文注释与文档；质量门禁 pytest+mypy+ruff；一个 task 一个 commit。
- **验证方式（Done Contract）**：codemap 与本 Spec 落盘；pytest 基线实测复核；用户确认最终目标与下一任务单元。

## 1. Open Questions（2026-07-17 20:45 已全部由用户决策，见下）

1. ✅ **最终目标确认** → **用户决策：A. TD-002+TD-003**（`subprocess` 沙箱后端 + `config.sandbox.backend` 生效，P0）。
2. ✅ **未提交工作区处置** → **用户决策：立即分批提交**（明确授权 git commit；按 TD-001 / Phase 4.7 / Web UI / 文档同步 分批）。
3. ✅ **AGENTS.md 路由** → **用户决策：新建**（最小路由：仅路由/底线/禁止项，不复制完整 skill）。

## 2. Context Sources

| 来源 | 类型 | 说明 |
|---|---|---|
| `CODEMAP.md`（根目录，2026-07-12 版） | 旧 codemap | 已被本任务新图取代索引地位；缺 web 模块 |
| `docs/progress-spec.md` / `docs/session-context.md` | 旧进度体系 | Phase 1–10 完成记录、工程规范 |
| `docs/evaluation-log.md` | 评测日志 | 基线/Bug/优化/STAR 素材 |
| `.kimi/vibe_specs/technical-debt-spec.md` | 技术债总表 | 9 项 TD，TD-001 已修 |
| `.kimi/vibe_specs/web-ui-spec.md` | 功能 spec | Web UI 已部分实现（代码未提交） |
| 实测：`pytest tests/ -q` | 验证 | **541 passed, 1 skipped**（2026-07-17，与记录一致） |
| 实测：`git status` / `default_prompt_check.py` | 验证 | 未提交改动清单；无 prompt 路由 |

## 3. Codemap Used

- `mydocs/codemap/2026-07-17_20-38_hermes-agent-project.md`（project 模式，本任务生成，含 2 张 Mermaid 图 + 模块索引 + 热点风险）

## 4. Context Bundle Snapshot（Lite）

- **需求快照**：项目主体（Phase 1–10）已完成，进入技术债治理 + 演示增强阶段；用户要求以 SDD-RIPER-ONE 规范重新组织开发流程。
- **关键事实**：工作区有 3 批未提交改动且测试全绿；Web UI 代码已写但 spec 要求的人工确认（TD-008）未做；`subprocess` 后端是 P0 断点。
- **信息缺口**：用户对下一任务单元的取舍、提交策略、AGENTS.md 意愿（见 §1）。

## 5. Research Findings

1. **真实代码状态与文档记录基本一致，且比记录更新**：实测 541 passed / 1 skipped 与 `session-context.md` 基线吻合；mypy/ruff 待 Execute 前复核。
2. **发现文档未覆盖的新增模块**：`src/agent/web/`（FastAPI Web UI，165 行 app + 模板 + 82 行测试）已实现但未提交、未进旧 CODEMAP、未进 progress-spec——spec 与代码存在记录性偏差，已通过新 codemap 修正索引。
3. **技术债优先级**（依 `technical-debt-spec.md` Phase A→D）：P0 = TD-002/003/007（可用性断点）；P1 = TD-004/005（架构扩展性）；P2 = TD-006/008（安全与体验）；P3 = TD-009。
4. **流程基线已具备**：skill 全局安装完成，4 个 skill 可用；`mydocs/` 标准产物区已建立（codemap/specs/context/archive）。
5. **风险**：未提交工作区意味着任何新 Execute 会与存量改动混合，审计粒度变差——建议先做提交决策再进新任务单元。

## 6. Next Actions

1. 等待用户回答 §1 三个 Open Questions（方向 / 提交策略 / AGENTS.md）。
2. 用户确认最终目标后：选定任务单元 → 补充该单元 Research 细节 →（复杂任务进 Innovate）→ Plan → 等待 `Plan Approved`。
3. 若用户批准 AGENTS.md：按 `default-prompt-setup.md` 最小路由模板新建（仅此文件，不改其他）。

## 7. Resume / Handoff 锚点

- **Spec path**：`mydocs/specs/2026-07-17_20-38_project-rebaseline.md`
- **Codemap path**：`mydocs/codemap/2026-07-17_20-38_hermes-agent-project.md`
- **Phase**：RESEARCH（收口待用户输入） | **Status**：LOCKED | **Approval**：N/A
- **恢复指令**：新会话先读本 Spec §0/§1/§6 + codemap §7，即可续接。

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-17 20:38 | sdd_bootstrap：Pre-Research 收口，生成 codemap + 首版 Spec，pytest 基线实测复核 |
| 2026-07-17 20:45 | 用户决策（Reverse Sync）：①下一任务单元=TD-002+003；②立即分批提交未存改动；③新建 AGENTS.md 最小路由 |
| 2026-07-17 20:50 | 质量门禁复核：mypy 42 文件零错误、ruff 全绿（此前 pytest 541 passed 已实测） |
| 2026-07-17 20:52 | 分批提交完成（4 commit）：`ff2777a` TD-001 / `c41738e` Phase 4.7 / `ea2b895` Web UI / `f24281d` 文档同步；工作区干净（仅 `mydocs/` 未跟踪，按隐私边界默认不入库） |
| 2026-07-17 20:55 | 新建 `AGENTS.md` 最小路由并提交（`3b58c78`）；`default_prompt_check.py --mode one` 复核 `Required route found: True` |
| 2026-07-17 20:55 | 本单元 CLOSED；下一任务单元 TD-002+003 另立 Spec：`mydocs/specs/2026-07-17_20-55_td-002-003-subprocess-backend.md` |

## 9. Project Sync Candidates（待用户确认落点，默认不提交）

1. `mydocs/` 已成为标准产物区——候选写入 `AGENTS.md` 或项目文档约定。
2. Web UI 模块存在的事实——候选同步到根 `CODEMAP.md` 与 `docs/progress-spec.md`（随其所属任务单元处理）。
