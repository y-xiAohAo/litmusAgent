# 归档：项目级 STAR 定稿（简历流水线）全闭环 — Human 视角

- **日期**：2026-07-21
- **Source Index**：
  - `mydocs/specs/2026-07-19_01-50_project-star-finalization.md`（主 Spec，checklist 7/7）
  - `mydocs/resume/litmus-agent-resume.md`（正式稿 v3）
  - `docs/batch-e2e-batch{1,2,3,4,5}-report.md`（数字证据）

## 任务全貌

为 Litmus Agent 项目产出简历可用的项目级 STAR 定稿。两阶段完成：

**阶段一（2026-07-19，R1-R5）**：网络对标（8+3 样本）→ JD 关键词矩阵（7 份真实 JD）→ 逐句打磨（B v1→v6，用户逐轮批准）→ 叙述版派生 → 终检落盘**预留稿**（结构措辞定稿，数字待升级）。

**阶段二（2026-07-19~21，批量 E2E 升级）**：五批迭代建成批量评测体系（详见 batch 系列归档），简历预留稿转**正式稿 v3**——五个 bullet 全部批量级数字：

| Bullet | 数字 | 出处 |
|---|---|---|
| 自动规划 | L5 成功率 88%→98%（+10pp，120 次运行） | batch4 报告 |
| 自我反思 | 成功率 88%→98%（+10pp） | batch4 报告 |
| 长期记忆 | 跨会话召回 0%→100%（80 次对照） | batch5 报告 |
| 安全执行 | 双沙箱 + 策略引擎 + 人工确认 | TD-006/008 |
| 工程质量 | 732 测试 / 91% 覆盖 / mypy 零错误 | evaluation-log 基线 |

## 关键决策

- **数据红线**：所有数字 100% 来自 evaluation-log 与 batch 报告真实记录，零虚构、不暗示更大样本量（用户强调的最高优先级约束）。
- **正向表述**：机制效果写"88%→98% 提升"而非"移除后下降"（用户选定）。
- **旧小样本数字全删**（用户决定）：0/8→3/3、5v5 A/B、记忆 0/2→2/2 均被批量数字替代。
- **隐私边界**：简历内容全部留本地 `mydocs/`（不入 git）；公开仓库只保留纯项目内容。

## 方法论沉淀（简历流水线）

`证据对账（evaluation-log）→ 网络对标 → JD 关键词矩阵 → 逐句打磨（逐轮批准）→ 批量 E2E 升级数字 → 终检三项（对账/ATS/扫读）`

该流水线已抽象为 vision seed（`mydocs/specs/2026-07-19_resume-pipeline-framework-vision.md`），可复用于任何按 SDD 规范开发的项目。

## Trace to Sources

- 主 Spec 全流程：`2026-07-19_01-50_project-star-finalization.md` §4/§5/§6/§7
- 批量证据：`docs/batch-e2e-batch{1,2,3,4,5}-report.md`、`mydocs/archive/2026-07-20_22-04_batch-e2e-benchmark-series_*.md`
- 简历定稿：`mydocs/resume/litmus-agent-resume.md`（v3 + Change Log）
