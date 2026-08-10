# 归档：TD-013 LLM 对话事实提取器 — Human 视角

- **日期**：2026-07-21
- **Feature Spec**：`mydocs/specs/2026-07-21_00-35_td-013-llm-memory-extractor.md`
- **Commit**：`1d34969`

## 背景与目标

Batch 5 实证：规则记忆提取器只覆盖产物/环境/失败模式，用户口头陈述的事实进不了长期记忆（`llm_extraction_enabled` 开关存在两年无实现）。本任务实现该能力，并顺带接通记忆定时清理。

## 方案与决策

- **提取器**：`LLMMemoryExtractor`（新文件），LLM 从每轮对话提取用户事实（PREFERENCES）+ 任务摘要（TASK_SUMMARIES），用户决策范围 B。
- **成本护栏**：预过滤（无实质输入/纯触发语跳过）+ 每 run 最多 1 次调用 + temperature 0 + max_tokens 有界；失败静默降级绝不影响主流程。
- **去重（双层）**：① LLM 注入现有记忆摘要做增量提取；② 保存时内容规范化精确去重（命中刷新 updated_at，recency 语义自然成立）。
- **定时清理**：`max_age_days`（默认 None 不改现状）+ `cleanup_on_exit` 接线——调研发现 store.cleanup 与数量淘汰早已存在，只缺调用点（15 行接通）。
- **冲突**：都存 + recency 优先（复用 TD-009 检测机制，不自动合并）。

## 关键实现发现

1. **Trace 不存完整 messages**（设计如此，只记元数据）——改经 `run_metadata["messages"]` 注入，零接口变更。
2. **`record()` async 化**：LLM 提取必须异步，isawaitable 兼容同步/异步提取器；存量 5 处测试同步改 async。
3. **预过滤阈值实证修正**：20→8 字符（16 字符真实事实句被误跳过）。
4. **mypy strict 下提取器 duck-typed**（async extract 与 sync 基类签名冲突）。

## 结果与证据

- Batch 5 对话版 T101/T102（无文件载体纯口语教学）：**mem 臂 4/4 PASS，no-mem 臂 0/4**——对照成立
- 集成测试（对话事实 → 持久化 → 新会话召回）+ 11 单测
- 门禁：745 passed / mypy 47 文件 / ruff 全绿；总表 TD-013 → ✅ 已完成

## Trace to Sources

- Spec 全程：`mydocs/specs/2026-07-21_00-35_td-013-llm-memory-extractor.md`（§5/§6/§7）
- 验收记录：`docs/evaluation-log.md` 2026-07-21 TD-013 验收行
- 边界实证起源：`mydocs/specs/2026-07-20_22-20_batch-e2e-batch5-memory.md` §5 Step 4a
