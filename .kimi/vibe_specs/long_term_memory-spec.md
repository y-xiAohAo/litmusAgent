# Phase 8 Spec：长期记忆机制（Event-Driven Structured Sandbox Memory）

> 本 spec 覆盖 Phase 8 长期记忆机制的设计、接口、风险与验收标准。
> 设计前提：基于现有 Hermes Agent 架构，**增强其它 Phase 但不依赖它们**，默认关闭，MVP 不引入向量数据库/embedding。

---

## 1. 目标

1. 跨 session / 跨进程持久化代码沙箱 Agent 的关键知识：
   - 沙箱环境状态（已安装包、Python 版本、镜像）
   - 已生成产物元数据（路径、类型、摘要、来源任务）
   - 失败模式与已验证恢复策略
   - 任务摘要
   - 用户偏好
2. 让 Agent 在多次启动后能基于过去的执行经验更快、更稳地完成任务。
3. 与 Phase 5~9 保持解耦，默认关闭，不破坏现有行为。

---

## 2. 核心概念

| 术语 | 定义 |
|---|---|
| **MemoryEntry** | 单条长期记忆，结构化数据 + 元数据。 |
| **MemoryCategory** | 记忆类别：`environment`、`artifacts`、`failure_patterns`、`task_summaries`、`preferences`。 |
| **MemoryQuery** | 检索请求，支持 category、tags、text、top_k、time_range。 |
| **MemoryStore** | 存储抽象，负责持久化读写。 |
| **MemoryExtractor** | 提取抽象，负责从 Trace/State 生成 MemoryEntry。 |
| **MemoryManager** | 编排层：提取、检索、注入、清理。 |
| **MemoryInjector** | 把检索到的记忆格式化成 LLM 上下文片段。 |
| **Memory URI** | `hermes://memory/<category>/<entry_id>.jsonl`，统一寻址。 |

---

## 3. 设计原则

1. **事件驱动、规则提取为主**：默认 `RuleMemoryExtractor` 不调用 LLM，从 Trace 事件和 State 中确定性提取事实。
2. **LLM 提取可选**：`LLMMemoryExtractor` 通过注入 `Summarizer` 或独立 LLM client 生成高质量任务摘要。
3. **元数据 + URI 引用**：大内容引用 Phase 7 `hermes://context/...`，记忆文件不复制原始输出。
4. **默认关闭**：`MemoryConfig.enabled` 默认 `False`，行为与 Phase 7 一致。
5. **最小侵入主循环**：记忆是侧车组件，失败不阻塞主循环。
6. **人类可读/可审计**：存储为 JSONL/YAML，方便 CLI 展示和手动修正。

---

## 4. 数据模型

### 4.1 MemoryCategory 与 MemoryEntry

```python
from enum import Enum

class MemoryCategory(str, Enum):
    """长期记忆的类别枚举。"""

    ENVIRONMENT = "environment"
    ARTIFACTS = "artifacts"
    FAILURE_PATTERNS = "failure_patterns"
    TASK_SUMMARIES = "task_summaries"
    PREFERENCES = "preferences"
```

```python
@dataclass
class MemoryEntry:
    """单条长期记忆实体。"""

    entry_id: str                          # uuid4 hex
    category: MemoryCategory               # 记忆类别
    content: dict[str, Any]                # 结构化 payload，按 category 定义 schema
    summary: str                           # 一句话摘要，用于注入 LLM
    tags: list[str] = field(default_factory=list)  # 检索标签
    source_trace_id: str | None = None     # 来源 Trace id（可选）
    source_run_id: str | None = None       # 来源 run id
    uri: str = ""                          # hermes://memory/<category>/<entry_id>.jsonl
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0                # 0.0 ~ 1.0，规则提取默认 1.0
```

#### 字段含义

| 字段 | 类型 | 含义 |
|---|---|---|
| `entry_id` | `str` | 唯一标识，也是文件名的一部分 |
| `category` | `MemoryCategory` | 决定 `content` 的 schema |
| `content` | `dict[str, Any]` | 实际保存的结构化数据 |
| `summary` | `str` | 注入 system prompt 时显示的一句话摘要 |
| `tags` | `list[str]` | 检索关键词，由 RuleMemoryExtractor 自动生成 |
| `source_trace_id` | `str \| None` | 来源 Trace id，用于审计 |
| `source_run_id` | `str \| None` | 来源 run id |
| `uri` | `str` | 统一资源标识 |
| `created_at` / `updated_at` | `datetime` | 创建/更新时间 |
| `confidence` | `float` | 可信度，LLM 提取时可低于 1.0 |

