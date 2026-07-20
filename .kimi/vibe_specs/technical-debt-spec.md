# Technical Debt Spec 清单

> **SDD-RIPER-ONE 产物**：本文件是 Hermes Agent 当前技术债的“唯一真相源”。  
> **原则**：`No Spec, No Code`。本清单中的任何一项进入 `Execute` 阶段前，必须先被选中并产出/细化对应 Spec，再经过 `Plan Approved` 门禁。  
> **维护规则**：每完成一项技术债修复，必须同步更新本文件状态、相关测试数与文档（`docs/progress-spec.md`、`docs/session-context.md`、`docs/evaluation-log.md`、`CODEMAP.md`）。  
> **最后更新**：2026-07-21

---

## 1. 当前技术债总表

| 编号 | 名称 | EVAL ID | 严重程度 | 状态 | 阻塞 Coding Agent？ | 预估工时 |
|---|---|---|---|---|---|---|
| TD-001 | Docker 后端文件跨轮持久性 | EVAL-004 | 🔴 高 | ✅ 已完成 | ✅ 是 | 1-2 天 |
| TD-002 | `subprocess` 沙箱后端未真正实现 | EVAL-003 | 🟠 中 | ✅ 已完成（2026-07-17） | ✅ 是（Docker 不可用时） | 1-2 天 |
| TD-003 | `config.sandbox.backend` 被忽略 | EVAL-005 | 🟡 低 | ✅ 已完成（2026-07-17） | ⚠️ 间接 | 0.5 天 |
| TD-004 | `ExecutionContext` 已实现但未接入工具 | EVAL-006 | 🟠 中 | ✅ 已完成（2026-07-17） | ⚠️ 间接 | 1-2 天 |
| TD-005 | 内部工具闭包注入导致 `Agent.__init__` 膨胀 | EVAL-007 | 🟠 中 | ✅ 已完成（2026-07-18） | ❌ 否 | 2-3 天 |
| TD-006 | 文件写操作缺少 workspace 边界限制 | EVAL-008 | 🟠 中 | ✅ 已完成（2026-07-17） | ⚠️ 安全层面 | 0.5-1 天 |
| TD-007 | Docker Hub 拉取受限 / 镜像源未配置 | EVAL-002 | 🟠 中 | ✅ 已完成（2026-07-18） | ✅ 是（当前环境） | 0.5 天 |
| TD-008 | Web UI / CLI 未接入写操作人工确认 | — | 🟡 低-中 | ✅ 已完成（2026-07-18，CLI；Web UI 留待后续单元） | ❌ 否 | 1-2 天 |
| TD-009 | Phase 8.4 长期记忆增强未实现 | — | 🟡 低 | ✅ 已关闭（2026-07-18 核实：Phase 8.4 已交付，验收全过） | ❌ 否 | 2-3 天 |
| TD-010 | 沙箱网络策略增强（两阶段网络 + `network_mode` 配置化） | — | 🟡 低-中 | ⏳ 候选（2026-07-18 联调讨论登记） | ⚠️ 间接（S3 类场景） | 0.5-1 天 |
| TD-011 | 默认门禁套件环境不确定性（`OPENAI_*` 污染 + web 测试隐性真实调用） | — | 🟠 中 | ✅ 已完成（2026-07-19，`tests/conftest.py` 全局清理） | ❌ 否 | 0.5 天 |
| TD-012 | `requirements.txt` 与 `pyproject.toml` 依赖漂移（缺 fastapi/uvicorn/jinja2） | — | 🟡 低 | ✅ 已完成（2026-07-19） | ❌ 否 | 0.1 天 |
| TD-013 | 纯对话事实不入记忆（`llm_extraction_enabled` 有开关无实现） | — | 🟡 低-中 | ⏳ 候选（2026-07-21 Batch 5 实证登记） | ❌ 否 | 1-2 天 |

---

## 2. 修复路线建议

### Phase A：让 Coding Agent 真正可用（P0）

> 目标：在没有 Docker 或 Docker 不可用的情况下，也能完成“写代码 → 改代码 → 运行验证”的最小闭环。

