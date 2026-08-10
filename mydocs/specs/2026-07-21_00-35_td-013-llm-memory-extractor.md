# SDD Spec: TD-013 LLM 对话事实提取器（llm_extraction_enabled 实现）

- **Spec 层级**: Feature Spec
- **创建时间**: 2026-07-21 00:35
- **当前 Phase**: Plan 完成，等待 `Plan Approved`
- **Approval Status**: 未批准
- **关联**: 技术债总表 TD-013；Batch 5（产品边界实证来源）

## 0. Open Questions

- [ ] Q1: `max_age_days` 默认值给多少？（建议 90 天；`None` 保持不清理的现状也可以，见 §3 Fork 3）

## 1. Requirements (Context)

- **Goal**: 实现 `llm_extraction_enabled` 配置承诺的能力——LLM 驱动的对话事实提取，使用户直接陈述的事实与任务摘要进入长期记忆，并顺带接通记忆定时清理。
- **In-Scope**:
  1. `LLMMemoryExtractor`（新类）：用户事实（PREFERENCES）+ 任务摘要（TASK_SUMMARIES）。
  2. 成本护栏：预过滤（无实质用户输入则跳过）+ 每 run 最多 1 次 LLM 调用 + temperature 0 + 有界 max_tokens。
  3. 双层去重：提取时注入现有同类记忆摘要（只输出增量）+ 保存时内容规范化去重。
  4. 记忆定时清理：`max_age_days` 配置 + `cleanup_on_exit` 接线（复用 store 已有的 time-based cleanup 与数量淘汰）。
  5. 验收：单测 + 集成测试 + Batch 5 对话版复验（无文件载体教学 → 跨会话召回）。
- **Out-of-Scope**:
  - 向量检索/embedding；冲突自动合并（只检测提示，复用 TD-009）；
  - 改变 RuleMemoryExtractor 现有行为（两提取器叠加）；
  - `llm_extraction_enabled` 默认值变更（保持 False，用户显式开启）。

### 用户已决项（2026-07-21）

| 决策点 | 决定 |
|---|---|
| 提取范围 | **B**：用户事实 + 任务结果摘要（去重需下功夫——已调研，见 §2） |
| 触发与成本 | **A**：预过滤 + 每 run 最多 1 次 LLM 调用（预过滤需细设计） |
| 冲突处理 | 都存 + recency 优先 + **需要记忆定时清理**（本 Spec 附带接通） |
| 验收方式 | **A**：Batch 5 对话版复验 + 单测 |

## 1.1 Context Sources

- Requirement Source: 技术债总表 TD-013（Batch 5 实证：纯对话事实不入记忆）
- Code Refs:
  - `src/agent/core/memory.py:377`（MemoryExtractor 接口）、`:981`（llm_extractor 参数）、`:1325`（record 已调用 llm_extractor 且失败隔离）、`:46`（PREFERENCES/TASK_SUMMARIES 枚举已在）
  - `src/agent/core/runtime.py:81-90`（当前只传 RuleMemoryExtractor，未接线）
  - `src/agent/config.py:102`（llm_extraction_enabled）、`:105`（cleanup_on_exit）
  - `src/agent/core/memory.py:252`（store.cleanup(max_age) 已存在）、`:1544`（数量淘汰已存在）、`:802+`（冲突检测已存在）
- 调研依据: Batch 5 spec §5 Step 4a（mem 臂对话教学后 memory_search 检索为空）

## 1.5 Codemap Used

- Codemap File: `mydocs/codemap/2026-07-17_20-38_hermes-agent-project.md`（复用）

## 1.7 Minimum Chaos Unit Assessment

