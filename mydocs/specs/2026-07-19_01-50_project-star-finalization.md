# Feature Spec — 项目级 STAR 定稿（简历叙事任务）

> **Spec 层级**：Feature Spec（**非代码任务**：叙事/文档产出，RIPER 流程同样适用）
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-19 | **Phase**：`EXECUTE`（B v2 逐句打磨中） | **Status**：`[LOCKED]`
> **Approval Status**：`APPROVED — 2026-07-19 新会话已批准执行，范围经用户确认扩大`
> **交接说明**：本 Spec 是跨会话交接包。新会话只需读本文件 + §3 证据索引所指文档即可执行。
> **v2 变更摘要**：① 流程改为「网络对标驱动」，对标分析见 `mydocs/resume/2026-07-19_resume-benchmark-analysis.md`；② 落盘点从 `docs/evaluation-log.md` 改为 `mydocs/resume/`（公开仓库 litmusAgent 只保留纯项目内容）；③ §3 数字勘误（缺陷 7→6、mypy 46→44 文件、归档 18→16 份）；④ 定位已确认：LLM/Agent 应用工程 · 校招/实习 · 中文简历。

---

## 0. 任务复述（Restate First）

- **最终目标**：为整个 Agent 项目产出**简历可用的项目级 STAR 定稿**（面试叙述版 + 简历正文版），以及一个**独特的项目名**（叙述层）。
- **任务性质**：叙事/写作任务，不是代码任务。验收标准是可读性、准确性、与证据一致性，不是测试通过率。
- **In Scope**：项目命名定夺、STAR 双版本定稿、`docs/evaluation-log.md` 新增"项目级 STAR"章节。
- **Out of Scope**：代码改动、包名/仓库改名（仅叙述层命名）、demo 录制（已决策不做）、新增实验。
- **Done Contract**：
  1. 项目名确定（叙述层，可为直白描述型；仓库名已定 `litmusAgent`），全文统一使用。
  2. STAR 双版本定稿：面试叙述版（~2 分钟口语）+ 简历正文版（简介 + 3-5 条 bullet，方向已定：**B 机制深度流**）。
  3. 每个数字都能在 §3 证据索引中找到出处（不虚构、不夸大）。
  4. 落盘至 `mydocs/resume/`（**变更**：不再写 `docs/evaluation-log.md`，公开仓库仅保留纯项目内容）。

## 1. 命名决策

约束：与 "Hermes" 重名冲突；**仅叙述层改名**（代码包名 `agent` 不动，已决策）。

**进展（2026-07-19 v2）**：远程仓库已上线为 `litmusAgent`（github.com:y-xiAohAo/litmusAgent）；用户明确表示叙述层不强制独特名字，「把技术亮点介绍好」优先。简历项目名可在定稿时用「Litmus Agent」或直白描述型，随 STAR 定稿一并确定。

项目特质（命名锚点）：① 从错误中学习（反思纠错）；② 用实验代替感觉（A/B 对照、真实联调、Done by Evidence）；③ 沙箱隔离与安全；④ 完整工程闭环。

候选（推荐度降序）：

| 名字 | 映射 | 叙事钩子 |
|---|---|---|
| **Litmus**（石蕊试纸，推荐） | 证据驱动 | "每个机制都过了石蕊测试：13 场景联调 + 两组 A/B 实验" |
| **Temper**（回火） | 自我纠错 | "金属回火更韧——Agent 从错误中恢复后更强" |
| **Assay**（化验鉴定） | 沙箱+验证 | "沙箱是化验室，产物皆经鉴定" |
| **Kaizen**（改善） | 持续改进 | "从技术债清零到 EVAL-014，一路改善" |

## 2. STAR 素材草案（起点，定稿时迭代）

### 面试叙述版（~2 分钟）

> **S**：我希望深入理解 LLM Agent 的工程本质——不是调 API 拼 demo，而是回答"一个 Coding Agent 要在真实环境活下来需要哪些机制"。于是从零设计并实现了 <项目名>：一个具备自我纠错能力的代码沙箱 Agent 框架。
>
> **T**：三层目标：① 完整实现 Agent 闭环（规划→执行→观察→纠错→交付）；② 工程质量达到生产标准；③ 所有核心机制必须有真实环境下的量化证据。
>
> **A**：架构上实现双沙箱后端、可插拔工具系统、策略引擎、长期记忆、上下文压缩、反思纠错与自动规划，全部配置驱动；工程上全程 TDD（679 测试、91% 覆盖、mypy strict），用 SDD 流程清零 9 项技术债；验证上建立真实 LLM 联调体系（13 场景套件 + A/B 对照实验）。
>
> **R**：两个控制变量实验——Planner 使多步任务成功率 0/8→3/3，反思机制使无效调用 -26%、轮数 -32%；真实联调揪出并修复 7 个 mock 不可见的缺陷；记忆系统三层重构使跨会话召回 0/2→2/2。所有数字可追溯。

