# Phase 8.4 开发接力文档：记忆审计、用户反馈与可选增强

> **本文档目标**：为下一个 session 提供足够上下文，使其能在 Phase 8.1~8.3 已完成基线上继续推进 Phase 8.4（可选增强）。
> 
> **状态**：规划文档 / 待审批后实施。
> 
> **最后更新**：2026-07-04

---

## 1. 当前基线（进入 8.4 之前的状态）

### 1.1 已完成交付

| Task | 状态 | 关键文件 |
|------|------|----------|
| 8.1 存储层 + 数据模型 | ✅ | `src/agent/core/memory.py`（`MemoryCategory`, `MemoryEntry`, `MemoryQuery`, `MemoryStore`, `StructuredMemoryStore`） |
| 8.2 提取/管理层 | ✅ | `src/agent/core/memory.py`（`RuleMemoryExtractor`, `MemoryInjector`, `MemoryManager`） |
| 8.3 主循环集成 | ✅ | `src/agent/core/engine.py`, `src/agent/tools/memory_read.py`, `src/agent/tools/__init__.py` |
| 8.3 边界测试 | ✅ | `tests/test_memory_integration.py`（8 个集成测试） |

### 1.2 质量基线

```bash
pytest tests/ -q        # → 331 passed, 1 skipped（tiktoken 未安装）
mypy src/               # → Success: no issues found in 31 source files
ruff check src/ tests/  # → All checks passed!
```

- Git 分支：`master`，HEAD `d2860ea`
- 工作区：干净，无未提交修改

### 1.3 默认行为（必须保持）

- `MemoryConfig.enabled` 默认 `False`，未启用时 Phase 1~7 行为不变。
- 记忆注入/记录/读取失败必须内部捕获异常，**不阻塞主循环**。
- `memory_read` 是内部工具，不受 `config.tools.enabled` 控制，受 `register_memory_read` 控制。

---

## 2. Phase 8.4 范围与边界

### 2.1 来源

完整设计见 `.kimi/vibe_specs/long_term_memory-spec.md` §10.4，核心内容如下：

> - 用户反馈打分（thumbs up/down）
> - 记忆与当前环境冲突检测
> - 陈旧/低置信度记忆自动降权或标灰
> - CLI 命令：`hermes memory list`、`hermes memory delete <id>`
> - 可选：LLM 自我审计记忆有效性

### 2.2 推荐优先级

建议按以下顺序实现，方便每轮都能独立验收：

| 优先级 | 模块 | 内容 | 理由 |
|--------|------|------|------|
| P0 | 用户反馈 | `MemoryManager.record_feedback(entry_id, score)` + CLI `hermes memory feedback` | 数据简单、风险低、为后续排序提供信号 |
| P0 | CLI 管理 | `hermes memory list` / `delete` / `show` | 用户可手动管理记忆，立即有用 |
| P1 | 检索排序增强 | 把 `confidence` / 反馈 / 陈旧度纳入注入排序 | 让“好记忆”优先被 LLM 看到 |
| P1 | 冲突检测 | 规则检测同类记忆矛盾（如同一包不同版本） | 避免 LLM 看到互相冲突的提示 |
| P2 | 陈旧降权 | 按时间和类别自动降低 confidence 或标灰 | 与冲突检测配合，减少噪声 |
| P2（可选） | LLM 审计 | 小模型评估记忆是否仍有效 | 依赖外部调用，默认关闭 |

### 2.3 严禁做

延续 Phase 8 整体约束：

- 不引入向量/图数据库（FAISS、Chroma、Neo4j 等）。
- 不修改现有 Tool（`sandbox_exec`、`file_read`、`file_list`、`finish`、`context_read`）的签名或行为。
- 不替换 `ReflectiveAdvisor` / `ErrorPatternLedger`；只能可选消费它们的事件。
- 不默认开启长期记忆。
- 不让记忆相关失败阻塞主循环或改变 `Agent.run()` 返回值。

---

## 3. 现有接口速查（供扩展使用）

### 3.1 数据模型

```python
# src/agent/core/memory.py
@dataclass
class MemoryEntry:
    entry_id: str
    category: MemoryCategory          # environment / artifacts / failure_patterns / task_summaries / preferences
    content: dict[str, Any]
    summary: str
    tags: list[str]
    source_trace_id: str | None
    source_run_id: str | None
    uri: str                          # 标准格式 hermes://memory/<category>/<entry_id>.jsonl
    created_at: datetime
    updated_at: datetime
    confidence: float = 1.0
```