1. **TD-002 + TD-003**：实现 `subprocess` 后端并让 `config.sandbox.backend` 生效。
2. **TD-001**：修复 Docker 后端文件跨轮持久性（与 TD-002 共享 workspace 抽象）。
3. **TD-007**：配置镜像源 / 本地镜像 fallback，确保 Docker 路径可落地。

### Phase B：架构可扩展性（P1）

> 目标：让新工具、新内部能力不再硬编码进 `Agent.__init__`。

4. **TD-004**：将 `ExecutionContext` 接入工具签名，支持跨 tool call 状态共享。
5. **TD-005**：重构 `context_read` / `memory_read` 的注入方式，引入通用运行时上下文注入。

### Phase C：安全与体验（P2）

> 目标：提升默认安全边界和人机协作体验。

6. **TD-006**：为 `file/path` write 增加 workspace 边界。
7. **TD-008**：为写/编辑类工具增加可选的人工确认流程。

### Phase D：可选增强（P3）

8. **TD-009**：实现 Phase 8.4 长期记忆增强（CLI 审计、用户反馈、冲突检测等）。

---

## 3. 各技术债详细 Spec

---

### TD-001：Docker 后端文件跨轮持久性不确定

#### 背景

`DockerSandboxBackend` 当前为每个 `execute_code()` / `put_file()` 调用从预热池中获取一个容器，调用结束后立即销毁并补充新容器。这导致：

- `file_write` 写入的文件，后续 `file_read` / `sandbox_exec` 可能看不到。
- `file_edit` 读到的内容可能是旧容器遗留，或根本读不到。
- 同一 Agent 会话内无法形成“写 → 读 → 运行”的连续工作区。

#### 目标

确保同一个 `DockerSandboxBackend` 实例在生命周期内提供**单一、持久、可写**的工作区，让文件类工具和代码执行工具看到一致的文件系统。

#### 范围

**Must Have**

1. 同一 `DockerSandboxBackend` 实例内，`put_file` 写入的文件必须能被后续 `get_file`、`execute_code`、`file_list` 访问到。
2. 保持现有 public API 不变（`execute_code`、`put_file`、`get_file`、`create_container`、`remove_container`、`close`）。
3. 保持现有安全限制（network=none、non-root、read_only root、tmpfs）。
4. 更新/补充 `tests/test_sandbox.py`，覆盖跨调用文件持久性。

**Non-Goals**

- 不改写沙箱层以外的模块。
- 不引入新的后端抽象接口（保留后续对接 subprocess 的空间即可）。
- 不追求多进程共享 workspace（session 内单 backend 实例足够）。

#### 候选方案

| 方案 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|
| A. 每个 backend 实例维护一个持久容器，所有操作复用该容器 | 实现简单，文件天然持久 | 容器崩溃后需重建；与现有预热池逻辑冲突较大 | ⭐⭐⭐ |
| B. 挂载共享 Docker volume 到 `/workspace`，池化容器只执行代码，文件落 volume | 保留池化优势，文件跨容器持久 | 需要管理 volume 生命周期；容器创建参数变化较大 | ⭐⭐⭐⭐ |
| C. 在宿主机维护 workspace 目录，通过 bind mount 到每个容器 | 调试方便，可直接查看文件 | Windows 路径兼容、权限隔离更复杂 | ⭐⭐⭐ |

**建议采用方案 B**：对现有池化结构改动最小，同时解决持久性问题。

#### 涉及文件

- `src/agent/sandbox/docker_backend.py`
- `src/agent/core/tool_router.py`
- `tests/test_sandbox.py`
- `docs/session-context.md`
- `docs/progress-spec.md`
- `docs/evaluation-log.md`

#### 验收标准

- `pytest tests/test_sandbox.py -v` 全部通过。
- 新增至少 2 个跨调用持久性测试：
  - `put_file` → `get_file` 能读回。
  - `put_file` → `execute_code` 能在同一 `/workspace` 下看到文件。
- `pytest tests/ -q` 不新增失败。
- `mypy src/` / `ruff check src/ tests/` 全绿。

#### 风险

- 改动 backend 容器生命周期可能影响大量现有测试，需要仔细调整 mock 预期。
- volume 挂载在 Windows Docker Desktop 上可能需要额外路径处理。

#### 修复记录