### 4.2 各类别 content schema

| 类别 | content 字段示例 |
|---|---|
| `environment` | `{"packages": [{"name": "pandas", "version": "2.1.0"}], "python_version": "3.11", "image": "python:3.11-slim"}` |
| `artifacts` | `{"path": "/workspace/report.md", "type": "markdown", "description": "销售数据分析报告", "source_task": "analyze sales.csv"}` |
| `failure_patterns` | `{"tool": "sandbox_exec", "exc_type": "ModuleNotFoundError", "error_signature": "ModuleNotFoundError: pandas", "signature_detail": {"missing_module": "pandas"}, "recovery": "pip install pandas", "resolved": true, "occurrences": 3}` |

`failure_patterns` 的 `signature_detail` 是可选的、类型不固定的 dict，用于扩展：

| exc_type | `signature_detail` 示例 |
|---|---|
| `ModuleNotFoundError` | `{"missing_module": "pandas"}` |
| `NameError` | `{"missing_variable": "df"}` |
| `KeyError` | `{"missing_key": "date"}` |
| `AttributeError` | `{"missing_attribute": "colum"}` |
| `SyntaxError` | `{"line_hint": "x = "}` |
| `TypeError` / `ValueError` / 其它 | `{"first_line": "..."}` 或空 dict |
| `task_summaries` | `{"goal": "分析 sales.csv", "outcome": "生成 report.md", "key_decisions": [...], "unresolved": []}` |
| `preferences` | `{"key": "chart_library", "value": "matplotlib", "scope": "user"}` |

### 4.3 MemoryQuery

```python
@dataclass
class MemoryQuery:
    categories: list[MemoryCategory] | None = None
    tags: list[str] | None = None
    text: str | None = None
    top_k: int = 5
    time_range: tuple[datetime, datetime] | None = None
```

---

## 5. 模块与接口

### 5.1 新增文件

| 文件 | 核心抽象 | 职责 |
|---|---|---|
| `src/agent/core/memory.py` | `MemoryStore`, `MemoryExtractor`, `MemoryManager`, `MemoryInjector`, 数据模型 | 记忆子系统核心 |
| `src/agent/tools/memory_read.py` | `memory_read(uri)` | LLM 按需读取记忆内容（可选） |
| `src/agent/config.py` | `MemoryConfig` | 配置 schema |
| `src/agent/core/engine.py` | `Agent` 集成点 | 初始化、注入、记录 |

### 5.2 MemoryStore

```python
class MemoryStore(ABC):
    @abstractmethod
    def save(self, entry: MemoryEntry) -> MemoryEntry: ...
    @abstractmethod
    def get(self, entry_id: str) -> MemoryEntry | None: ...
    @abstractmethod
    def query(self, query: MemoryQuery) -> list[MemoryEntry]: ...
    @abstractmethod
    def delete(self, entry_id: str) -> bool: ...
    @abstractmethod
    def cleanup(self, max_age: timedelta | None = None) -> int: ...
    @abstractmethod
    def list_entries(self, category: MemoryCategory | None = None) -> list[MemoryEntry]: ...
```

**默认实现：`StructuredMemoryStore`**

- 存储根目录：`.hermes/memory/`
- 目录结构：`.hermes/memory/<category>/<entry_id>.jsonl`
- 每条记忆独立一行 JSONL，便于追加和人工查看。
- `query` 实现：先按 category/tags 过滤，再对 text 做简单关键词/token 重叠排序。

### 5.3 MemoryExtractor

```python
class MemoryExtractor(ABC):
    @abstractmethod
    def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]: ...
```

**默认实现：`RuleMemoryExtractor`**

- 从 `trace.to_dict()` 中扫描事件：
  - `tool_execution`（`sandbox_exec` 成功且包含 `pip install`）→ `environment`
  - `tool_execution`（`file_read`/`sandbox_exec` 产生文件路径）→ `artifacts`
  - `error_classification` + `reflection` → `failure_patterns`
  - `state_transition` 到 `finished` + artifacts → `task_summaries`
- 不调用 LLM。

**可选实现：`LLMMemoryExtractor`**

- 接收注入的 `Summarizer` 或独立 `llm_client`。
- 只用于生成 `task_summaries` 和高质量 `preferences`。
- 失败时返回空列表，不阻塞规则提取结果。