- Final Goal: 纯对话教学的事实可跨会话召回（开关开启时），记忆有定时清理能力
- Current Task Unit: 1 个新提取器类 + 2 处接线（runtime/cleanup）+ 去重逻辑 + 测试验收
- Why small enough: 脚手架全部存在（接口/参数/枚举/开关/cleanup/冲突检测），改动集中且默认关闭
- Verification Evidence: 门禁三件套全绿；单测（scripted LLM client）覆盖提取/预过滤/去重/清理；Batch 5 对话版复验通过
- Failure / Rework Plan: LLM 输出解析不稳 → 收紧 JSON 契约 + 容错解析；提取噪声大 → 收紧 prompt 范围
- User Decision: 待批准

## 2. Research Findings（含用户点名的两项调研）

### 2.1 去重现状（Q1 调研结论）

- **已有**：`_detect_preference_conflicts` 等冲突检测（TD-009，memory.py:802+）——能发现重复/矛盾，但只用于 CLI 审计提示，不在保存路径上。
- **缺口**：保存路径无内容级去重——同一事实换说法反复存会膨胀（数量淘汰兜底但不优雅）。
- **方案（双层）**：① 提取时把现有 PREFERENCES 摘要注入 LLM prompt，指令"只输出新增/有变化的事实"（增量提取，摘要通常很小、成本低）；② 保存时对 content 做规范化（去空白/标点）后精确去重，命中则刷新 updated_at 而非新增（recency 语义自然成立）。

### 2.2 记忆清理现状（Q3 调研结论："能做吗"——大部分已存在）

- **已有**：`StructuredMemoryStore.cleanup(max_age)`（time-based 删除，memory.py:252）；`_enforce_category_limit` 数量淘汰（保存时触发）；`stale` 字段；`cleanup_on_exit` 配置（默认 False）。
- **缺口**：`MemoryManager.cleanup()` 目前调 `store.cleanup(None)` = 永不清理；`cleanup_on_exit` 未接线；无 max_age 配置。
- **方案**：新增 `memory.max_age_days: int | None = None`（默认 None 保持现状）；Agent 退出路径（close/reset 或 CLI 收尾）在 `cleanup_on_exit=True` 且 `max_age_days` 非 None 时调用 `store.cleanup(timedelta(days=max_age_days))`。改动约 15 行。

### 2.3 预过滤设计（Q2 细化）

跳过 LLM 调用的条件（全部命中才跳过）：① 本轮无 user 消息；② user 消息总长度 < 20 字符（纯触发语）；③ trace 无任何 tool_execution 事件（纯闲聊但无产出时仍提取一次事实，不提取任务摘要——facts 与 summary 分开判定）。

## 3. Innovate (Optional: Options & Decision)

### Fork 1: 提取器放置
- A. **新文件 `src/agent/core/memory_llm_extractor.py`** → 选 A：memory.py 已 1600+ 行，独立文件可测试性好
- B. 塞入 memory.py：拒绝（文件膨胀）

### Fork 2: 去重策略
- A. **双层（增量 prompt + 规范化精确去重）** → 选 A：调研结论（§2.1）
- B. 仅 recency 都存：用户已补充要求清理配合，A 更完整

### Fork 3: 清理默认值
- A. **`max_age_days: int | None = None`（默认不清理）** → 选 A：不改变现状，用户显式开启；Open Question 问默认值建议
- B. 默认 90 天：改变现有行为，拒绝

### Fork 4: 失败处理
- A. **提取失败静默降级为空列表**（record 已有 try/except 隔离）→ 选 A：提取永不能搞挂主流程

## 4. Plan (Contract)

### 4.1 File Changes

- `src/agent/core/memory_llm_extractor.py`（**新增**）：`LLMMemoryExtractor`
- `src/agent/core/runtime.py`（修改）：`llm_extraction_enabled=True` 时构造并传入 llm_extractor
- `src/agent/config.py`（修改）：`MemoryConfig` 增加 `max_age_days: int | None = None`
- `src/agent/core/memory.py`（修改）：`MemoryManager.cleanup()` 接 `max_age_days`；保存路径加内容规范化去重
- `src/agent/core/engine.py`（修改）：退出路径在 `cleanup_on_exit=True` 时调用 `memory_manager.cleanup()`
- `tests/test_memory_llm_extractor.py`（**新增**）：单测
- `tests/test_memory_integration.py`（修改）：纯对话事实跨会话召回集成测试
- `examples/batch_tasks_b5.py`（修改）：新增 2 个对话版复验任务（T101/T102，无文件载体）
- `docs/configuration.md`（修改）：两个新配置项说明
- `.kimi/vibe_specs/technical-debt-spec.md`（修改）：TD-013 状态流转