- **日期**：2026-07-04
- **采用方案**：方案 B（命名 Docker volume + 池化容器共享）
- **实现要点**：
  - `DockerSandboxBackend.__init__` 新增 `workspace_volume` / `cleanup_workspace`。
  - `_do_create_container()` 自动挂载 `volumes={workspace_volume: {"bind": "/workspace", "mode": "rw"}}`。
  - `get_file()` 改为从池化容器读取，不再依赖 `self._container`。
  - `close()` 在关闭 client 时清理 volume（可通过 `cleanup_workspace=False` 保留）。
- **测试覆盖**：`tests/test_sandbox.py` 新增 `TestDockerSandboxBackendWorkspace`，覆盖 volume 唯一性、挂载、跨方法共享、close 清理；全量测试 541 passed，1 skipped。
- **使用约定**：需要持久化的文件必须写入 `/workspace`；`/tmp` 保持原临时语义。

---

### TD-002：`subprocess` 沙箱后端未真正实现

#### 背景

`SandboxConfig.backend` 支持 `"docker"` 和 `"subprocess"`，但 `src/agent/sandbox/` 下只有 `docker_backend.py`。当 Docker 不可用时（如当前环境无法连接 Docker Hub），Agent 无法执行任何代码。

#### 目标

实现一个轻量级 `SubprocessSandboxBackend`，作为 Docker 不可用时的 fallback，让 Agent 在无 Docker 环境下仍能完成基础代码执行与文件操作。

#### 范围

**Must Have**

1. 新增 `src/agent/sandbox/subprocess_backend.py`。
2. 实现与 `DockerSandboxBackend` 同名的 public 方法：
   - `execute_code(code: str, timeout: int | None = None) -> ExecutionResult`
   - `put_file(path: str, content: bytes) -> bool`
   - `get_file(path: str) -> bytes | None`
   - `ping() -> bool`
   - `close() -> None`
   - 可选：`create_container`、`remove_container` 可降级为 no-op 或等价清理。
3. 子进程执行时使用临时目录作为 workspace，隔离不同 backend 实例。
4. 基本安全限制：timeout、禁止网络（可通过环境变量/防火墙尽量限制）。

**Non-Goals**

- 不追求与 Docker 同等级别的安全隔离（明确为轻量 fallback）。
- 不实现 cgroup、seccomp、user namespace。
- 不实现容器预热池。

#### 涉及文件

- 新增：`src/agent/sandbox/subprocess_backend.py`
- 修改：`src/agent/sandbox/__init__.py`（导出）
- 新增：`tests/test_subprocess_backend.py`
- 修改：`docs/usage.md`、`docs/configuration.md`（说明 fallback 行为）

#### 验收标准

- `pytest tests/test_subprocess_backend.py -v` 全部通过。
- 在 `subprocess` 后端上能跑通 `tests/test_tools.py` 中的 `sandbox_exec` / `file_read` / `file_list` / `file_write` / `file_edit` 测试（可通过参数化 backend 实现）。
- `mypy src/` / `ruff check src/ tests/` 全绿。

---

### TD-003：`config.sandbox.backend` 被忽略

#### 背景

`Agent.__init__` 中 `self._sandbox_backend = sandbox_backend or DockerSandboxBackend()` 永远创建 Docker 后端，完全不读取 `config.sandbox.backend`。

#### 目标

让配置中的 `sandbox.backend` 真正决定默认后端类型。

#### 范围

**Must Have**

1. 在 `src/agent/core/engine.py` 或 `src/agent/sandbox/__init__.py` 中增加后端工厂函数，根据 `SandboxConfig.backend` 返回对应实例。
2. `Agent.__init__` 在未注入 `sandbox_backend` 时，使用工厂函数构造后端。
3. 未知 backend 值时记录警告并回退到 `subprocess`（或 Docker，取决于可用性）。

**Non-Goals**

- 不修改 `SandboxConfig` schema。
- 不改动已注入 `sandbox_backend` 的行为。

#### 涉及文件

- `src/agent/core/engine.py`
- `src/agent/sandbox/__init__.py`
- `tests/test_config.py` 或 `tests/test_core.py`

#### 验收标准

