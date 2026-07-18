# Phase 7 Spec：上下文压缩（Context Compression）

> 本 spec 覆盖 Phase 7 全部 Task（7.1 ~ 7.6）。
> 核心亮点：**工具结果外迁到 Markdown 缓存文件**，消息历史只保留引用与摘要；结合滑动窗口 + 小模型摘要管理非工具历史。

---

## 1. 目标

让 Agent 在长时间、多轮、工具输出庞大的对话中，仍能把发给 LLM 的上下文控制在预算以内，同时不丢失关键信息。

核心能力：

1. **Token 预算感知**：估算当前 `messages` 的 token 占用，并与模型上下文窗口对比。
2. **工具结果外迁缓存**：当 `sandbox_exec` / `file_read` 等结果过长时，把完整内容写入本地 `.md` 缓存，消息里只留 URI 引用、类型、成功状态和短摘要。
3. **按需读取缓存**：给 LLM 一个 `context_read(uri)` 工具，让它在需要时把缓存内容拉回对话。
4. **历史摘要与裁剪**：对过旧的消息回合做滑动窗口保留或小模型摘要，保留最近工作集。
5. **全程可观测**：所有压缩、外迁操作写入 `AgentTrace`。

---

## 2. 核心概念

| 术语 | 定义 |
|------|------|
| **Session** | 一个 `Agent` 实例的生命周期，可包含多次 `run()` 调用。 |
| **Run** | 一次 `Agent.run(user_input)` 调用，内部包含多轮 LLM ↔ 工具交互。 |
| **ContextCache** | 本地文件缓存，按 `<session_id>/<run_id>/<entry_id>.md` 存放工具结果。 |
| **Cache URI** | `hermes://context/<session_id>/<run_id>/<entry_id>.md`，用于在消息和工具中引用缓存。 |
| **Context Budget** | `context_window - reserve_tokens`，发送给 LLM 前的硬上限。 |
| **Protected Tail** | 最近若干条消息/回合，不允许被压缩或删除，防止 LLM“失忆”。 |

---

## 3. 设计原则与解耦策略

### 3.1 核心设计原则

1. **消息历史是工作集，Trace/Cache 是档案馆**：
   - 可以大胆压缩 `messages`，因为完整事件已在 `AgentTrace` 中。
   - 可以外迁工具结果，因为缓存文件保留了原始内容。

2. **工具调用对必须保持完整**：
   - 不能删除 assistant 的 `tool_calls` 消息。
   - 不能删除对应的 tool 结果消息，但可以把其 `content` 替换为引用+摘要。

3. **最近一轮不可动**：
   - 最后一条 user 消息、最后一条 assistant 消息、以及它产生的所有 tool 结果必须保留在上下文中。

4. **外迁优先于摘要，摘要优先于删除**：
   - 长工具结果 → 外迁到文件（成本低，信息不丢）。
   - 旧对话回合 → 小模型摘要（保留语义）。
   - 极旧且无引用价值的信息 → 删除（最后手段）。

5. **小模型做摘要**：
   - 摘要由独立的轻量 LLM 完成（如 `gpt-4o-mini`），主循环大模型专注推理。
   - 未配置摘要模型时，使用规则摘要兜底（前 N 行 + 关键错误行）。

6. **默认关闭，显式启用**：
   - `ContextCompressionConfig.enabled` 默认 `false`，避免静默改变现有 Agent 行为。
   - 只有用户显式配置或注入压缩组件时才启用，保证 Phase 7 不强制耦合到其它模块。

### 3.2 与其它 Phase 的解耦策略

