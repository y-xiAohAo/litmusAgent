# 归档：项目级 STAR 定稿（简历流水线）— LLM 视角

> 用途：后续会话接管简历/评测相关工作。只记约束、口径、触点与坑。

## 核心约束（不可违反）

1. **数据红线**：简历任何数字必须 100% 可溯源到 `docs/evaluation-log.md` 或 `docs/batch-e2e-batch*-report.md`；禁止编造、换算夸大、暗示更大样本量。
2. **隐私边界**：`mydocs/`（spec/resume/archive/reports）不入 git；公开仓库只放纯项目内容。
3. **正向表述**：机制效果写提升（88%→98%），不写移除后下降（用户选定口径）。
4. **小样本数字已弃用**：0/8→3/3、5v5 A/B、记忆 0/2→2/2 不再出现在简历（被批量数字替代）。

## 简历当前口径（正式稿 v3，2026-07-21）

| 声称 | 数字 | 出处 |
|---|---|---|
| 规划机制 | L5 成功率 88%→98%（+10pp，120 runs） | batch4 报告聚合表 |
| 反思机制 | 成功率 88%→98%（+10pp） | 同上（no-reflect 对照） |
| 错误恢复 | 0/2→2/2（T73 稳定复现） | batch4 报告采样一致性 |
| 记忆召回 | 0%→100%（80 runs，20 两阶段任务） | batch5 报告 |
| 评测体系 | 80 任务集、三重判分、290+ 次运行、成本可核算 | b1-b5 报告 |
| 工程质量 | 732 测试 / 91% 覆盖 / mypy 零错误 | evaluation-log 基线 |

## 触点

- 简历定稿：`mydocs/resume/litmus-agent-resume.md`（改数字必同步 §3 映射与 Change Log）
- 对标/关键词：`mydocs/resume/2026-07-19_resume-benchmark-analysis.md`、`jd-keyword-analysis.md`
- 批量 Runner：`examples/batch_e2e.py`（`--set b1-b5` `--samples` `--arms`）
- 技术债总表：`.kimi/vibe_specs/technical-debt-spec.md`（TD-013 候选 = 纯对话事实提取器）

## Anti-patterns（不要这么做）

- ❌ 简历写未经批量验证的小样本数字（会被面试官"就跑了几次？"击穿）
- ❌ 把 resume/spec/mydocs 内容提交进 git（隐私边界）
- ❌ 机制效果用"移除后下降"表述（用户已定正向口径）
- ❌ 数字四舍五入夸大（39/40 写 98% 可以，写 100% 不行）

## 下一步钩子

- TD-013 实现：LLM 对话事实提取器（记忆叙事最后一块拼图）
- Batch 6：大记忆库压力 / T73 类地雷 5 采样显著性
- 简历流水线框架化立项（vision seed 触发）

## Trace to Sources

- 主 Spec：`mydocs/specs/2026-07-19_01-50_project-star-finalization.md`
- 批量系列归档：`mydocs/archive/2026-07-20_22-04_batch-e2e-benchmark-series_*.md`
