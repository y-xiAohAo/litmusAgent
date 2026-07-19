# 批量 E2E 评测报告 Batch 1（20 任务 × 2 机制臂）

- 运行时间：2026-07-19 19:58
- 模型：deepseek-chat（OpenAI 兼容端点）；judge 与执行同模型（temperature=0）
- 采样说明：每 task×arm 单样本（Batch 1 口径）
- 原始数据：`mydocs/reports/batch1_raw.jsonl`（本地）；任务定义 `examples/batch_tasks.py`；Runner `examples/batch_e2e.py`

## 聚合指标

| 机制臂 | 成功率 | 平均轮数 | 总 token | 平均 token/run | 失败分类分布 |
|---|---|---|---|---|---|
| full（反思开启） | 20/20（100%） | 4.1 | 118,384 | 5,919 | — |
| no-reflect（反思关闭） | 20/20（100%） | 4.5 | 128,629 | 6,431 | — |

- 总消耗：**247,013 tokens**（40 runs，含 judge 调用）
- 判分方式：16 任务沙箱断言（退出码）+ 4 任务 LLM-judge（rubric 打分，≥4 通过）

## 观察与局限（如实记录）

1. **任务集对当前模型偏易**：双臂 100% 通过、零失败样本，无法产生失败分类分布，也不足以区分机制差异。Batch 2 应提高难度（更长链路、更易错的约束）。
2. **弱信号（不构成结论）**：no-reflect 臂平均轮数 +0.4（4.5 vs 4.1）、平均 token +8.7%（6,431 vs 5,919），与"反思机制提升效率"的方向一致，但单样本、零失败下统计强度不足。
3. judge 任务（T17-T20）两轮均通过，rubric 判分稳定；judge 与执行同模型存在自评偏差风险（已记入 Spec）。
4. 与既有场景抽查（S1-S12，含失败案例）互补：本批为标准化批量基线，场景抽查覆盖更难/更特异的机制点。

## 明细

| 任务 | 臂 | 判分 | 结果 | 轮数 | token | 耗时s |
|---|---|---|---|---|---|---|
| T01 | full | assert | ✅ | 4 | 4,788 | 13.3 |
| T02 | full | assert | ✅ | 4 | 4,630 | 13.0 |
| T03 | full | assert | ✅ | 3 | 3,607 | 10.9 |
| T04 | full | assert | ✅ | 4 | 4,667 | 13.8 |
| T05 | full | assert | ✅ | 4 | 4,786 | 13.6 |
| T06 | full | assert | ✅ | 3 | 2,885 | 9.1 |
| T07 | full | assert | ✅ | 5 | 6,121 | 16.5 |
| T08 | full | assert | ✅ | 4 | 4,720 | 13.7 |
| T09 | full | assert | ✅ | 3 | 5,427 | 12.1 |
| T10 | full | assert | ✅ | 5 | 5,737 | 17.8 |
| T11 | full | assert | ✅ | 4 | 4,792 | 15.9 |
| T12 | full | assert | ✅ | 4 | 4,915 | 14.3 |
| T13 | full | assert | ✅ | 3 | 3,595 | 11.2 |
| T14 | full | assert | ✅ | 5 | 6,424 | 20.6 |
| T15 | full | assert | ✅ | 4 | 4,614 | 12.9 |
| T16 | full | assert | ✅ | 7 | 10,352 | 21.4 |
| T17 | full | llm-judge | ✅ | 4 | 8,213 | 19.8 |
| T18 | full | llm-judge | ✅ | 3 | 6,387 | 19.5 |
| T19 | full | llm-judge | ✅ | 3 | 6,119 | 15.8 |
| T20 | full | llm-judge | ✅ | 6 | 15,605 | 38.0 |
| T01 | no-reflect | assert | ✅ | 4 | 4,568 | 14.9 |
| T02 | no-reflect | assert | ✅ | 4 | 4,502 | 13.0 |
| T03 | no-reflect | assert | ✅ | 4 | 5,039 | 13.7 |
| T04 | no-reflect | assert | ✅ | 4 | 4,854 | 13.0 |
| T05 | no-reflect | assert | ✅ | 4 | 4,997 | 13.5 |
| T06 | no-reflect | assert | ✅ | 3 | 2,924 | 9.4 |
| T07 | no-reflect | assert | ✅ | 5 | 6,117 | 16.2 |
| T08 | no-reflect | assert | ✅ | 4 | 4,713 | 13.0 |
| T09 | no-reflect | assert | ✅ | 4 | 4,720 | 15.9 |
| T10 | no-reflect | assert | ✅ | 5 | 5,706 | 16.8 |
| T11 | no-reflect | assert | ✅ | 4 | 4,746 | 14.9 |
| T12 | no-reflect | assert | ✅ | 4 | 4,735 | 14.8 |
| T13 | no-reflect | assert | ✅ | 3 | 3,665 | 11.5 |
| T14 | no-reflect | assert | ✅ | 6 | 7,464 | 19.6 |
| T15 | no-reflect | assert | ✅ | 4 | 4,656 | 13.0 |
| T16 | no-reflect | assert | ✅ | 6 | 8,582 | 19.3 |
| T17 | no-reflect | llm-judge | ✅ | 5 | 10,548 | 23.5 |
| T18 | no-reflect | llm-judge | ✅ | 5 | 10,575 | 23.8 |
| T19 | no-reflect | llm-judge | ✅ | 4 | 8,839 | 21.0 |
| T20 | no-reflect | llm-judge | ✅ | 7 | 16,679 | 38.8 |