| 相关 Phase | 耦合点 | 解耦措施 |
|-----------|--------|---------|
| **Phase 2 ErrorHandler / Phase 6 ReflectiveAdvisor** | 错误分类从 `result.content` 提取异常类名 | 错误分类在 `ToolResultExternalizer` 之前使用原始 `result.content`；失败 traceback 默认完整保留（D1），不丢失异常信息；外迁只处理成功/中性长内容。 |
| **Phase 5 Agent Trace** | Trace 记录完整执行过程 | `tool_execution` 事件始终记录原始 `result.content`；`llm_request` 记录实际发送的消息数；压缩只影响发送给 LLM 的 `messages`，不影响 Trace 档案馆。 |
| **Phase 3 沙箱 / Phase 4 工具** | 工具签名和沙箱文件读取 | 不修改任何现有 Tool 的函数签名；`context_read` 读取的是 host 缓存，与沙箱 `file_read` 用不同 URI 方案，语义分离。 |
| **Phase 8 长期记忆** | 记忆系统可能需要引用缓存 | `ContextCache` 只负责 session 内文件存储，URI 方案 `hermes://context/...` 为记忆系统预留 `hermes://memory/...` 扩展空间；记忆层不直接依赖 `ContextCache` 内部路径。 |
| **Phase 9 安全策略** | 读取 host 缓存的权限 | `context_read` 通过 URI 访问，`ContextCache.read()` 严格校验，禁止路径遍历；未来安全策略只需限制 URI scheme，无需改动压缩模块。 |
| **Phase 10 CLI** | CLI 需要查看缓存 | `ContextCache` 目录结构清晰（`.hermes/context_cache/<session_id>/<run_id>/`），CLI 可直接遍历，不依赖 Agent 内部状态。 |

---

## 4. 模块与接口

### 4.1 TokenEstimator

```python
class TokenEstimator(ABC):
    @abstractmethod
    def estimate(self, messages: list[Message]) -> int: ...

class CharTokenEstimator(TokenEstimator):
    """按字符数估算：tokens = total_chars // chars_per_token。"""
    def __init__(self, chars_per_token: int = 4) -> None: ...

class TiktokenEstimator(TokenEstimator):
    """可选实现：使用 tiktoken 精确估算。"""
    def __init__(self, model: str) -> None: ...
```

### 4.2 ContextCache

```python
@dataclass
class CacheEntry:
    entry_id: str
    run_id: str
    session_id: str
    tool_name: str
    created_at: datetime
    file_path: Path
    uri: str
    summary: str
    content_length: int

class ContextCache:
    """本地文件缓存，按 session/run 组织。"""

    def __init__(self, root_dir: Path, session_id: str) -> None: ...

    def store(
        self,
        run_id: str,
        tool_name: str,
        content: str,
        summary: str = "",
    ) -> CacheEntry: ...

    def read(self, uri: str) -> str | None: ...

    def cleanup(self, max_age: timedelta | None = None) -> int: ...
```

### 4.3 Summarizer

```python
class Summarizer(ABC):
    @abstractmethod
    async def summarize(self, content: str, max_length: int = 500) -> str: ...

class StaticSummarizer(Summarizer):
    """规则摘要：取前 N 行 + Traceback/错误行。"""

class LLMSummarizer(Summarizer):
    """使用小模型生成摘要。"""
    def __init__(self, llm_client: Any, model: str, max_tokens: int) -> None: ...
```

### 4.4 ToolResultExternalizer

```python
class ToolResultExternalizer:
    """决定一个工具结果是否需要外迁到缓存。"""

    def __init__(
        self,
        cache: ContextCache,
        threshold: int = 800,              # 字符数阈值
        file_read_preview: int = 500,      # file_read 预览长度
        exec_success_preview: int = 200,   # sandbox_exec 成功预览长度
        exec_error_preview: int = 1000,    # 失败 traceback 保留长度
    ) -> None: ...

    def externalize_if_needed(
        self,
        run_id: str,
        tool_name: str,
        content: str,
        success: bool,
    ) -> tuple[str, CacheEntry | None]:
        """
        对原始 content 做外迁判断。

        规则：
          - 长度 <= threshold：原样返回。
          - 失败且长度 <= exec_error_preview：原样返回（D1，保留完整 traceback）。
          - 失败且长度 > exec_error_preview：截断到 exec_error_preview，给出缓存链接。
          - file_read 成功：使用 file_read_preview。
          - 其它成功：使用 exec_success_preview。

        注意：此接口只接收原始 content，不接收分类后的错误元数据。
        错误分类在调用本组件之前完成，保证 Phase 6 不受外迁影响。

        返回：
          - 最终要写入 messages 的 content（原内容或引用+摘要）。
          - 如果外迁了，返回 CacheEntry；否则返回 None。
        """
```

