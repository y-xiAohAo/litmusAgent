# 归档：TD-013 LLM 对话事实提取器 — LLM 视角

> 用途：后续会话维护/扩展记忆系统。只记约束、契约、触点与坑。

## 核心约束（未来任务必须遵守）

1. **提取失败必须静默降级**（返回 []）——记忆是增强，永不能搞挂 Agent 主流程。
2. **成本护栏不可拆**：预过滤（无 user 输入/<8 字符纯触发语跳过）+ 每 run 最多 1 次 LLM 调用 + temperature 0 + max_tokens 有界。
3. **默认关闭**：`llm_extraction_enabled` / `cleanup_on_exit` / `max_age_days` 默认都不改变现状；开启路径才有测试义务。
4. **run_metadata 是扩展通道**：messages / existing_preferences 都经它注入——新增提取器数据源走这里，不改 MemoryExtractor 接口。

## 触点

| 触点 | 位置 | 说明 |
|---|---|---|
| LLM 提取器 | `src/agent/core/memory_llm_extractor.py` | duck-typed（勿继承 MemoryExtractor——async 签名冲突，mypy strict 会炸） |
| 调度点 | `memory.py:record()`（async） | isawaitable 兼容；注入 existing_preferences（去重第一层） |
| 去重第二层 | `memory.py:_save_entry` | PREFERENCES 规范化去重（`_normalize_preference_text`） |
| 定时清理 | `memory.py:MemoryManager.cleanup()` + `engine.py:close()` | `max_age_days` + `cleanup_on_exit` 配合 |
| 接线 | `runtime.py:81-93` | 开关开启才构造 LLMMemoryExtractor |
| 验收任务 | `examples/batch_tasks_b5.py` T101/T102 | 对话版复验（无文件载体） |

## 已验证事实

- 纯对话教学跨会话召回 mem 4/4 vs no-mem 0/4（2026-07-21 验收）
- trace 不存完整 messages（engine.py:701 注释"不保存完整 messages，只记录元数据"）
- 预过滤 8 字符阈值：纯触发语 ≤4、真实事实句 ≥9（16 字符事实句曾被 20 阈值误杀）
- 提取器按路径去重：同路径二次 file_write 只保留首个快照（`memory.py:482`）

## Anti-patterns（不要这么做）

- ❌ 在 sync extract 里直接调 async LLM（运行中循环不能嵌套；走 isawaitable 路径）
- ❌ 让提取异常向上抛（record 的 try/except 是最后防线，不是设计）
- ❌ 无预过滤直接每 run 调 LLM（token 成本失控）
- ❌ 改 llm_extraction_enabled 默认值为 True（静默改变行为 + 静默产生成本）

## 下一步钩子

- Batch 6：大记忆库压力（50+ 事实，memory_search 必要性）+ LLM 提取质量审计（噪声/误提取抽查）
- 提取器增强候选：冲突自动合并（当前只检测）；TASK_SUMMARIES 进检索排序优化

## Trace to Sources

- Spec：`mydocs/specs/2026-07-21_00-35_td-013-llm-memory-extractor.md`
- 测试：`tests/test_memory_llm_extractor.py`、`tests/test_memory_integration.py::TestLlmExtractionIntegration`
- 总表条目：`.kimi/vibe_specs/technical-debt-spec.md` TD-013
