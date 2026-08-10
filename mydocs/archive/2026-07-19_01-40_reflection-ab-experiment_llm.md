# 归档（LLM 视角）— 反思层 A/B 对照实验与 EVAL-014

> 生成：2026-07-19 | 模式：snapshot | 受众：llm（后续会话续接用）
> Source Index：`docs/evaluation-log.md`、`src/agent/tools/file_*.py` diff、实验原始输出
> 冲突标记：无

---

## 1. 约束（Constraints，新增）

- **工具错误文本必须携带异常类名前缀**（`FileNotFoundError:` / `OSError:`）——`_classify_tool_error` 依赖 `(\w+Error|\w+Exception)` 正则，纯中文文案会使分类→账本→反思全链静默（EVAL-014）。
- 写新工具时遵循同一约定：错误 content 以 `<ExceptionName>: <中文描述>` 开头。

## 2. 实测行为事实（Facts）

1. DeepSeek v4-flash：可降级任务 1 次失败即自愈（v1，反思无需触发）；不可能任务会变换战术直到触顶（v2）。
2. 反思层触发条件：同（工具+异常类型）错误 ≥2 次——强模型自然行为下罕见。
3. 修复后 A/B（受限工具+重复 FileNotFoundError）：反思开=轮数 5.0/失败 8.6/事件 33；反思关=7.4/11.6/0（-32% 轮数、-26% 失败调用）。
4. 两组均 5/5 如实报告——反思层价值在"收敛速度"而非"结局正确性"。

## 3. 反模式（Anti-patterns，新增）

1. ❌ 错误文案只写自然语言描述不带异常身份（反思/日志分析链路全断）。
2. ❌ 用单组观测代替 A/B 对照下结论（S8 的教训：有反思事件≠机制有效）。
3. ❌ 实验设计不考虑模型方差（v1 单版数据差点被误读为"无差异"）。

## 4. 下一步钩子

1. 项目级 STAR 定稿：以整个 Hermes Agent 为主语，功能/实验为证据。
2. 候选：反思阈值自适应（按模型强度调 reflection_threshold）。
3. 当前 git HEAD：`717be2d`。