注意：工具结果外迁**不调用 LLM 生成摘要**，只使用规则预览。LLM 摘要器仅用于 `HybridCompressor` 对旧对话历史的摘要。

### 4.5 ContextCompressor

```python
@dataclass
class CompressionResult:
    messages: list[Message]
    original_token_count: int
    compressed_token_count: int
    strategy: str
    summary: str
    removed_ranges: list[tuple[int, int]]
    cache_entries: list[CacheEntry]

class ContextCompressor(ABC):
    @abstractmethod
    async def compress(
        self,
        messages: list[Message],
        budget: int,
        token_estimator: TokenEstimator,
    ) -> CompressionResult: ...

class HybridCompressor(ContextCompressor):
    """
    策略：
      1. 保护头部（system + 首轮用户/助手）。
      2. 从尾部向前计算 token，保留完整最近 K 个回合（Protected Tail）。
      3. 中间区域先尝试小模型摘要成一条 summary 消息。
      4. 摘要后仍超预算，则继续丢弃更旧的消息。
      5. 边界按“回合组”对齐，不拆分 tool_call/tool 结果。
    """
```

### 4.6 context_read 工具

新增 `src/agent/tools/context_read.py`：

```python
async def context_read(uri: str, cache: ContextCache) -> str:
    """读取 hermes://context/... 缓存文件内容。"""
```

`Agent` 在启用压缩时，通过闭包把 `ContextCache` 实例注入该工具并注册到 `ToolRegistry`。

---

## 5. 配置 Schema

在 `AgentRuntimeConfig` 中新增：

```python
class ContextCompressionConfig(BaseModel):
    enabled: bool = False
    context_window: int = 8192
    reserve_tokens: int = 1024
    externalize_threshold: int = 800          # 工具结果超过多少字符就外迁
    file_read_preview_chars: int = 500        # file_read 保留预览长度
    exec_success_preview_chars: int = 200     # sandbox_exec 成功保留预览长度
    exec_error_preview_chars: int = 1000      # 失败 traceback 保留长度
    protect_first_n: int = 2                  # 保护前 N 条消息
    protect_last_n_turns: int = 2             # 保护最近 N 个完整回合
    summary_model: str = "gpt-4o-mini"        # 摘要小模型
    summary_max_tokens: int = 512
    cleanup_on_exit: bool = True              # Agent 销毁时是否清理缓存
    cache_root: str = ".hermes/context_cache" # 缓存根目录（相对或绝对路径）
    register_context_read: bool = True        # 是否自动注册 context_read 工具
```

对应 YAML：

```yaml
agent:
  context_window: 8192
  reserve_tokens: 1024
  compression:
    enabled: true   # 默认 false，此处显式启用
    externalize_threshold: 800
    file_read_preview_chars: 500
    exec_success_preview_chars: 200
    exec_error_preview_chars: 1000
    protect_first_n: 2
    protect_last_n_turns: 2
    summary_model: gpt-4o-mini
    summary_max_tokens: 512
    cleanup_on_exit: true
    cache_root: .hermes/context_cache
    register_context_read: true
```

---

## 6. 主循环集成点

`Agent.__init__` 新增：

```python
context_compressor: ContextCompressor | None = None,
summarizer: Summarizer | None = None,
context_cache: ContextCache | None = None,
```

如果 `config.agent.compression.enabled` 为 True 且用户未注入上述组件，`Agent` 使用默认实现：
- `ContextCache(root_dir=<project_root>/.hermes/context_cache, session_id=...)`
- `CharTokenEstimator`
- `HybridCompressor`
- `StaticSummarizer`（若未提供 `summarizer_llm_client`）或 `LLMSummarizer`（若提供）

如果 `enabled` 为 False 且未注入组件，则完全不启用压缩，行为与 Phase 6 之前一致。