### 5.4 MemoryManager

```python
class MemoryManager:
    def __init__(
        self,
        store: MemoryStore,
        extractor: MemoryExtractor,
        config: MemoryConfig,
    ) -> None: ...

    def inject(self, user_input: str) -> str:
        """根据用户输入检索相关记忆，返回要附加到 system prompt 的上下文片段。

        返回空字符串表示无相关记忆或注入被禁用。
        Agent 负责将该片段追加到 system prompt，不直接修改 messages。
        """

    def record(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        """从 Trace/State 提取记忆并持久化。"""

    def cleanup(self) -> int:
        """清理过期记忆。"""
```

### 5.5 MemoryInjector

- 把 `MemoryEntry` 列表格式化为一段 `[历史记忆]` 文本块。
- 受 `inject_max_tokens` / `inject_max_entries` 限制。
- 默认注入位置：`system prompt` 末尾（在 Planner 进度之后），避免破坏 system prompt 主干。

---

## 6. 配置 Schema

在 `AgentRuntimeConfig` 中新增 `memory: MemoryConfig`：

```python
class MemoryConfig(BaseModel):
    enabled: bool = False
    backend: str = "structured"           # 仅 structured，语义检索预留
    memory_root: str = ".hermes/memory"
    max_entries_per_category: int = 100
    retrieval_top_k: int = 5
    inject_max_entries: int = 5
    inject_max_tokens: int = 800
    persist_error_patterns: bool = True
    filter_sensitive: bool = True
    sensitive_patterns: list[str] = Field(default_factory=lambda: [
        "api_key", "password", "secret", "token", "private_key"
    ])
    llm_extraction_enabled: bool = False
    summarizer_model: str = "gpt-4o-mini"
    summarizer_max_tokens: int = 512
    cleanup_on_exit: bool = False         # 长期记忆默认不清理
    register_memory_read: bool = True
```

对应 YAML：

```yaml
agent:
  memory:
    enabled: false
    backend: structured
    memory_root: .hermes/memory
    max_entries_per_category: 100
    retrieval_top_k: 5
    inject_max_entries: 5
    inject_max_tokens: 800
    persist_error_patterns: true
    filter_sensitive: true
    llm_extraction_enabled: false
    summarizer_model: gpt-4o-mini
    summarizer_max_tokens: 512
    cleanup_on_exit: false
    register_memory_read: true
```

---

## 7. 主循环集成

### 7.1 Agent.__init__

新增参数：

```python
memory_manager: MemoryManager | None = None,
```

如果 `config.agent.memory.enabled == True` 且未注入 `memory_manager`，则创建默认：

- `StructuredMemoryStore(root_dir=Path(memory_config.memory_root))`
- `RuleMemoryExtractor()`
- 若 `llm_extraction_enabled=True` 且提供了 `summarizer_llm_client`，则组合 `LLMMemoryExtractor`
- 若 `register_memory_read=True`，注册 `memory_read` 内部工具

### 7.2 Agent.run

```text
run(user_input):
  1. 启动阶段：
     - 追加 user 消息
     - self._memory_context = ""
     - 若启用记忆：
         self._memory_context = memory_manager.inject(user_input)
  2. 主循环：
     - _build_openai_messages() 在 system prompt 末尾附加 self._memory_context
     - 其余逻辑不变
  3. 结束阶段（finish / fatal / max_turns）：
     - 若启用记忆：memory_manager.record(self.trace, self.state)
     - _finalize_run(...)
```

注入约束：

- 每次 `run()` 独立查询、独立注入，避免不同任务互相污染。
- 注入内容追加在 system prompt 末尾（Planner 进度之后），属于头部消息，受 Phase 7 压缩的 `protect_first_n` 保护。
- 注入总长度受 `inject_max_tokens` / `inject_max_entries` 硬限制，防止记忆本身撑爆上下文。

### 7.3 Trace 事件

新增 `memory_recorded` 事件：

```json
{
  "run_id": "...",
  "entries_count": 4,
  "categories": ["environment", "artifacts", "failure_patterns"],
  "entry_ids": ["...", "..."]
}
```

---

## 8. 跨 Phase 解耦与接口约定

