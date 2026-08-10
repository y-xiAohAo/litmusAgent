# 归档：查询扩展（Multi-Query Expansion）— LLM 视角

> 用途：后续会话维护/扩展记忆检索。只记约束、契约、触点与坑。

## 核心约束（未来任务必须遵守）

1. **仅失配触发**：QE 层只在原查询 L1 失配时调用 LLM（命中零成本）——不要把扩展移到命中路径上。
2. **失败静默降级**：LLM 异常/输出不可解析 → 返回 []，调用方按原 fallback 链继续（L2 → L0）。
3. **默认关闭**：`query_expansion_enabled: false`；开启路径才有测试义务。
4. **合并去重**：entry_id 首次出现顺序保留（排前的变体结果优先）；原查询结果天然优先。

## 触点

| 触点 | 位置 | 说明 |
|---|---|---|
| QE 实现 | `memory.py:_expand_and_retrieve()` | 变体解析（剥离编号/项目符号/原查询去重/上限 5） |
| QE prompt | `memory.py:_QE_PROMPT` | 含 T122 同型双示例（提高变体质量的关键） |
| fallback 链 | `memory.py:search()` | L1 → QE → L2 → L0 |
| 验收臂 | `examples/batch_e2e.py` `mem-qe` | 记忆开 + QE 开（不开 LLM 提取） |
| 验收任务 | `examples/batch_tasks_b6.py` T122-T125 | 硬 paraphrase 复验（零共享词） |

## 已验证事实（带出处）

- QE 修复硬 paraphrase：qe 8/8 vs default 5/8，T122 复活 2/2（2026-08-03 验收 16 runs）
- L1 命中时不触发 LLM 调用（`test_memory_query_expansion.py::test_hit_skips_expansion`）
- QE 与 L2 分工：L2 重排注入（b6 证无增量），QE 治字面失配（本验收）
- 搜索词运气是真实方差源：default 臂 T123 分裂 ✅❌，qe 稳定 2/2

## Anti-patterns（不要这么做）

- ❌ 每次搜索都先调 LLM 扩展（成本失控且无益——字面命中占多数）
- ❌ 让 QE 异常向上抛（静默降级是契约）
- ❌ 用 QE 替代 L2 或删除 L2（分工不同，共存）
- ❌ 变体不加数量上限（噪声膨胀稀释排序）

## 下一步钩子

- Batch 7：QE 全量回归 b6（23 任务 × mem-qe，验证字面命中场景无回归）
- QE 变体质量抽查（prompt 迭代）；200+ 条压力上限；LLM 提取质量审计

## Trace to Sources

- Spec：`mydocs/specs/2026-08-03_23-05_query-expansion-memory.md`
- 测试：`tests/test_memory_query_expansion.py`
- 调研归档：`mydocs/archive/2026-08-03_23-30_query-expansion-memory_human.md`（方法选型对比表）