`Agent.run()` 流程变更：

1. 生成 `run_id = uuid4().hex`。
2. `Agent.__init__` 阶段：
   - 如果用户未注入 `context_cache` 但 `config.agent.compression.enabled=True`，
     按 `cache_root` 创建默认 `ContextCache`。
   - 如果 `context_cache` 不为 None 且 `register_context_read=True`，
     调用 `register_context_tools(self.tools, self.context_cache)` 注册 `context_read`。
   - `tools.enabled` 中是否包含 `context_read` 不影响自动注册；`context_read` 是压缩子系统的内部配套工具。
3. 工具执行后、把结果追加到 `self.messages` 前：
   - **先用原始 `result.content` 做错误分类**（保证 Phase 6 不受外迁影响）。
   - 再调用 `ToolResultExternalizer.externalize_if_needed(run_id, tool_name, result.content, result.success)`。
   - 对失败结果按 D1 策略保留完整 traceback；对成功/中性长内容使用外迁后的引用文本。
   - 最后把分类元数据、反思提示等 wrap 到最终要写入 messages 的 content 上。
4. 每轮调用 `_build_openai_messages()` 前：
   - 用 `TokenEstimator` 估算当前 `messages` token。
   - 若超过 budget，调用 `HybridCompressor.compress(...)`。
   - 用返回的 `messages` 替换 `self.messages`（或生成用于本次发送的副本）。
   - 记录 `context_compression` Trace 事件。
5. `Agent` 销毁或显式 `close()` 时，根据 `cleanup_on_exit` 清理缓存。

---

## 7. Trace 事件

### 7.1 `tool_result_externalized`

在工具结果因过长被外迁时记录：

```json
{
  "tool": "sandbox_exec",
  "entry_id": "...",
  "uri": "hermes://context/<session_id>/<run_id>/<entry_id>.md",
  "original_length": 12500,
  "summary": "执行成功，输出前 200 字..."
}
```

### 7.2 `context_compression`

在调用压缩器时记录：

```json
{
  "run_id": "...",
  "strategy": "hybrid",
  "original_message_count": 32,
  "compressed_message_count": 12,
  "original_token_count": 9200,
  "compressed_token_count": 6100,
  "removed_ranges": [[3, 18]],
  "summary": "[上下文摘要] 前面已完成项目初始化...",
  "cache_entries": ["..."]
}
```

---

## 8. 缓存生命周期

- **目录结构**：`<project_root>/.hermes/context_cache/<session_id>/<run_id>/<entry_id>.md`
- **Session 内持久**：同一个 `Agent` 实例的多次 `run()` 共享 `session_id`，缓存可跨 run 访问。
- **不跨进程保留**：Phase 7 不涉及长期记忆；进程结束后缓存默认不保留（除非用户手动挂载到持久目录）。
- **清理策略**：
  - `cleanup_on_exit=True`：`Agent.__del__` / `close()` 删除整个 session 目录。
  - 测试环境使用 `tmp_path` 作为 `root_dir`。

---

## 9. Task 拆分与验收标准

### 7.1 Token 预算与估计

- 实现 `TokenEstimator` 抽象 + `CharTokenEstimator`。
- 在 `AgentRuntimeConfig` 中新增 `context_window` / `reserve_tokens`。
- 验收：
  - `tests/test_context_compression.py` 中估算器误差在合理范围。
  - 不破坏现有测试。

### 7.2 ContextCache 与 ToolResultExternalizer

- 实现 `ContextCache`、`CacheEntry`。
- 实现 `ToolResultExternalizer`，支持规则摘要兜底。
- 验收：
  - 长工具结果写入 `.md` 文件并返回正确 URI。
  - 短结果不外迁。
  - URI 可被 `ContextCache.read()` 读回。

### 7.3 小模型摘要器

- 实现 `Summarizer` 抽象 + `StaticSummarizer` + `LLMSummarizer`。
- `LLMSummarizer` 使用单独注入的小模型 client。
- 验收：
  - 未配置小模型时 `StaticSummarizer` 工作。
  - 配置小模型时调用正确模型并生成摘要。