| 相关 Phase | 关系 | 解耦措施 |
|---|---|---|
| **Phase 5 Agent Trace** | 记忆读取 Trace | 只读 `trace.to_dict()`；新增 `memory_recorded` 事件；不修改 Trace 数据结构 |
| **Phase 6 ReflectiveAdvisor** | 记忆增强 Advisor | `ErrorPatternLedger` 仍是 session 级；Phase 8 **不 seed Ledger**；`failure_patterns` 只通过 system prompt / `memory_read` 给 LLM 提供背景提示；如需更强联动未来再扩展 |
| **Phase 7 Context Compression** | 记忆引用 cache URI | 记忆条目只存元数据/URI；`memory_read` 结果跳过 `ToolResultExternalizer`（同 `context_read`）；注入内容参与 token 预算 |
| **Phase 9 安全策略** | 安全策略将来包裹记忆 | `memory_read` 走 URI 校验；敏感内容过滤内嵌；未来策略引擎只需限制 category/读写权限 |
| **Phase 10 CLI** | CLI 读取记忆 | 结构化文件目录清晰，CLI 可直接遍历；提供 `MemoryStore.list_entries()` |

---

## 9. 冲突风险评估

### 9.1 与现有模块的冲突矩阵

| 模块 | 潜在冲突 | 风险等级 | 缓解措施 |
|---|---|---|---|
| `AgentConfig` | 新增 `MemoryConfig` 可能与未来字段命名冲突 | 低 | 使用嵌套 `agent.memory` 命名空间 |
| `Agent.__init__` | 参数列表继续增长 | 中 | 保持可选参数；未来可考虑 `MemoryManager` 由工厂函数创建 |
| `Agent.run` | 记忆注入增加 messages 长度，可能频繁触发压缩 | 中 | `inject_max_tokens` / `inject_max_entries` 硬限制；注入失败不报错 |
| `ToolRegistry` | `memory_read` 与 `tools.enabled` 冲突 | 低 | `memory_read` 为内部工具，不受 `tools.enabled` 控制（同 `context_read`） |
| `ReflectiveAdvisor` | `persist_error_patterns` 与 Advisor 自带开关可能语义重叠 | 中 | 明确分工：Advisor 开关控制 session 内行为；记忆开关控制跨 session 持久化 |
| `ContextCache` | 记忆可能误把 context cache 路径当普通文件保存 | 低 | 强制使用 `hermes://context/...` URI，不保存绝对路径 |
| `ToolResultExternalizer` | `memory_read` 结果可能被二次外迁 | 低 | 在 `externalize_if_needed()` 中跳过 `memory_read`（同 `context_read`） |
| `ErrorPatternLedger` | 无直接冲突（Phase 8 不操作 Ledger） | 低 | 明确 Phase 8 只通过 system prompt 提示，不修改 Ledger 状态和计数 |
| 测试 | 记忆写入真实文件可能影响测试隔离 | 中 | 测试使用 `tmp_path` 和 `InMemoryMemoryStore` |

### 9.2 运行时风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 文件并发写入冲突 | 多进程同时写同一 category | 按 entry 独立文件；append-only JSONL 降低冲突 |
| 记忆注入污染 system prompt | LLM 被无关记忆干扰 | category + tag 过滤；top_k 限制；摘要质量阈值 |
| 敏感信息泄露 | API key 等被持久化 | 默认开启 `filter_sensitive`；用户可扩展正则列表 |
| 存储膨胀 | 长期运行产生大量记忆 | `max_entries_per_category`；按时间/ LRU 清理 |
| LLM 提取失败 | task summary 缺失 | 规则提取兜底；LLM 失败不阻塞 |
| 记忆陈旧 | 旧环境状态误导新任务 | 时间戳；过期自动降权；用户可手动清理 |
| system prompt 过长 | 首轮即触发 Phase 7 压缩 | `inject_max_tokens` 硬限制；默认 800 字符 |
| 空/极短 user_input | 召回不相关记忆 | 空输入时跳过注入；设置最小查询长度 |

---

## 10. Task 拆分与验收标准

建议 Phase 8 拆分为 4 个 Task，每个 Task 一个 commit。其中 **8.1~8.3 为 MVP**，**8.4 为可选增强**：

| Task | 范围 | 是否 MVP |
|---|---|---|
| 8.1 | MemoryStore + 数据模型 + 配置 | ✅ |
| 8.2 | MemoryExtractor + MemoryManager | ✅ |
| 8.3 | 主循环集成 + `memory_read` 工具 + 文档 | ✅ |
| 8.4 | 记忆审计、用户反馈、自动冲突检测与纠正 | ⚠️ 可选 |