### 3.2 存储层

```python
class StructuredMemoryStore(MemoryStore):
    def save(self, entry: MemoryEntry) -> MemoryEntry: ...
    def get(self, entry_id: str) -> MemoryEntry | None: ...
    def query(self, query: MemoryQuery) -> list[MemoryEntry]: ...
    def delete(self, entry_id: str) -> bool: ...
    def cleanup(self, max_age: timedelta | None = None) -> int: ...
    def list_entries(self, category: MemoryCategory | None = None) -> list[MemoryEntry]: ...
```

### 3.3 管理层

```python
class MemoryManager:
    def inject(self, user_input: str) -> str: ...
    def record(self, trace, state, run_metadata=None) -> list[MemoryEntry]: ...
    def cleanup(self) -> int: ...
    def read(self, uri: str) -> str | None: ...
```

### 3.4 配置

```python
class MemoryConfig(BaseModel):
    enabled: bool = False
    backend: str = "structured"
    memory_root: str = ".hermes/memory"
    max_entries_per_category: int = 100
    retrieval_top_k: int = 5
    inject_max_entries: int = 5
    inject_max_tokens: int = 800
    persist_error_patterns: bool = True
    filter_sensitive: bool = True
    sensitive_patterns: list[str] = ...
    llm_extraction_enabled: bool = False
    summarizer_model: str = "gpt-4o-mini"
    summarizer_max_tokens: int = 512
    cleanup_on_exit: bool = False
    register_memory_read: bool = True
```

---

## 4. 推荐设计草案

### 4.1 数据模型扩展

在 `MemoryEntry` 末尾追加可选字段（全部有默认值，不破坏现有构造）：

```python
@dataclass
class MemoryEntry:
    # ... 已有字段 ...
    confidence: float = 1.0

    # 8.4 新增
    feedback_score: int | None = None       # -1 踩 / 0 中性 / 1 赞；None 表示无反馈
    feedback_count: int = 0                 # 反馈动作次数
    last_feedback_at: datetime | None = None
    stale: bool = False                     # 显式标灰
    linked_entry_ids: list[str] = field(default_factory=list)  # 审计时建立的关联
```

> 注意：`_entry_to_dict` / `_entry_from_json` 需要同步处理新字段；已有文件缺少这些字段时回退到默认值。`expires_at` 本次不引入。

### 4.2 用户反馈

#### API

```python
class MemoryManager:
    def record_feedback(self, entry_id: str, score: int) -> bool:
        """记录用户对某条记忆的反馈。

        Args:
            entry_id: 记忆 id。
            score: -1 / 0 / 1。

        Returns:
            是否成功更新。
        """
```

#### 实现要点

- 仅当 `self._config.enabled` 为 True 时执行。
- 内部捕获异常，失败返回 `False`。
- 更新 `feedback_score`、`feedback_count`、`last_feedback_at`。
- 对多次反馈**只保留最新一次** score，但 `feedback_count` 递增，`last_feedback_at` 更新。在 CLI help 中说明 `feedback_count` 为反馈动作次数。

#### CLI

```bash
python scripts/hermes-memory.py feedback <entry_id> --score 1
python scripts/hermes-memory.py feedback <entry_id> --score -1
```

### 4.3 CLI 管理命令

由于 Phase 10 才会建完整 CLI，Phase 8.4 先提供一个**独立脚本**，避免与未来 CLI 架构冲突：

| 命令 | 作用 | 示例 |
|------|------|------|
| `list` | 列出记忆，支持按 category 过滤 | `python scripts/hermes-memory.py list --category environment` |
| `show` | 显示单条记忆完整 JSON | `python scripts/hermes-memory.py show <entry_id>` |
| `delete` | 删除指定记忆 | `python scripts/hermes-memory.py delete <entry_id>` |
| `feedback` | 给记忆打分 | `python scripts/hermes-memory.py feedback <entry_id> --score 1` |
| `audit` | 手动触发冲突/陈旧扫描 | `python scripts/hermes-memory.py audit` |
| `export` | 导出 Markdown memory-bank | `python scripts/hermes-memory.py export` |

建议文件：