### 简历正文版（3-4 行）

> **<项目名>｜自我纠错的代码沙箱 Agent 框架**（Python，个人项目）
> 设计并实现双沙箱后端、工具系统、策略引擎、长期记忆、上下文压缩与反思纠错机制；以 TDD（679 测试/91% 覆盖/mypy strict）与 SDD 流程完成 9 项技术债清零。建立真实 LLM 联调体系，通过 A/B 实验量化验证核心机制：规划模块使多步任务成功率 0/8→3/3，反思机制使无效调用 -26%，记忆重构使跨会话召回 0/2→2/2；联调共发现并修复 7 个真实环境缺陷。

## 3. 证据索引（定稿时逐条核对）

| 数字 | 出处 | 勘误 |
|---|---|---|
| 679 passed / 91% 覆盖 / mypy 44 文件 / ruff 全绿 | `docs/evaluation-log.md` 项目基线 | mypy 文件数 46→**44**（以基线表为准） |
| 9 项技术债清零 | `.kimi/vibe_specs/technical-debt-spec.md` | — |
| Planner 0/8→3/3（S4p）、自动规划 2/2（S4-auto） | `docs/evaluation-log.md` E2E 表 | — |
| 反思机制 -26% 失败调用 / -32% 轮数（5v5） | `docs/evaluation-log.md` 2026-07-19 A/B 行 | — |
| 记忆召回 0/2→2/2 | `docs/evaluation-log.md` S6 复验行 | — |
| **6** 个真实缺陷（EVAL-009~014；EVAL-010 即 docker 权限） | `docs/evaluation-log.md` Bug 清单 | 原写 7 个，系 docker 权限重复计数 |
| 13 场景联调（11 个 S 场景 + Web UI + CLI chat，另 4 组对照） | `docs/evaluation-log.md` E2E 表 | 口径已明确 |
| 归档复盘 16 份 | `mydocs/archive/` | 原写 18 份 |

## 4. 执行 Checklist

- [x] 0. 网络对标分析 → `mydocs/resume/2026-07-19_resume-benchmark-analysis.md`（2026-07-19 用户批准）
- [x] 1. 仓库名确定：`litmusAgent` 已上线；叙述层项目名随定稿确定（可为直白描述型）
- [x] 2a. 风格选定：简介 + bullet 形态，**B 机制深度流**（2026-07-19 用户选定）
- [x] 2b. 简历正文版逐句打磨（B v1→v6 定稿，用户逐轮批准）
- [x] 2c. 面试叙述版派生（~2 分钟，用户批准为预留稿）
- [x] 3. 数字逐条对账（§3 索引，含勘误）
- [x] 4. 落盘 `mydocs/resume/litmus-agent-resume.md`（**预留稿**：数字栏位待批量 E2E 升级）
- [x] 5. README 及全仓显示名更新为 Litmus Agent（2026-07-19 已推送 `3dfa423`；技术标识符 hermes:// URI、.hermes/ 目录、docker 服务名、包名 agent 按既定决策保留）
- [x] 6. Review：终检三项（数字对账 / ATS 覆盖 / 扫读自检）通过
- [x] 7. 批量 E2E → 数字升级 → 转正式稿（✅ 2026-07-21 完成：b1-b5 五批迭代、累计 290+ 次真实运行；简历预留稿转**正式稿 v3**，五个 bullet 全部批量级数字；证据链 `docs/batch-e2e-batch{1,2,3,4,5}-report.md`）

## 5. 交接锚点（Resume / Handoff）

- **当前状态（2026-07-21 v6，任务全部闭环）**：R1-R5 + 批量 E2E 升级全部完成。简历为**正式稿 v3**（`mydocs/resume/litmus-agent-resume.md`）——五个 bullet 全部批量级数字（规划/反思 +10pp、记忆 100% vs 0%、80 任务 290+ 次运行、723→732 测试基线）；仓库 litmusAgent 已上线。
- **新会话启动指令**：读本 Spec → 待决项已全部关闭 → 新任务请走完整 SDD-RIPER-ONE 立项。
- **待决项（按优先级）**：
  1. ~~批量 E2E → 预留稿转正式稿~~（✅ 2026-07-21 完成：b1-b5 五批，正式稿 v3）；
  2. ~~文档小债：mypy 基线 44→46~~（✅ 2026-07-19 已还，`docs/evaluation-log.md` 已更新推送）；
  3. ~~设想未落盘：简历流水线框架化~~（✅ 2026-07-19 已落盘为 vision seed：`2026-07-19_resume-pipeline-framework-vision.md`，未来触发再立项）。