- 配置 `sandbox.backend: subprocess` 时，`Agent` 默认使用 `SubprocessSandboxBackend`。
- 配置 `sandbox.backend: docker` 时，默认使用 `DockerSandboxBackend`。
- 非法值时回退并记录警告，不抛异常。

---

### TD-004：`ExecutionContext` 已实现但未接入工具

#### 背景

`ExecutionContext`（位于 `src/agent/core/state.py`）用于在单次 Agent 执行中跨 tool call 共享状态，例如“已安装包列表”、“当前工作目录”。但当前 `ToolRegistry` 只向 handler 传递 tool_call 参数，工具无法读写该上下文。

#### 目标

让工具 handler 能够读取/写入 `ExecutionContext`，使 Agent 能维护跨 tool call 的运行时状态。

#### 范围

**Must Have**

1. 定义工具 handler 可选接收 `execution_context` 参数（向后兼容，不强制）。
2. 修改 `ToolRegistry.execute()`：在调用 handler 前，检查其签名是否包含 `execution_context`，若有则注入当前 `Agent` 的 `ExecutionContext`。
3. 在 `Agent.run()` 中维护一个 `ExecutionContext` 实例，并在每轮 tool call 中传递。
4. 提供至少一个使用示例：在 `sandbox_exec` 或工具结果处理中记录已安装包。

**Non-Goals**

- 不一次性把所有工具改为使用 `ExecutionContext`。
- 不将 `ExecutionContext` 暴露给 LLM（仍通过 message history 交互）。

#### 涉及文件

- `src/agent/core/engine.py`（`ToolRegistry`、`Agent`）
- `src/agent/core/state.py`（可能需要扩展接口）
- `tests/test_state.py` 或新增 `tests/test_execution_context.py`

#### 验收标准

- 新增工具 handler 可以通过签名接收 `execution_context`。
- 不破坏现有工具（签名不含该参数的工具行为不变）。
- 至少一个集成测试证明状态可跨 tool call 保留。

---

### TD-005：内部工具闭包注入导致 `Agent.__init__` 膨胀

#### 背景

`context_read` 和 `memory_read` 是内部配套工具，它们在 `Agent.__init__` 中通过闭包注入 `ContextCache` 和 `MemoryManager`。未来每增加一个需要运行时状态的内部工具，都要修改 `Agent.__init__`。

#### 目标

将内部工具的注册从 `Agent.__init__` 中解耦，让新增内部工具不需要改动核心引擎。

#### 范围

**Must Have**

1. 设计一个轻量的“运行时上下文”对象（或扩展 `ExecutionContext`），封装 `ContextCache`、`MemoryManager` 等内部依赖。
2. 修改 `register_context_tools` / `register_memory_tools`，使其接收该上下文对象而非具体实例。
3. `Agent.__init__` 只需在适当时机调用注册函数，传入统一的上下文对象。

**Non-Goals**

- 不引入重型 DI 框架。
- 不修改外部工具（`sandbox_exec`、`file_read` 等）的注册方式。

#### 涉及文件

- `src/agent/tools/__init__.py`
- `src/agent/core/engine.py`
- `src/agent/core/state.py`（可能）
- 相关测试

#### 验收标准

- `Agent.__init__` 中内部工具注册逻辑明显简化。
- 新增一个假设的内部工具时，无需修改 `Agent.__init__`。
- 所有现有测试通过。

---

### TD-006：文件写操作缺少 workspace 边界限制

#### 背景

默认安全规则只拒绝 `/etc/passwd`、`.ssh` 等敏感路径的 write，但未限定允许范围。如果后端未来支持 bind mount 宿主目录，LLM 可能通过 `file_write` 写入任意位置。

#### 目标

为 `file/path` write 操作增加默认 workspace 边界：只允许写入 `/workspace` 下路径（或配置指定的 workspace）。

#### 范围

**Must Have**

1. 在 `default_security_rules.yaml` 中增加 `file/path` write 的 allow 规则，限定允许路径前缀（如 `/workspace`）。
2. 拒绝写入 workspace 以外的路径（敏感路径继续拒绝）。
3. 配置中支持自定义 `security.workspace_path`。

**Non-Goals**

- 不修改 read 规则（read 已有自己的规则集）。
- 不引入复杂的文件系统 ACL。