- `src/agent/cli/__init__.py`
- `src/agent/cli/memory_cli.py`（纯 argparse，无外部依赖）
- `scripts/hermes-memory.py`（入口包装）

### 4.4 检索排序增强（注入质量）

当前 `MemoryStore.query` 只按字符重叠分和 `updated_at` 排序。8.4 建议在 `MemoryManager.inject` 中做二次排序：

```python
def _rank_entries(self, entries: list[MemoryEntry]) -> list[MemoryEntry]:
    # 1. 陈旧降权
    # 2. 反馈升权
    # 3. confidence 作为乘数
    # 最终按综合得分 + updated_at 排序
```

实现策略：

- 从 `store.query` 拉取 `retrieval_top_k * 2` 条候选。
- 计算每条候选的 `effective_score = overlap_score * confidence * feedback_multiplier * stale_multiplier`。
- 按 `effective_score` 降序，再按 `updated_at` 降序。
- 截取前 `inject_max_entries` 条给 `MemoryInjector.format`。

乘数建议：

| 条件 | multiplier |
|------|------------|
| `feedback_score == 1` | 1.5 |
| `feedback_score == -1` | 0.3 |
| `feedback_score is None` 或 `0` | 1.0 |
| `confidence < 1.0` | 乘以 confidence |

**连续衰减公式（替代阶跃 stale multiplier）**：

```python
age_days = (now - entry.updated_at).total_seconds() / 86400
half_life = (
    config.environment_stale_days
    if entry.category == MemoryCategory.ENVIRONMENT
    else config.stale_threshold_days
)
stale_multiplier = 0.5 ** (age_days / half_life)
```

> 注：`stale` 布尔字段由 `audit()` 显式写回，用于人类可读标记；排序时直接使用连续衰减，不依赖 `stale` 布尔值。

### 4.5 冲突检测

新增 `MemoryConflictDetector`：

```python
@dataclass
class MemoryConflict:
    conflict_type: str          # "version_mismatch", "contradiction", "duplicate"
    entry_ids: list[str]
    reason: str
    suggested_action: str       # "keep_latest", "downgrade", "manual_review"

class MemoryConflictDetector:
    def detect(self, store: MemoryStore) -> list[MemoryConflict]: ...
```

规则示例（可逐步增加）：

- **environment / version_mismatch**：同名包出现多个不同 version。
- **artifacts / duplicate**：相同 `path` 出现多条记录。
- **preferences / contradiction**：相同 key 的 value 不同。
- **failure_patterns / recovery_conflict**：相同 `(tool, exc_type)` 但 recovery action 不同。

冲突检测**仅在 CLI `audit` 触发**，不在 `MemoryManager.record()` 中自动运行，避免改动 `record()` 接口和 `engine.py`。

发现冲突时，把相关条目的 `linked_entry_ids` 单向链接起来（新条目链接到旧条目），并保存回 store。`linked_entry_ids` 8.4 仅作为审计元数据，不参与 `inject()` 排序。

### 4.6 陈旧降权

配置项（新增到 `MemoryConfig`）：

```python
stale_threshold_days: int = 30       # 通用类别半衰期（天）
environment_stale_days: int = 7      # environment 类别半衰期（天）
```

实现：

- 在 `MemoryManager.inject()` 的二次排序中按 §4.4 连续衰减公式计算 `stale_multiplier`，**只读不写**。
- `MemoryManager.audit()` 显式扫描并按 category 阈值把过期条目 `stale=True`，**保存回 store**。
- CLI `audit` 命令可触发。
- 时间基准使用 `updated_at`：用户反馈后会刷新 `updated_at`，使记忆"复活"。

### 4.7 LLM 自我审计（已移至 Phase 8.5）

`LLMMemoryAuditor` 和 `LLMMemoryExtractor` 不放入 Phase 8.4。

原因：
- 需要 LLM 调用、输出解析、错误降级，复杂度高。
- Agent 自主记忆写入工具（`memory_search` / `memory_write` 等）需要 Phase 9 安全策略引擎监管。

Phase 8.5 方向：
- 激活 `LLMMemoryExtractor`，从 Trace 提取高质量 task summary / preferences / code facts。
- 可选增加 `MemoryAuditor` 评估记忆有效性。
- 增加 Agent 可调用记忆工具。

---

## 5. 建议任务拆分