### 7.4 context_read 工具

- 新增 `src/agent/tools/context_read.py`。
- `Agent` 在启用压缩时自动注册该工具。
- 验收：
  - LLM 可通过 `context_read(uri)` 读取缓存内容。
  - 无效 URI 返回友好错误。

### 7.5 HybridCompressor 与主循环接入

- ✅ 实现 `HybridCompressor`（`src/agent/core/compressor.py`）。
- ✅ 在 `Agent.run()` 中集成：工具结果外迁 + 预算检查 + 压缩。
- ✅ 记录 Trace 事件 `tool_result_externalized` 与 `context_compression`。
- ✅ 补充 `HybridCompressor` 单元测试与 Agent 集成测试。
- 验收：
  - 长对话不超出 budget。
  - 工具调用对不被破坏。
  - Trace 中包含 `tool_result_externalized` 和 `context_compression` 事件。

### 7.6 配置、测试、文档

- ✅ 把 `ContextCompressionConfig` 接入 `AgentConfig`。
- ✅ 补充单元测试 + 集成测试（`tests/test_context_compression.py` 覆盖 7.1~7.5）。
- ✅ 更新 `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md`、`docs/learning-journal.md`。
- ✅ 验收：
  - `pytest tests/ -q` 全绿（276 passed，1 skipped）。
  - `mypy src/`、`ruff check src/ tests/` 全绿。
  - 所有新增 public 类/函数有中文 docstring 和类型标注。

---

## 10. 严禁做

- 不修改现有 Tool 的签名或行为（`sandbox_exec` / `file_read` / `file_list` / `finish` 保持原样）。
- 不把 `ContextCache` 直接暴露给 LLM 作为文件系统工具（必须通过 `context_read` 受控访问）。
- 不跨进程持久化缓存到用户主目录（Phase 7 只保留 session 级缓存，跨进程交给 Phase 8）。
- 不删除 assistant 的 `tool_calls` 消息或对应的 tool 消息（只能替换 content）。
- 不因为压缩而丢失 `AgentTrace` 中的完整事件记录。

---

## 11. 涉及文件

- 新增：`src/agent/core/context_compression/`（或平铺在 `src/agent/core/` 下）：
  - `token_estimator.py`
  - `context_cache.py`
  - `summarizer.py`
  - `externalizer.py`
  - `compressor.py`
- 新增：`src/agent/tools/context_read.py`
- 新增：`tests/test_context_compression.py`、`tests/test_context_compression_integration.py`
- 修改：`src/agent/config.py`（新增配置字段）
- 修改：`src/agent/core/engine.py`（集成点）
- 修改：`src/agent/tools/__init__.py`（注册 context_read）
- 修改：相关文档

---

## 12. 长远影响与风险

### 12.1 架构可扩展性

- **闭包注入模式的技术债**：`context_read` 通过闭包在 `Agent.__init__` 阶段注入 `ContextCache`。如果未来出现第二个、第三个需要运行时状态的内部工具，`Agent.__init__` 会逐渐变成“依赖装配中心”。届时应考虑引入更通用的运行时上下文注入机制（例如扩展 `ExecutionContext` 或轻量 DI 容器）。
- **`context_read` 的专用性**：它只读缓存。未来 Phase 8 的长期记忆、知识库等可能需要类似的 `memory_read`、`kb_read`。当前 URI 方案 `hermes://context/...` 预留了扩展空间，但工具本身需要复用或抽象。

### 12.2 模型行为正确性

- **LLM 不会主动读缓存**：如果 LLM 没有看到预览里的关键信息，可能不会去调 `context_read`，而是凭猜测继续。缓解手段：
  - 外迁消息里明确写“如需完整内容请调用 context_read(...)”。
  - 对 `file_read` 保留足够长的预览（500 字符）。
  - 失败 traceback 默认完整保留（D1），避免调试信息被隐藏。
- **摘要丢失细节**：小模型摘要对复杂任务可能遗漏关键事实。长期可以通过“分层摘要 + 索引”改进，但 Phase 7 先保持简单。