#### 涉及文件

- `src/agent/core/default_security_rules.yaml`
- `src/agent/core/security.py`（如果需要支持 allow 规则优先级）
- `tests/test_tool_security.py`

#### 验收标准

- `file_write("/workspace/main.py")` 被允许。
- `file_write("/etc/passwd")` 被拒绝。
- `file_write("/tmp/foo.py")` 在默认配置下被拒绝。

---

### TD-007：Docker Hub 拉取受限 / 镜像源未配置

#### 背景

当前环境无法直接连接 Docker Hub 拉取 `python:3.11-slim`，导致 Docker 后端无法创建容器。

#### 目标

提供镜像源配置或本地镜像 fallback，使 Docker 后端在受限网络下可用。

#### 范围

**Must Have**

1. 在 `SandboxConfig` 中增加 `image_registry` 或 `image_pull_policy` 配置。
2. `DockerSandboxBackend.ensure_image()` 支持从配置的镜像源拉取。
3. 如果本地已存在镜像，跳过拉取（当前已实现，但需确保行为稳定）。

**Non-Goals**

- 不实现私有仓库认证（后续可扩展）。
- 不解决 Docker daemon 本身不可达的问题。

#### 涉及文件

- `src/agent/config.py`
- `src/agent/sandbox/docker_backend.py`
- `docs/configuration.md`

#### 验收标准

- 配置镜像源后，`ensure_image()` 从指定源拉取。
- 本地存在镜像时，不触发拉取。
- 新增测试覆盖镜像源配置解析。

---

### TD-008：Web UI / CLI 未接入写操作人工确认

#### 背景

`file_write` 和 `file_edit` 会静默修改沙箱文件。在 Coding Agent 场景中，用户可能希望在应用修改前进行 review/approve。

#### 目标

为写/编辑类工具提供可选的人工确认钩子，CLI 和 Web UI 可以选择性启用。

#### 范围

**Must Have**

1. 在 `AgentConfig` 中增加 `human_approval.enabled` 与 `human_approval.tools` 配置。
2. 在 `ToolRegistry.execute()` 中，对于配置的 tool，执行前调用 approval callback。
3. CLI 模式提供 `--approve` 或交互式确认；Web UI 提供前端确认面板。

**Non-Goals**

- 不默认开启人工确认（保持自动化体验）。
- 不实现异步等待外部审批的复杂工作流。

#### 涉及文件

- `src/agent/config.py`
- `src/agent/core/engine.py`
- `src/agent/cli/chat.py`
- `src/agent/web/app.py`、`src/agent/web/templates/index.html`
- 相关测试

#### 验收标准

- 启用人工确认后，`file_write` 执行前会询问用户，用户拒绝则返回 `success=False`。
- CLI 和 Web UI 至少一个接入该能力。
- 未启用时行为完全不变。

---

### TD-009：Phase 8.4 长期记忆增强未实现

#### 背景

Phase 8.1~8.3 已实现长期记忆存储、注入、记录。Phase 8.4 规划了 CLI 审计、用户反馈、冲突检测、Markdown memory-bank 导出等增强，但尚未落地。

#### 目标

实现 Phase 8.4 中的核心增强，让长期记忆可被用户查看、反馈、纠正。

#### 范围

**Must Have**

1. CLI 命令：`hermes memory list`、`hermes memory show <id>`、`hermes memory delete <id>`、`hermes memory feedback <id> <score>`。
2. 用户反馈影响注入排序（confidence × feedback_multiplier × stale_multiplier）。
3. Markdown memory-bank 导出。

**Non-Goals**

- 不实现自动冲突纠正（只检测并提示）。
- 不引入向量数据库。

#### 涉及文件

- `src/agent/cli/` 下新增/修改
- `src/agent/core/memory.py`
- `scripts/hermes-memory.py`（可能）
- 相关测试与文档

#### 验收标准

- CLI 命令可列出/查看/删除/反馈记忆条目。
- 反馈后注入排序发生变化。
- Markdown 导出文件人类可读。

---

### TD-011：默认门禁套件环境不确定性

#### 背景