### 10.1 Task 8.1：MemoryStore + 数据模型 + 配置

- 实现 `MemoryEntry`、`MemoryQuery`、`MemoryStore`、`StructuredMemoryStore`。
- 实现 `MemoryConfig` 并接入 `AgentConfig`。
- 新增 `tests/test_memory_store.py`。

**验收标准**：
- save/query/delete/cleanup/list_entries 全部通过。
- YAML 配置可正确加载 `agent.memory`。
- `mypy src/` / `ruff check src/ tests/` 全绿。

### 10.2 Task 8.2：MemoryExtractor + MemoryManager

- 实现 `RuleMemoryExtractor`，覆盖 `environment` / `artifacts` / `failure_patterns`。
- 实现 `MemoryManager.inject` 和 `MemoryManager.record`。
- 实现 `MemoryInjector`。
- 新增 `tests/test_memory_extractor.py`、`tests/test_memory_manager.py`。

**验收标准**：
- 给定模拟 Trace/State，能正确提取记忆条目。
- 注入记忆后 messages 长度不超过配置限制。
- LLM 提取器为可选，未配置时不影响规则提取。

### 10.3 Task 8.3：主循环集成 + memory_read 工具 + 文档

- 在 `Agent.__init__` / `Agent.run()` 中接入 `MemoryManager`。
- 新增 `memory_read` 工具（可选内部工具）。
- 记录 `memory_recorded` Trace 事件。
- 更新 `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md`、`docs/learning-journal.md`。
- 新增集成测试 `tests/test_memory_integration.py`。

**验收标准**：
- `pytest tests/ -q` 全绿（不破坏现有 276 passed 基线）。
- `mypy src/` / `ruff check src/ tests/` 全绿。
- 启用记忆后，Agent 能记录环境/产物/失败模式；新 Agent 启动时能读取并注入相关记忆。
- 所有新增 public 类/函数有中文 docstring 和类型标注。

### 10.4 Task 8.4：记忆审计与纠正机制（可选增强）

> 本 Task 不在 MVP 范围内，但属于 Phase 8 的合理延伸。当前设计已预留必要字段和接口。

**可能包含的内容**：

- 用户反馈打分（thumbs up/down）
- 记忆与当前环境冲突检测
- 陈旧/低置信度记忆自动降权或标灰
- CLI 命令：`hermes memory list`、`hermes memory delete <id>`
- 可选：LLM 自我审计记忆有效性

**用户交互边界**：

| 交互方式 | 8.1~8.3 | 8.4 |
|---|---|---|
| Agent 回复体现记忆 | ✅ | ✅ |
| LLM 通过 `memory_read` 读记忆 | ✅ | ✅ |
| 用户手动编辑 `.hermes/memory/` JSONL | ✅ | ✅ |
| CLI 查看/删除记忆 | ❌ | ✅ |
| 聊天中“忘记/纠正”记忆 | ❌ | 可选 |
| 用户反馈打分 | ❌ | ✅ |

---

## 11. 严禁做

- 不引入向量数据库、embedding 模型或 FAISS/Chroma 等重型依赖（Phase 8.1）。
- 不修改现有 Tool（`sandbox_exec`、`file_read`、`file_list`、`finish`、`context_read`）的签名或行为。
- 不替换 `ReflectiveAdvisor` 或 `ErrorPatternLedger`；只能可选地增强它们。
- 不把 `ContextCache` 的原始大内容复制到记忆文件；只允许 URI 引用。
- 不默认开启长期记忆。
- 不让记忆提取/注入的失败阻塞主循环或改变 Agent 返回结果。

---

## 12. 长远扩展点

| 扩展 | 时机 | 方式 |
|---|---|---|
| 语义检索 | 记忆条目 > 500 条或检索噪声明显时 | 在 `MemoryStore` 下新增 `VectorMemoryStore` 实现，保持接口不变 |
| 多 Agent 共享记忆 | 需要多进程/多用户共享时 | 把 `MemoryStore` 后端替换为 SQLite/Postgres |
| 记忆反馈学习 | 用户纠正记忆注入质量时 | 给 `MemoryEntry` 增加 `feedback` 字段，调整排序权重 |
| 安全策略接入 | Phase 9 实现后 | 在 `MemoryStore.read/write` 和 `memory_read` 中接入策略检查 |

---

*版本：0.4（已划分 Task 8.1~8.4，明确 MVP 与用户交互边界）*