- **约束**：不新增实验（批量 E2E 除外，需单独立项）、数字必须可溯源（§3 勘误后口径 + 数据红线）。

## 7. 正式执行计划（2026-07-19 用户批准）

**验收标准（Done Contract 细化）**：① 每条 bullet 符合对标结论（痛点→方案→量化结果；术语带"做了什么"）；② 数字零虚构、可溯源；③ 通过 10 秒扫读 / ATS 关键词覆盖 / 朗读（≤2 分钟）三项检查；④ 定稿落盘 `mydocs/resume/`，过程稿留痕。

| Round | 内容 | 产出 | 状态 |
|---|---|---|---|
| R1 | 样本收集（8+3 个样本：高赞改造文/真实点评/JD/全文级模板） | `2026-07-19_resume-benchmark-analysis.md` | ✅ 完成 |
| R2 | JD 关键词 × 简历覆盖矩阵（7 份真实 JD） | `mydocs/resume/jd-keyword-analysis.md` | ✅ 完成 |
| R3 | 逐句打磨（B v1→v6，每轮 1-3 处，逐轮批准） | B v6 定稿 | ✅ 完成 |
| R4 | 面试叙述版派生 | ~2 分钟口语版 | ✅ 完成（预留稿） |
| R5 | 终检三项通过 + 落盘 + Change Log | `mydocs/resume/litmus-agent-resume.md`（**预留稿**） | ✅ 完成 |

**节奏约定**：每 Round 产出物经用户批准后进入下一 Round，不跳轮。

**数据红线（2026-07-19 用户强调）**：简历中"评估体系"及一切数字，必须 100% 来自 `docs/evaluation-log.md` 的真实 LLM E2E 记录（场景数、A/B 样本量、前后对照均按原始口径），禁止编造、换算夸大或暗示更大样本量。这是本任务的最高优先级约束。

## 6. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-19 | 任务确立（上一会话收尾）：范围/候选名/草案/证据索引/交接锚点全部落盘，待新会话执行 |
| 2026-07-19 v2 | 新会话执行：定位确认（LLM/Agent 校招·中文）→ 网络对标分析完成并获批准 → 数字勘误（6 缺陷/44 文件/16 份）→ 仓库 litmusAgent 上线（简历内容全部留本地 mydocs/）→ 风格选定 B 机制深度流，进入逐句打磨 |
| 2026-07-19 v3 | 正式执行计划（R1-R5）批准并全轮执行：R1 补强（7 份真实 JD + 3 份全文级样本）→ R2 JD 关键词矩阵 → R3 五轮打磨收敛（B v6）→ R4 叙述版 → R5 终检落盘 `mydocs/resume/litmus-agent-resume.md`（**预留稿**，用户裁定：测试样本太少，数字栏位待批量 E2E 升级，批量 E2E 已立 seed spec） |
| 2026-07-19 v4 | 交接审计：修复 §5/§7 状态滞后（原停留在 B v2），补齐待决项清单；README 及全仓显示名已改 Litmus Agent（`3dfa423` 已推送） |
| 2026-07-19 v5 | 收尾：mypy 基线文档债已还（`8cbc236`）；简历流水线框架设想落盘为 vision seed；kimi-cli 升级已由用户自行完成 |
| 2026-07-21 v6 | **任务闭环**：批量 E2E 五批迭代（b1 基线 → b2 提难度 → b3 开放+工具断言 → b4 L5+采样 → b5 记忆专项）完成，累计 290+ 次真实运行、约 305 万 tokens；简历预留稿转**正式稿 v3**（规划/反思各 +10pp、记忆 100% vs 0%、五 bullet 全批量数字）；checklist 7/7 完成，待决项清零 |

## 8. Archive Record

- Archive Mode: `snapshot`
- Audience: `both`
- Source Targets:
  - `mydocs/specs/2026-07-19_01-50_project-star-finalization.md`
  - `mydocs/resume/litmus-agent-resume.md`
  - `docs/batch-e2e-batch{1,2,3,4,5}-report.md`
- Archive Outputs:
  - `mydocs/archive/2026-07-21_00-30_project-star-finalization_human.md`
  - `mydocs/archive/2026-07-21_00-30_project-star-finalization_llm.md`
- Key Distilled Knowledge: SDD 项目→简历流水线（证据对账→网络对标→JD 矩阵→逐句打磨→批量升级→终检）；数据红线纪律（零虚构、可溯源）；小样本数字必须升级为批量统计。