宿主机设置用户级 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` 后，EVAL-012 环境变量覆盖机制（故意特性）使默认配置变为 DeepSeek，导致 `test_cli_config_default_plain/rich` 断言 `gpt-4o` 失败；`test_web_ui.py` chat 测试在有真实 key 时**意外发起真实 API 调用**（烧配额），并在 Windows ProactorEventLoop 下 httpx TLS 关闭崩溃（"Event loop is closed"）。门禁套件结果取决于机器环境，丧失确定性。

#### 界定

债 = 默认套件不确定性 + 隐性真实调用；真实 LLM 测试能力本身**不是债**，由显式通道 `examples/e2e_suite.py` 承载（独立脚本，不经 pytest conftest）。

#### 修复记录

- **日期**：2026-07-19
- **方案**：新增 `tests/conftest.py`，function 级 autouse fixture 用 monkeypatch 清理三个 `OPENAI_*` 变量；既有显式 `setenv`/`delenv` 用例顺序兼容（先清后设）。
- **验证证据**：污染环境 678 passed, 1 skipped；干净环境 678 passed, 1 skipped；`ruff check src/ tests/` 全绿。
- **Feature Spec**：`mydocs/specs/2026-07-19_16-59_test-env-isolation.md`

---

### TD-012：`requirements.txt` 与 `pyproject.toml` 依赖漂移

#### 背景

`pyproject.toml` 的 web UI 运行依赖（`fastapi>=0.110.0`、`uvicorn[standard]>=0.27.0`、`jinja2>=3.1.0`）未同步到 `requirements.txt`，按后者安装将得到残缺环境。

#### 修复记录

- **日期**：2026-07-19
- **方案**：`requirements.txt` Core 段补齐三个依赖，版本约束与 `pyproject.toml` 对齐。
- **Feature Spec**：`mydocs/specs/2026-07-19_16-59_test-env-isolation.md`

---

### TD-013：纯对话事实不入记忆（`llm_extraction_enabled` 有开关无实现）

#### 背景

Batch 5（记忆专项批量评测）试点实证：默认 `RuleMemoryExtractor` 只覆盖三类记忆——产物（file_write 内容快照）、环境（pip 安装包）、失败模式（错误+反思事件）；**用户在对话中直接陈述的事实（"请记住：代号是 X"）不会被提取**。`MemoryConfig.llm_extraction_enabled` 配置项存在（`src/agent/config.py:102`）但 src 中无对应实现。

实测记录：mem 臂 Agent 对话教学后 `memory_search` × 4 均检索为空（2026-07-20 试点）；事实改以 file_write 产物承载后召回 100%。

#### 目标

实现 LLM 驱动的对话事实提取器，使用户直接陈述的关键信息（偏好、代号、参数、约定）进入长期记忆，无需借助文件载体。

#### 范围（候选草案）

**Must Have**

1. 实现 `LLMMemoryExtractor`（实现 `MemoryExtractor` 接口）：run 结束后用 LLM 从对话 trace 提取关键事实（去重、带置信度）。
2. 接通 `llm_extraction_enabled` 配置开关：默认关闭（不破坏现有行为与成本）。
3. 提取结果走既有 MemoryManager 写入与注入管线。
4. 新增测试：对话事实 → 记忆条目 → 跨会话注入召回。

**Non-Goals**

- 不改变 RuleMemoryExtractor 现有行为（两提取器可叠加）。
- 不做向量数据库/embedding 检索。

#### 验收标准

- 对话教学"代号是 X"后，新会话能通过记忆注入或 memory_search 召回 X。
- `pytest tests/ -q` 不新增失败；mypy/ruff 全绿。
- Batch 5 对话版任务（无文件载体）在开关开启后通过。

#### 来源

- 登记依据：`mydocs/specs/2026-07-20_22-20_batch-e2e-batch5-memory.md` §5 Step 4a；`docs/batch-e2e-batch5-report.md` 核心发现§4。

---

## 4. 下一步选择

请从上方选择**下一个要进入 SDD-RIPER-ONE 流程**的技术债，回复格式例如：

> “先处理 TD-001，请按 sdd-riper-one 给出完整 Spec 并等待 Plan Approved。”

选中后，我会为该项产出完整 Spec（Research / Plan），并在你批准后再进入 Execute。