### 4.2 Signatures

```python
# src/agent/core/memory_llm_extractor.py
class LLMMemoryExtractor(MemoryExtractor):
    """LLM 驱动的对话事实提取器（PREFERENCES + TASK_SUMMARIES）。

    成本护栏：预过滤 + 每 run 最多 1 次调用 + temperature 0 + max_tokens 有界。
    失败降级：任何异常返回 []（绝不中断主流程）。
    """

    def __init__(self, llm_client: Any, *, max_facts: int = 10) -> None: ...

    def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """预过滤 → 组装 prompt（对话 + 现有 PREFERENCES 摘要）→ 解析 JSON → 构造条目。"""
        ...

    def _should_skip(self, trace: AgentTrace) -> tuple[bool, bool]:
        """返回 (skip_facts, skip_summary)。规则见 §2.3。"""

    @staticmethod
    def _parse_output(text: str) -> tuple[list[dict[str, Any]], str | None]:
        """容错解析 LLM JSON 输出：{"facts": [...], "task_summary": "..."}。"""
```

```python
# src/agent/core/memory.py（MemoryManager 修改）
def cleanup(self) -> int:
    """按 max_age_days 清理过期记忆（None 或 0 删除）。"""
    # self._config.max_age_days 非 None 时：store.cleanup(timedelta(days=...))

def _save_entry(self, entry: MemoryEntry) -> MemoryEntry:
    """保存前内容规范化去重：同类同 content（去空白/标点）命中则刷新 updated_at。"""
```

```python
# src/agent/config.py（MemoryConfig 增加）
max_age_days: int | None = None   # 记忆最大保留天数；None = 不清理（默认）
# llm_extraction_enabled / cleanup_on_exit 已存在，不变
```

### 4.3 Implementation Checklist

- [ ] 1. `config.py` max_age_days + `memory_llm_extractor.py` 提取器（预过滤/增量 prompt/容错解析/降级）+ runtime 接线
- [ ] 2. `memory.py` cleanup 接 max_age_days + 保存规范化去重；`engine.py` 退出清理接线
- [ ] 3. `test_memory_llm_extractor.py`：预过滤规则/JSON 解析/去重/降级/清理（scripted client）→ 门禁三件套全绿
- [ ] 4. 集成测试：对话教学代号 → 新会话召回（开关开）；开关关时不提取（行为不变）
- [ ] 5. Batch 5 对话版复验：T101/T102（无文件载体，`--arms mem`）通过；开关关闭时回退为原边界（文档记录）
- [ ] 6. `docs/configuration.md` 更新；总表 TD-013 状态 → ✅
- [ ] 7. 双环境全量 pytest + mypy + ruff；回写本 Spec §5/§6/§7

### 4.4 Spec Review Notes (Optional Advisory, Pre-Execute)

- 未执行 `review_spec`；如需预审请指示。

### 4.5 Route Alignment (Water Flow Check)

- Original assumption: TD-013 需要新建提取管线
- Current route: 脚手架全在（接口/参数/枚举/开关/cleanup/冲突检测），只需写提取器本体 + 3 处接线
- Scope impact: 默认关闭，现有行为不变

## 5. Execute Log

