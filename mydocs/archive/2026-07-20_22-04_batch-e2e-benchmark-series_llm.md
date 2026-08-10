# 归档：批量 E2E 评测体系建设（b1-b6）— LLM 视角

> 用途：后续会话快速接管批量评测体系。只记约束、契约、触点与坑。

## 核心约束（未来任务必须遵守）

1. **判分规格自包含**：prompt 是唯一合同——verify 断言的每个要素（文件路径/格式/函数名/精度）必须显式写进 prompt。b3 的 T47/T48/T51 三个判分 bug 全部源于"假设 agent 读懂意图"。
2. **难度设计三要素**：① 不给步骤枚举（显式分步会抵消 planner 测量条件）；② 埋确定性陷阱（naive 解法必错）；③ 工具路径断言（产物对但工具错 = FAIL）。
3. **重复采样 ≥2**：单样本失败无法区分稳定失败与模型抖动；b3 的 T42 孤例靠 b4 双采样才定性。
4. **机制臂构造**：full = `config.agent.planner.enabled=True` + 默认 advisor；no-reflect = planner 开 + `ReflectiveAdvisor(reflection_threshold=10**9, escalate_threshold=10**9)`（无 src 改动）。
5. **EVAL-015**：token 成本经 `client.usage_totals` 统计（additive，不影响契约）。

## 代码触点

| 触点 | 位置 | 说明 |
|---|---|---|
| 批量 Runner | `examples/batch_e2e.py` | `--set b1-b4` `--arms` `--samples N` `--echo`；JSONL 落 `mydocs/reports/` |
| 任务集 | `examples/batch_tasks{,_b2,_b3,_b4}.py` | `BatchTask` dataclass（verify_script XOR judge_rubric；expected_tools/artifact_path 可选） |
| 判分链 | run_one 内 | agent.run → trace 提取工具序列 → 沙箱内执行 verify_script / LLM-judge（temp=0，≥4 过） |
| 机制开关 | `src/agent/core/engine.py:346-352` | planner enabled 读取点 |
| 反思关闭 | `src/agent/core/reflective_advisor.py:171` | 高阈值注入法 |

## 已验证事实（带出处）

- L5 难度 planner +10pp（98/88/88%）→ `docs/batch-e2e-batch4-report.md`
- T73 nobody 写 /etc 必然 Permission denied（docker 实证）→ b4 报告§2
- 反思在零失败场景不触发（规则式，threshold=2）→ b3 报告§3
- deepseek-chat 处理 L1-L4 显式分步任务天花板：三臂 100% → b2 报告
- 记忆对照 mem 100% vs no-mem 0%（80 runs，两阶段跨会话）→ `docs/batch-e2e-batch5-report.md`
- **规则提取器不覆盖纯对话事实**（只产物/环境/失败；`llm_extraction_enabled` 有开关无实现）→ TD-013；b5 spec §5 Step 4a
- 提取器按路径去重（同路径二次写入被跳过）→ `memory.py:482`（冲突更新须用新文件承载新值）
- file_write 内容快照截断 200 字 → `memory.py:480`（干扰任务拆文件规避）
- 100 条库下字面检索 100% 稳健（30 天深埋、15 相似干扰）→ `docs/batch-e2e-batch6-report.md`
- **L2 语义重排无可测增量**（双臂 92%；只重排注入候选，不改 memory_search 字面本质）→ b6 报告§2
- 硬 paraphrase 瓶颈在搜索词联想（T122 双臂 0/2）非检索机制 → b6 报告§3
- 程序化种子零成本测压（21.3 万 tokens/80 runs）→ `examples/batch_e2e.py:seed_memory`

## Anti-patterns（不要这么做）

- ❌ 显式分步 prompt（"1) 2) 3)"）测 planner——等于替 LLM 规划完
- ❌ 只断言产物不断言工具路径——S4 式失败（跳过 file_edit）会被吞
- ❌ verify 引用 prompt 未指定的文件名/函数名/格式
- ❌ 单样本下结论（尤其失败样本）
- ❌ BatchRunResult 位置参数错位（echo 分支踩过：sample 塞进 tools）

## 下一步钩子

- 查询扩展（LLM 生成同义搜索词再检索）——T122 类失败的直接解法，可立项
- Batch 7 候选：200+ 条 / 90 天深埋压力上限；LLM 提取质量审计
- TD-013 已实现；judge 异构化：引入第二 provider 消除自评偏差

## Trace to Sources

- 六份 Spec：`mydocs/specs/2026-07-19_17-50` / `20-05` / `21-50` / `23-20` / `2026-07-20_22-20` / `2026-07-21_23-10`（batch*）
- 公开报告：`docs/batch-e2e-batch{1,2,3,4,5,6}-report.md`
- 原始数据：`mydocs/reports/b{1,2,3,4,5,6}_raw.jsonl`
