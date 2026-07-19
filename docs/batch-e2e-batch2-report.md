# 批量 E2E 评测报告 Batch 2（20 高难任务 × 3 机制臂）

- 运行时间：2026-07-19 21:39
- 模型：deepseek-chat（OpenAI 兼容端点）；judge 与执行同模型（temperature=0）
- 采样说明：每 task×arm 单样本
- 原始数据：`mydocs/reports/b2_raw.jsonl`；任务定义 `examples/batch_tasks_b2.py`
- 臂定义：full = planner 开 + 反思开；no-planner = planner 关 + 反思开；no-reflect = planner 开 + 反思关

## 聚合指标

| 机制臂 | 成功率 | 平均轮数 | 总 token | 平均 token/run | 失败分类分布 |
|---|---|---|---|---|---|
| full | 20/20（100%） | 5.5 | 189,626 | 9,481 | — |
| no-planner | 20/20（100%） | 5.0 | 161,697 | 8,085 | — |
| no-reflect | 20/20（100%） | 5.0 | 176,540 | 8,827 | — |

- 总消耗：**527,863 tokens**（60 runs，约 25 分钟）
- 判分方式：18 任务沙箱断言 + 2 任务 LLM-judge

## 观察与局限（如实记录）

1. **三臂全部 100%**：即使引入了确定性陷阱（脏数据、并列约定、预埋 bug、跨文件编辑链），deepseek-chat 在当前 prompt 形态下仍全部通过，机制对照差异为 0。
2. **planner 开销可见但未换来收益**：full 臂平均轮数 +10%（5.5 vs 5.0）、平均 token +17%（9,481 vs 8,085）。合理解释：b2 任务的 prompt 普遍显式分步（"1) 2) 3) 4)"），等于用户预先完成了规划，planner 在此形态下是纯开销。这与 S4 场景（prompt 不预分解，planner 0/8→3/3）不矛盾——两者测量的是不同 prompt 形态。
3. **产物断言看不到工具偏好失败**：S4 的失败模式是"跳过 file_edit 改用 sandbox_exec"；b2 的断言只检查最终产物，不检查工具使用路径，该类失败对本批不可见。
4. **结论外推边界**：本批结果只能表述为"在显式分步、单样本、20 任务规模下，机制开关不影响成功率"；不能表述为"机制无用"。
5. Batch 3 候选方向：开放式 prompt（不预分解，恢复 planner 测量条件）+ 工具使用路径断言（记录 trace 工具序列）+ 更长链路/更弱约束。

## 与 Batch 1 的口径差异

Batch 1 的 "full" 臂为 planner 关 + 反思开（当时未接 planner）；Batch 2 的 full 臂为 planner 开 + 反思开。两批绝对值不可直接比较。

## 明细

