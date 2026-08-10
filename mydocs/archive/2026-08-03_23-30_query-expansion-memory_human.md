# 归档：查询扩展（Multi-Query Expansion）记忆检索增强 — Human 视角

- **日期**：2026-08-03
- **Feature Spec**：`mydocs/specs/2026-08-03_23-05_query-expansion-memory.md`
- **Commit**：`5ff166d`

## 背景与目标

Batch 6 实证：硬 paraphrase 查询（"发布用的编号"→"构建标签"）双臂 0/2 稳定失败，瓶颈在搜索词联想而非检索机制。目标：修复该类失败且不改变现状行为。

## 调研与选型

调研四种查询扩展路线后选定 **Multi-Query 扩展**（rewrite-retrieve-read 标准管线）：

| 方法 | 结论 |
|---|---|
| Multi-Query（LLM 生成 N 个同义变体，分别检索合并） | ✅ 选用：复用字面检索器，零新基础设施 |
| HyDE（假设答案文档 embedding 检索） | ❌ 需向量库（无）；关键词退化版不如 Multi-Query 直接 |
| Query2doc / Step-back | ❌ 面向长文档语义检索，精确事实召回过重 |
| Agentic 澄清（反问用户） | ❌ 破坏无人值守 |

参考：rewrite-retrieve-read（arXiv:2511.01386）、HyDE 对比（arXiv:2502.04095）、DMQR（arXiv:2411.13154）。

## 方案与结果

- **机制**：`search()` fallback 链 L1 命中（零成本）→ **QE 扩展层**（失配才触发：LLM 生成 3-5 个同义变体，逐一字面检索合并去重）→ L2 → L0；LLM 失败静默降级。
- **验收（16 runs，约 4 万 tokens）**：mem-qe **8/8（100%）** vs mem-default 5/8（63%）；**T122（b6 双臂 0/2 稳定失败）在 qe 臂 2/2 复活**；搜索词运气型分裂（T123）被稳定为 2/2。
- **工程约束**：默认关闭（`query_expansion_enabled: false`）；命中零成本有测试锁定；7 单测；760 passed / mypy 47 / ruff 全绿。

## 关键认知

- **QE 与 L2 语义重排的分工**：L2 只重排注入候选（b6 已证无增量）；QE 直接治疗字面失配（搜索词联想失败）——两者位置不同、对症不同，共存不冲突（QE 优先，L2 兜底）。
- **成本设计的价值**：仅失配触发使该能力在字面命中为主的场景下几乎免费。

## Trace to Sources

- Spec 全程：`mydocs/specs/2026-08-03_23-05_query-expansion-memory.md`（§5/§6/§7）
- 验收记录：`docs/evaluation-log.md` 2026-08-03 QE 验收行
- 失败根因：`docs/batch-e2e-batch6-report.md` 核心发现§3