### 12.3 性能与成本

- **磁盘 I/O**：每个长工具结果都要写文件。高频工具调用场景下可能成为瓶颈。缓解：写入操作是本地文件、量不大；未来可改为异步批量写入。
- **摘要 LLM 成本**：`LLMSummarizer` 每次压缩旧历史都会调用一次小模型。长会话中可能频繁触发。缓解：
  - 只在真正接近 budget 时才压缩。
  - 压缩一次后，后续多轮可能不再触发（因为消息已变小）。
  - 未配置小模型时自动降级为 `StaticSummarizer`。
- **Token 估算误差**：`CharTokenEstimator` 是近似值，可能低估或高估。对精确预算敏感的场景，未来应接入 `tiktoken` 或 provider 提供的 tokenizer。

### 12.4 安全与隐私

- **缓存文件可能包含敏感信息**：工具输出里可能有 API key、环境变量、用户数据等。缓解：
  - 缓存根目录放在项目内 `.hermes/context_cache/`，并加入 `.gitignore`。
  - `context_read` 必须校验 URI，禁止路径遍历。
  - 未来可考虑对明显敏感内容（如 `SECRET=`、`password`）做过滤或跳过缓存。
- **进程崩溃导致缓存泄漏**：`cleanup_on_exit` 依赖 `Agent.__del__` / `close()`。如果进程异常退出，缓存可能留在磁盘。长期应加 TTL 或启动时清理过期 session。

### 12.5 与后续 Phase 的衔接

- **Phase 8 长期记忆**：session 缓存里的摘要、关键工具结果可以作为记忆条目。`ContextCache` 的 URI 方案便于记忆系统引用。
- **Phase 9 安全策略引擎**：`context_read` 读取的是 host 缓存，不是沙箱文件。未来安全策略需要区分“沙箱内文件”和“Agent 内部缓存”的权限。
- **Phase 10 CLI 与可观测性**：缓存目录本身可以作为调试入口，CLI 可以展示当前 session 有哪些缓存文件、大小、摘要。

### 12.6 测试与维护

- 新增模块较多（cache、externalizer、compressor、summarizer、token_estimator、context_read 工具），测试覆盖需要跟上。
- `LLMSummarizer` 的测试必须使用 mock client，不能依赖真实 LLM，否则测试不稳定且费钱。

---

## 13. 设计决策记录


- **proactive 外迁**：工具结果一超过阈值就外迁，避免消息历史先膨胀再压缩。
- **URI 方案 `hermes://context/...`**：与文件系统解耦，未来可迁移到对象存储或数据库。
- **小模型摘要**：把“总结旧历史”这种可并行、低创意的任务交给便宜模型，保护主模型上下文和费用。
- **Session 级缓存**：同一个 `Agent` 实例的多次 `run()` 可互相引用缓存，但不要求跨进程保留。
- **Trace 双事件**：`tool_result_externalized` 记录单次外迁；`context_compression` 记录整轮压缩，便于复盘。
- **默认关闭（enabled=false）**：避免 Phase 7 静默改变现有 Agent 行为，不强制耦合到其它 Phase 的测试和调用方。
- **外迁器只处理原始 content**：错误分类在调用外迁器之前完成，保证 Phase 6 的 `_classify_tool_error` 不受外迁后消息格式影响。
- **外迁器跳过 `context_read` 结果**：避免 LLM 主动读回的缓存内容被再次外迁，防止循环。
- **LLMSummarizer 失败降级**：小模型摘要失败时自动降级为 `StaticSummarizer`，避免主循环被摘要步骤中断。
- **缓存 id 白名单校验**：`session_id` / `run_id` 只允许 `a-zA-Z0-9_-`，防止路径遍历。
- **`context_read` 随压缩自动注册**：`tools.enabled` 不控制内部配套工具；可通过 `register_context_read=False` 关闭。
- **默认缓存目录 `.hermes/context_cache`**：可配置 `cache_root`；项目 `.gitignore` 应忽略 `.hermes/`。