| 任务 | 臂 | 判分 | 结果 | 轮数 | token | 耗时s |
|---|---|---|---|---|---|---|
| T21 | full | assert | ✅ | 4 | 5,503 | 18.4 |
| T22 | full | assert | ✅ | 4 | 6,811 | 16.8 |
| T23 | full | assert | ✅ | 5 | 6,589 | 19.1 |
| T24 | full | assert | ✅ | 4 | 5,733 | 16.5 |
| T25 | full | assert | ✅ | 4 | 6,005 | 16.3 |
| T26 | full | assert | ✅ | 7 | 13,389 | 29.8 |
| T27 | full | assert | ✅ | 4 | 8,198 | 24.3 |
| T28 | full | assert | ✅ | 4 | 6,912 | 19.8 |
| T29 | full | assert | ✅ | 3 | 5,192 | 17.8 |
| T30 | full | assert | ✅ | 8 | 11,938 | 26.8 |
| T31 | full | assert | ✅ | 10 | 15,884 | 40.9 |
| T32 | full | assert | ✅ | 9 | 13,485 | 33.4 |
| T33 | full | assert | ✅ | 7 | 10,102 | 29.5 |
| T34 | full | assert | ✅ | 5 | 6,922 | 24.2 |
| T35 | full | assert | ✅ | 7 | 14,673 | 30.8 |
| T36 | full | assert | ✅ | 4 | 5,672 | 22.7 |
| T37 | full | assert | ✅ | 7 | 9,576 | 24.4 |
| T38 | full | assert | ✅ | 5 | 7,363 | 19.6 |
| T39 | full | llm-judge | ✅ | 4 | 8,970 | 21.4 |
| T40 | full | llm-judge | ✅ | 4 | 20,709 | 45.4 |
| T21 | no-planner | assert | ✅ | 4 | 4,683 | 13.0 |
| T22 | no-planner | assert | ✅ | 4 | 6,184 | 15.4 |
| T23 | no-planner | assert | ✅ | 4 | 4,936 | 15.3 |
| T24 | no-planner | assert | ✅ | 3 | 3,911 | 12.3 |
| T25 | no-planner | assert | ✅ | 4 | 5,390 | 15.9 |
| T26 | no-planner | assert | ✅ | 5 | 8,909 | 22.0 |
| T27 | no-planner | assert | ✅ | 3 | 6,533 | 20.8 |
| T28 | no-planner | assert | ✅ | 5 | 8,959 | 19.5 |
| T29 | no-planner | assert | ✅ | 3 | 5,267 | 17.0 |
| T30 | no-planner | assert | ✅ | 7 | 9,679 | 22.2 |
| T31 | no-planner | assert | ✅ | 8 | 11,010 | 28.6 |
| T32 | no-planner | assert | ✅ | 7 | 9,083 | 26.2 |
| T33 | no-planner | assert | ✅ | 7 | 9,428 | 25.5 |
| T34 | no-planner | assert | ✅ | 4 | 5,325 | 22.7 |
| T35 | no-planner | assert | ✅ | 5 | 8,584 | 21.6 |
| T36 | no-planner | assert | ✅ | 5 | 6,407 | 17.8 |
| T37 | no-planner | assert | ✅ | 7 | 8,966 | 24.2 |
| T38 | no-planner | assert | ✅ | 6 | 8,289 | 20.7 |
| T39 | no-planner | llm-judge | ✅ | 5 | 10,667 | 25.6 |
| T40 | no-planner | llm-judge | ✅ | 3 | 19,487 | 48.3 |
| T21 | no-reflect | assert | ✅ | 4 | 5,572 | 17.7 |
| T22 | no-reflect | assert | ✅ | 4 | 6,963 | 19.3 |
| T23 | no-reflect | assert | ✅ | 5 | 6,848 | 18.4 |
| T24 | no-reflect | assert | ✅ | 4 | 5,842 | 16.5 |
| T25 | no-reflect | assert | ✅ | 5 | 8,277 | 21.9 |
| T26 | no-reflect | assert | ✅ | 6 | 11,177 | 27.4 |
| T27 | no-reflect | assert | ✅ | 3 | 7,041 | 20.0 |
| T28 | no-reflect | assert | ✅ | 3 | 4,912 | 14.8 |
| T29 | no-reflect | assert | ✅ | 4 | 7,849 | 18.5 |
| T30 | no-reflect | assert | ✅ | 7 | 10,036 | 22.6 |
| T31 | no-reflect | assert | ✅ | 6 | 8,793 | 29.3 |
| T32 | no-reflect | assert | ✅ | 7 | 9,666 | 27.1 |
| T33 | no-reflect | assert | ✅ | 7 | 10,131 | 31.0 |
| T34 | no-reflect | assert | ✅ | 5 | 7,015 | 23.5 |
| T35 | no-reflect | assert | ✅ | 5 | 8,884 | 24.2 |
| T36 | no-reflect | assert | ✅ | 4 | 5,668 | 21.3 |
| T37 | no-reflect | assert | ✅ | 7 | 9,622 | 24.7 |
| T38 | no-reflect | assert | ✅ | 5 | 7,302 | 20.6 |
| T39 | no-reflect | llm-judge | ✅ | 5 | 10,811 | 23.8 |
| T40 | no-reflect | llm-judge | ✅ | 4 | 24,131 | 49.8 |