- [x] Step 1: `config.py` + `max_age_days`；新增 `memory_llm_extractor.py`（预过滤/增量 prompt/容错解析/静默降级）；`runtime.py` 开关接线。**设计修正**：trace 不存完整 messages（只记元数据），改经 `run_metadata["messages"]` 注入（零接口变更，见 §7）
- [x] Step 2: `memory.py` —— `record()` async 化（isawaitable 兼容同步/异步提取器）+ 注入现有 PREFERENCES 摘要（去重第一层）+ `cleanup()` 接 `max_age_days` + `_save_entry` PREFERENCES 规范化去重（第二层）；`engine.py` —— record 调用 await + messages 注入、`close()` 退出清理接线；存量 5 处测试改 async 后 732 全绿
- [x] Step 3: `test_memory_llm_extractor.py` 11 单测（预过滤/解析/降级/去重/清理）；**预过滤阈值修正**：20→8 字符（16 字符真实事实句被误跳过，见 §7）；mypy 47 文件 / ruff / 745 passed 全绿
- [x] Step 4: 集成测试 `TestLlmExtractionIntegration`（对话教学 → 持久化 → 新会话 inject 召回；开关关闭行为不变）通过
- [x] Step 5: **Batch 5 对话版验收**：mem 臂加开 `llm_extraction_enabled`（additive）；新增 T101/T102（无文件载体纯对话教学）→ **mem 臂 4/4 PASS、no-mem 臂 0/4 FAIL（对照成立）**
- [x] Step 6: `docs/configuration.md` 三项配置说明；总表 TD-013 → ✅ 已完成（含修复记录）

## 6. Review Verdict

- Review Matrix (Mandatory):
| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | 纯对话事实可跨会话召回（开关开启）；定时清理可用；默认关闭行为不变 | PASS | T101/T102 验收 4/4；集成测试；745 passed |
| Spec-Code Fidelity | 文件/签名/checklist 与 Plan 一致（3 处设计修正有记录，见 §7） | PASS | checklist 7/7；门禁三件套全绿 |
| Code Intrinsic Quality | 失败静默降级；预过滤成本护栏；dedup 双层；async 兼容不破存量 | PASS | 11 单测 + 存量 732 全绿 |
- Overall Verdict: **PASS**
- Blocking Issues: 无
- Regression risk: Low（默认关闭；存量行为有测试锁定）
- Follow-ups:
  1. 简历口径可补：记忆系统现支持纯对话事实（LLM 提取，PREFERENCES+TASK_SUMMARIES）
  2. Batch 6 候选：大记忆库压力测试；LLM 提取质量抽查（噪声/误提取审计）
  3. `max_age_days` 默认值留用户按运维需要设定（当前 None）

## 7. Plan-Execution Diff

- **消息通道**：Plan 未细究 trace 不存完整 messages 的事实——改经 `run_metadata["messages"]` 注入（engine 传入），零接口变更
- **预过滤阈值**：20→8 字符（实测 16 字符真实事实句被误跳过；纯触发语 ≤4 字符，8 有足够间距）
- **类型设计**：`LLMMemoryExtractor` 不继承 `MemoryExtractor`（async extract 与 sync 基类签名冲突），改 duck-typed + `MemoryManager.llm_extractor: Any`（mypy strict 通过）
- **mem 臂语义**：batch mem 臂加开 `llm_extraction_enabled`（验收所需；对 b5 产物类任务为 additive，不影响其既有口径）
- 其余无偏差。

## 8. Archive Record

- Archive Mode: `snapshot`
- Audience: `both`
- Source Targets:
  - `mydocs/specs/2026-07-21_00-35_td-013-llm-memory-extractor.md`
  - `docs/evaluation-log.md`（2026-07-21 TD-013 验收行）
- Archive Outputs:
  - `mydocs/archive/2026-07-21_00-30_td-013-llm-memory-extractor_human.md`
  - `mydocs/archive/2026-07-21_00-30_td-013-llm-memory-extractor_llm.md`
- Key Distilled Knowledge: run_metadata 扩展通道；提取失败静默降级；双层去重；清理机制"只缺调用点"调研法。

## 9. Project Sync Candidates

- 候选：「记忆系统两类提取器叠加模式（Rule 免费 + LLM 精确，开关隔离）」→ 收口沉淀
- Sync decision: Not synced