| 子任务 | 内容 | 涉及文件 | 验收标准 |
|--------|------|----------|----------|
| 子任务 | 内容 | 涉及文件 | 验收标准 |
|--------|------|----------|----------|
| 8.4.1 | 扩展 `MemoryEntry` 字段 + 序列化兼容 | `src/agent/core/memory.py` | 旧文件读取不报错；新字段有默认值；mypy/ruff 通过 |
| 8.4.2 | 用户反馈 API + 测试 | `src/agent/core/memory.py`, `tests/test_memory_feedback.py` | `record_feedback` 覆盖成功/失败/未启用/多次覆盖 |
| 8.4.3 | CLI 骨架 + `list/show/delete/feedback` | `src/agent/cli/memory_cli.py`, `scripts/hermes-memory.py`, `tests/test_memory_cli.py` | 命令能列出/显示/删除/反馈 `.hermes/memory/` 中的条目 |
| 8.4.4 | 注入排序增强（confidence/反馈/连续衰减） | `src/agent/core/memory.py`, `tests/test_memory_manager.py` | 测试验证反馈/时间衰减影响排序 |
| 8.4.5 | 冲突检测 + `linked_entry_ids` | `src/agent/core/memory.py`, `tests/test_memory_conflict.py` | 覆盖 4 类冲突；验证单向链接保存 |
| 8.4.6 | 陈旧自动标灰 + `audit` CLI | `src/agent/core/memory.py`, `src/agent/config.py`, `tests/test_memory_conflict.py` | `audit()` 正确标灰；配置生效 |
| 8.4.7 | Markdown memory-bank 导出 | `src/agent/cli/memory_cli.py`, `tests/test_memory_cli.py` | 导出文件可读、敏感信息已过滤 |
| 8.4.8 | 文档同步 | `docs/progress-spec.md`, `docs/session-context.md`, `docs/plans/phase-8.4-plan.md` | 文档与实现一致 |

---

## 6. 测试策略

- **单元测试**：每个新类/方法独立测试，使用 `tmp_path` 构造 `StructuredMemoryStore`。
- **集成测试**：通过 `Agent` + Mock LLM 验证 `memory_recorded` 事件包含反馈/冲突信息。
- **CLI 测试**：用 `subprocess` 或导入 `memory_cli.main` 测试参数解析与输出。
- **兼容性测试**：用 Phase 8.1~8.3 生成的旧 JSONL 文件验证反序列化不崩溃。

---

## 7. 关键决策与开放问题

### 已确定

1. 不引入外部数据库，继续用 JSONL + 文件系统。
2. Phase 8.4 默认全部关闭/可选，不破坏现有行为。
3. CLI 先以独立脚本形式存在，不与未来 Phase 10 CLI 抢命名空间。

### 已确定决策

1. **反馈保留最新值**，`feedback_count` 递增。
2. **冲突检测仅在 CLI `audit` 触发**，不接入 `record()`。
3. **陈旧阈值**：`stale_threshold_days=30`，`environment_stale_days=7`；使用 `updated_at` 作为时间基准；排序采用连续指数衰减。
4. **`linked_entry_ids` 单向链接**（新条目 → 旧条目），不参与 8.4 排序。
5. **Markdown 导出到 `.hermes/memory-bank/`**，单向导出。
6. **`expires_at` / `access_count` / `detect_conflicts_on_record` / LLM 审计不做**，LLM 提取与 Agent 记忆工具移至 **Phase 8.5**。

---

## 8. 恢复开发状态

```bash
cd /d/djh/hermes/project1
python -m pytest tests/ -q      # 确认 331 passed, 1 skipped
python -m mypy src/             # 确认无类型错误
python -m ruff check src/ tests/ # 确认 lint 通过
git log --oneline -5            # 确认 HEAD 在 d2860ea 之后
```

---

## 9. 参考

- 完整设计 spec：`.kimi/vibe_specs/long_term_memory-spec.md`
- Phase 8 实现：
  - `src/agent/core/memory.py`
  - `src/agent/core/engine.py`
  - `src/agent/tools/memory_read.py`
  - `src/agent/tools/__init__.py`
  - `src/agent/config.py`
- 测试：
  - `tests/test_memory_store.py`
  - `tests/test_memory_extractor.py`
  - `tests/test_memory_manager.py`
  - `tests/test_memory_integration.py`
- 本计划：`docs/plans/phase-8.4-plan.md`
