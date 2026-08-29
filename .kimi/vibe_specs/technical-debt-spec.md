# Technical Debt Spec 清单

> **SDD-RIPER-ONE 产物**：本文件是 Hermes Agent 当前技术债的“唯一真相源”。  
> **原则**：`No Spec, No Code`。本清单中的任何一项进入 `Execute` 阶段前，必须先被选中并产出/细化对应 Spec，再经过 `Plan Approved` 门禁。  
> **维护规则**：每完成一项技术债修复，必须同步更新本文件状态、相关测试数与文档（`docs/progress-spec.md`、`docs/session-context.md`、`docs/evaluation-log.md`、`CODEMAP.md`）。  
> **最后更新**：2026-08-22

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
| TD-010 | 沙箱网络策略增强（两阶段网络 + `network_mode` 配置化） | — | 🟡 低-中 | ✅ 已完成（2026-08-22：network_mode/allow_setup_network 配置化 + pip 意图走有网临时容器；真实 Docker 联网验证通过，Spec：`mydocs/specs/2026-08-22_td-010-sandbox-network-policy.md`） | ⚠️ 间接（S3 类场景） | 0.5-1 天 |
| TD-011 | 默认门禁套件环境不确定性（`OPENAI_*` 污染 + web 测试隐性真实调用） | — | 🟠 中 | ✅ 已完成（2026-07-19，`tests/conftest.py` 全局清理） | ❌ 否 | 0.5 天 |
| TD-012 | `requirements.txt` 与 `pyproject.toml` 依赖漂移（缺 fastapi/uvicorn/jinja2） | — | 🟡 低 | ✅ 已完成（2026-07-19） | ❌ 否 | 0.1 天 |
| TD-013 | 纯对话事实不入记忆（`llm_extraction_enabled` 有开关无实现） | — | 🟡 低-中 | ✅ 已完成（2026-07-21，LLM 提取器 + 去重 + 定时清理接通） | ❌ 否 | 1-2 天 |
| TD-014 | 代码搜索工具缺失（无 grep/glob 类一等工具） | — | 🟡 低-中 | ✅ 已完成（2026-08-22，grep/glob 双模块 + 策略卡口 + externalizer 预览分支） | ❌ 否 | 1-2 天 |
| TD-015 | 工作区无法跨会话持久 / 不能维护宿主项目（Coding Agent 形态缺口） | — | 🔴 高 | ✅ 已完成（2026-08-22：单元 B+C 落地，真实 Docker 验证 10/10 通过，Spec：`mydocs/specs/2026-08-22_td-015-persistent-workspace.md`） | ✅ 是 | 3-5 天 |
| TD-016 | 不支持 MCP 工具接入（工具注册仅内置） | — | 🟠 中 | ✅ 已完成（2026-08-22：三传输 + 惰性装配 + 默认全确认；CR 回炉修装配竞态/私有导入/close 回收；924 passed，Spec：`mydocs/specs/2026-08-22_td-016-mcp-tools.md`） | ⚠️ 间接 | 1-2 天 |
| TD-017 | `memory_limit_mb` 配置存在但工厂未透传 | — | 🟡 低 | ✅ 已完成（2026-08-22：`__init__` 新增 `mem_limit` + 工厂透传 + 3 例测试；929 passed） | ❌ 否 | 0.1 天 |
| TD-018 | 容器加固缺 `cap_drop` / `no-new-privileges` | — | 🟡 低-中 | ✅ 已完成（2026-08-22：`cap_drop=ALL`+`cap_add=CHOWN`+`no-new-privileges`，真实 Docker 冒烟通过；929 passed） | ⚠️ 安全加固 | 0.5 天 |
| TD-019 | MCP server 超时降级后无重连机制 | — | 🟡 低-中 | ✅ 已完成（2026-08-22：`degrade_ttl` 降级冷却 + TTL 过期惰性重连） | ❌ 否 | 0.5 天 |
| TD-020 | `OpenAIClient` 无流式输出 | — | 🟡 低 | ✅ 已完成（2026-08-22：chat_stream 默认回退 + SSE 解析 + 思考链捕获 + CLI 三层渲染 + DeepSeek V4 适配；reasoning_content 多轮回传待真实端点补验；963 passed） | ❌ 否 | 0.5-1 天 |
| TD-021 | bind 模式缺会话内 `/undo` `/diff` git 交互 | — | 🟡 低 | ⏳ 候选（2026-08-22 登记） | ❌ 否 | 0.5-1 天 |
| TD-022 | Web UI 无写操作确认面板 | — | 🟡 低 | ⏳ 候选（2026-08-22 登记） | ❌ 否 | 0.5-1 天 |

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

#### 修复记录

- **日期**：2026-07-21
- **方案**：新增 `src/agent/core/memory_llm_extractor.py`（LLM 驱动，PREFERENCES 事实 + TASK_SUMMARIES 摘要；预过滤成本护栏；失败静默降级）；`runtime.py` 开关接线；双层去重（LLM 增量 prompt + 保存时规范化去重）；`max_age_days` + `cleanup_on_exit` 定时清理接通（复用既有 store.cleanup 与数量淘汰）。
- **验收证据**：`tests/test_memory_llm_extractor.py` 11 个单测 + 集成测试（对话事实跨会话召回）通过；Batch 5 对话版 T101/T102（无文件载体教学）mem 臂 4/4 PASS、no-mem 臂 0/4（对照成立）；全量 745 passed / mypy 47 文件 / ruff 全绿。
- **Feature Spec**：`mydocs/specs/2026-07-21_00-35_td-013-llm-memory-extractor.md`

---

### TD-014：代码搜索工具缺失（无 grep/glob 类一等工具）

#### 背景

默认工具集（`_build_tool_specs`，`src/agent/tools/__init__.py:50-165`）只有执行/读/列/写/局部编辑/交付 6 个工具，**没有内容级代码搜索能力**：在仓库里定位符号或文本，LLM 只能在 `sandbox_exec` 里写 grep 命令绕行——不是一等工具，无路径策略检查语义，也无输出截断约定。

评测证据（工具偏好问题的结构诱因之一）：

- S2 联调（`docs/evaluation-log.md:47`）：CSV 工作流任务中 LLM 用 `sandbox_exec` 一把梭，跳过 `file_write`/`file_read`，重跑行为稳定。
- S4 联调（`docs/evaluation-log.md:49`）：稳定跳过 `file_edit`，改用 `sandbox_exec` 改文件。
- Batch 3 为此引入工具路径断言（`expected_tools` 比对 Trace 实际调用序列，`docs/evaluation-log.md:68`）——产物对但没用指定工具 = FAIL。

口径说明：S2/S4 直接证明的是"模型工具偏好"，搜索工具缺失是其合理结构诱因之一（文件/代码操作面窄），非已证因果。

#### 目标

提供 `grep`（内容搜索）与 `glob`（文件名匹配）两个一等工具，让代码定位不再依赖 `sandbox_exec` 绕行；两工具全程走统一卡口（策略检查 / 人工确认 / ExecutionContext 注入 / Trace），不破坏"工具面最小"的注册中心设计。

#### 范围

**Must Have**

1. 新增 `src/agent/tools/code_search.py`，实现两个 handler：
   - `grep(pattern, path, include?)`：正则内容搜索，输出 `路径:行号:匹配行`，带结果条数与字节截断上限；
   - `glob(pattern, path?)`：文件名匹配（fnmatch 语义），输出相对路径列表，带截断。
2. 实现复用沙箱后端：通过 `SandboxBackend.execute_code` 执行一段只读搜索脚本（`os.walk` + `re`/`fnmatch`），**不改动 `SandboxBackend` Protocol**——Docker/Subprocess 双后端自动兼容。
3. 两工具注册进 `_build_tool_specs`（默认层），受 `tools.enabled` 白名单控制。
4. 路径参数接入 `ToolRegistry._PARAMETRIC_CHECKS`（`src/agent/core/engine.py:77-83`）：映射 `("file/path", "read", "path")`，复用现有参数级策略检查与路径归一化。
5. 测试覆盖：命中 / 无命中 / 多结果截断 / 策略拒绝 / 非法正则（可参数化双后端，参照既有 `file_*` 测试惯例）。

**Non-Goals**

- 不做语义/embedding 代码检索，不引入向量数据库或索引持久化（对齐 TD-009 先例）。
- 不修改 LLM 工具选择引导（system prompt 调优如需，另立项）。
- 不为搜索工具新增网络或宿主文件系统能力（只在沙箱 workspace 语义内）。
- 不追求 ripgrep 级性能（沙箱任务规模内 Python 实现足够）。

#### 候选方案

| 方案 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|
| A. `execute_code` 跑只读搜索脚本 | 零协议改动；双后端自动兼容；复用现有超时与安全门禁 | 输出格式与截断需自行约定 | ⭐⭐⭐⭐ |
| B. `SandboxBackend` Protocol 增加 `grep`/`glob` 方法 | 语义显式、类型可查 | 破抽象：两后端都需实现，协议膨胀 | ⭐⭐ |

**建议采用方案 A**。

#### 涉及文件

- 新增：`src/agent/tools/code_search.py`
- 修改：`src/agent/tools/__init__.py`（`_build_tool_specs` 注册两条 ToolSpec）
- 修改：`src/agent/core/engine.py`（`_PARAMETRIC_CHECKS` 增加两条映射）
- 新增：`tests/test_code_search.py`（或并入 `tests/test_tools.py`）
- 修改：`docs/configuration.md`（`tools.enabled` 说明补两个工具名）

#### 验收标准

- `grep`/`glob` 在 Docker 与 Subprocess 双后端下命中/无命中行为一致。
- 策略启用时 `grep(path="/etc")` 被 `file/path` read 规则拒绝，拒绝原因回传 LLM。
- 结果超上限时截断并注明截断。
- `pytest tests/ -q` 不新增失败；`mypy src/` / `ruff check src/ tests/` 全绿。
- （可选，评测验证）以 b3 风格工具路径断言复测 S4 类任务，观察 `file_edit`/`file_read` 使用率变化。

#### 风险

- 搜索输出可能很大 → 截断上限兜底；压缩启用时大输出天然走 `ToolResultExternalizer` 外迁。
- LLM 可能仍偏好 `sandbox_exec` → 用可选评测项观察使用率，不靠 prompt 硬扭。

#### 备注

- 定位：工具面最小哲学下的按需扩展——进默认层 `_build_tool_specs` 即自动获得策略检查/人工确认/ExecutionContext 注入/Trace 记录。
- 进入 Execute 前，按 SDD-RIPER-ONE 流程在 `mydocs/specs/` 产出独立 Feature Spec（参照 TD-013 路径：`mydocs/specs/2026-07-21_00-35_td-013-llm-memory-extractor.md`）。

#### 修复记录

- **日期**：2026-08-22
- **方案**：方案 A（`execute_code` 跑只读搜索脚本，零协议改动）；拆分为 `tools/grep.py` + `tools/glob.py` 双模块（贴合"模块名=工具名=函数名"约定）；通用化参数（grep: `include`/`ignore_case`/`max_results`；glob: stdlib recursive 支持 `**`）；`_PARAMETRIC_CHECKS` 追加两条 read 映射；externalizer 预览分支扩展为 `file_read`/`grep`/`glob` 均 500 字符。
- **影响面决策**：现有测试零破坏（无工具数量断言）；评测口径接受漂移（所有评测臂默认获得新工具，新旧批次 token/成功率不可直接对比，待重新基线）——已记入 `docs/evaluation-log.md`。
- **验收证据**：`tests/test_grep_glob.py` 21 用例全过（含策略拒绝/schema/截断/双后端语义）；全量 807 passed, 1 skipped；mypy 50 文件零错误；ruff 全绿；真实 SubprocessSandboxBackend 端到端抽查通过。
- **Feature Spec**：`mydocs/specs/2026-08-22_td-014-code-search-tools.md`

---

### TD-015：工作区无法跨会话持久 / 不能维护宿主项目（Coding Agent 形态缺口）

#### 背景

沙箱工作区是"会话级一次性"的：TD-001 后同一 backend 实例内有命名 volume 挂 `/workspace`，会话内写→读→改→运行闭环成立；但默认 volume 名随机（`hermes-workspace-<8hex>`，`docker_backend.py:75-77`）、`cleanup_workspace` 默认 True、且配置层完全不透传这两个参数（`SandboxConfig` 无 workspace 字段，`config.py:234-252`；工厂 `create_sandbox_backend` 不透传，`sandbox/__init__.py:33-56`）。结果：每次会话从空白开始，无法维护一个项目、做增量更新；宿主机上看不到工作区文件，IDE/git/CI 不可达。

**核查中发现的现有 bug（附带登记）**：CLI `agent run`/`chat` 从不调用 `sandbox_backend.close()`（`Agent.close()` 只清缓存与记忆，`engine.py:517-526`；cli/ 下无 close 命中），导致孤儿 volume `hermes-workspace-<8hex>` 持续泄漏——现状既不是"清理干净"也不是"可复用"，是最差形态。

#### 目标

让 Agent 能够跨会话持久维护一个工作区，最终形态可选地直接维护宿主机上的真实项目目录（增量编辑、宿主侧 IDE/git/CI 原生可用），同时安全边界不被削弱。

#### 候选方案

| 方案 | 做法 | 优点 | 代价/风险 | 推荐度 |
|---|---|---|---|---|
| A. 产物回传 | 现状能力（`get_file` 读回，调用方落盘） | 零改动 | 只能交付快照，多文件回传笨拙，不构成"维护" | ⭐⭐（现状） |
| B. 固定 volume + 持久化 | config 增加 `workspace_volume`/`cleanup_workspace` 字段并透传；按项目名固定卷名 | 改动最小（~1 天）；隔离性完全不变；跨会话增量成立 | 宿主仍看不到文件；孤儿卷需管理；只是"沙箱里的项目" | ⭐⭐⭐⭐（第一单元） |
| C. bind mount 宿主项目目录 | 容器挂载 `宿主项目路径 → /workspace` | 真正维护宿主项目，IDE/git/CI 原生可用 | 安全模型剧变（LLM 直写宿主真实文件）；需重做写边界、宿主权限（容器 nobody uid 65534 vs 宿主属主）、Windows 路径转换 | ⭐⭐⭐⭐（最终形态，第二单元） |
| D. git 桥 | 沙箱内工作，patch/commit 交付，宿主 review 合入 | 隔离保留 + review 门禁天然 | 链路长，依赖网络（碰 TD-010） | ⭐⭐⭐（后续可选） |

**建议路线：B → C 分两单元推进**（B 先恢复"不断片"的基本能力，C 作为真 Coding Agent 形态单独过安全设计评审）。

#### 阻力分析

1. **配置与工厂断层**（小阻力）：后端参数已支持固定卷名与保留，但 `SandboxConfig`/`create_sandbox_backend` 均不透传——补齐是纯管道工作。
2. **CLI 生命周期缺口**（中阻力）：`Agent.close()` 不碰沙箱后端、CLI 不调 `close()`——volume 清理/保留语义无处挂接；bind mount 后"会话结束做什么"更需要显式生命周期。需顺手修孤儿卷泄漏。
3. **安全边界重写**（最大阻力，方案 C）：现状写边界 = `default_security_rules.yaml` 三件套（deny `..` @95 / allow `^/workspace` @50 / deny catch-all @1），语义绑死容器内 `/workspace`；且 `security.enabled` **默认 False**、`file_write`/`file_edit` 工具层零路径校验（`file_write.py:32-33` 原样透传）。挂宿主目录后，边界语义要从"容器内固定路径"变成"挂载点内 + 敏感子路径 deny（.git? .env?）"，并强烈建议写操作人工确认（TD-008 机制已就绪）默认开启。
4. **权限错配**（方案 C 特有）：容器以 nobody(65534) 写入，bind mount 下宿主侧文件属主会变成 65534（Linux 宿主）或经 Docker Desktop 文件共享层映射（Windows/macOS 行为不同）——跨平台行为需实测。
5. **Windows 路径**：`docker_backend.py` 无任何平台分支（docker-py 隐式处理 npipe）；bind mount 需要 Windows 路径→Docker 路径转换（`D:\proj` → `/d/proj` 或 Docker Desktop 语义），无现成先例，TD-001 时就标记过该风险。
6. **read 无边界**：现状 read 只 deny 敏感路径、无 catch-all；挂宿主项目后 `file_read`/`grep` 可读挂载点内一切（含 `.env`、密钥）——read 边界规则需同步设计。

#### 影响范围（预估）

- **配置**：`SandboxConfig` 新增 workspace 相关字段（volume 名/cleanup/bind mount 路径）；`SecurityConfig.workspace_path` 语义扩展。
- **沙箱层**：`docker_backend.py`（bind mount 支持、生命周期）、`subprocess_backend.py`（`workspace_root` 参数已存在，语义天然对齐 C）、`create_sandbox_backend` 工厂透传。
- **引擎/CLI**：`Agent.close()` 与 CLI 入口的沙箱生命周期收口（修孤儿卷）。
- **安全**：写边界规则集重做 + read 边界评估 + 人工确认默认策略（方案 C）。
- **工具层**：`file_write`/`file_edit` 是否加兜底路径校验（ defense-in-depth）。
- **测试/文档/评测**：双后端契约测试扩展、configuration.md/usage.md、批量评测口径（挂载点任务场景）。

#### 风险

- **高危**：方案 C 下 LLM 直写宿主真实文件——误删/误改不可逆；必须配 read/write 边界 + 人工确认 + 文档醒目标注。
- **中危**：孤儿 volume 泄漏（现状 bug，方案 B 顺带修复）；权限属主错配导致宿主侧文件难清理。
- **低危**：新旧评测口径变化（同 TD-014 先例，接受漂移）。

#### 进入 Execute 前的路径

先按 SDD-RIPER-ONE 为**单元 B**（固定 volume + 配置透传 + 孤儿卷修复）产 Feature Spec；单元 C 待 B 落地后单独立项评审安全设计。

#### 行业权限模型调研（2026-08-22，方案 C 安全设计依据）

**结论：纯权限规则层不够，行业共识是四层防御纵深组合**：

| 层 | 防什么 | 行业先例 | Litmus 现状映射 |
|---|---|---|---|
| OS 级沙箱 | 任意子进程越界、prompt injection 绕过规则 | Codex：Seatbelt(macOS)/Landlock+seccomp(Linux)；官方建议容器场景由 Docker 承担隔离、容器内可跑 full-access | ✅ 容器即沙箱层（network=none/non-root/read-only 已有）；bind mount 后挂载点即边界 |
| 权限规则/审批策略 | 日常误操作、危险命令、敏感文件 | Claude Code：deny→ask→allow 求值、`Tool(specifier)` 语法、复合命令逐段匹配；Codex：sandbox×approval 双轴正交 | ✅ PolicyEngine 规则（优先级首命中）≈ Claude Code 规则层；TD-008 人工确认钩子 = approval 层；缺"双轴"中的 approval policy 分级概念 |
| 目录边界 | 读写范围收敛 | 全员：cwd/workspace 为默认边界，扩展需显式 add-dir；Copilot 最严（linked resource 都拒） | ⚠️ 现状 write 有 `/workspace` 边界、read 无边界；bind mount 后边界语义=挂载点 |
| git 安全网 | "批准了但结果糟糕"的剩余风险 | Aider：自动 commit + dirty 快照 + /undo + `(aider)` 署名 | ❌ 完全缺失，方案 C 必配 |

**关键认知**（Claude Code 官方自认）：权限规则只对内置工具调用生效，**管不住任意子进程**（`sandbox_exec` 里 Python 自己 open 文件）——bind mount 场景下真正的边界是**挂载点 + 容器 uid**，不是规则文本。

**uid 映射（bind mount 属主问题的行业解法）**：

- 主流做法：`--user $(id -u):$(id -g)` 以宿主用户身份运行——写出文件属主正确，且 agent 对宿主文件的能力 ≤ 用户本人（最小权限）
- `userns-remap`（daemon 级）隔离更强但 bind mount 属主会被 remap 打乱，运维坑多（buildkite/onedev 有案可查），不建议首版采用
- 现状冲突：Litmus 容器固定 `user="nobody"`(65534) + chown 65534（EVAL-010），bind mount 模式需改为宿主 uid 运行——两种模式的用户模型需分离设计

**方案 C 安全设计要点（已落入本节作为设计约束）**：

1. 容器加固维持并收紧：`--cap-drop ALL`、不挂 docker.sock、网络默认关（碰 TD-010 时白名单化）
2. bind mount 只挂项目目录（配置显式指定），绝不允许挂 `$HOME`/根目录；`.env`/`.ssh`/`.git` 敏感子路径规则层 deny + 文档警示
3. 用户模型双模：volume 模式维持 nobody+chown；bind mount 模式 `--user` 宿主 uid（Windows Docker Desktop 行为需实测，可能天然映射）
4. 审批策略升级为双轴：sandbox 配置 × approval policy（参照 Codex `untrusted/on-request/on-failure/never`），bind mount 模式默认不低于 on-request
5. git 安全网：bind mount 目标是 git 仓库时，默认 agent 改动前快照 commit / 独立分支工作，提供回滚路径（Aider 模式）
6. 文档化危险面：提供管理员级开关禁用"全自动 + bind mount"组合（参照 Claude Code `disableBypassPermissionsMode`）

---

## 3.5 衍生事项登记（2026-08-22，TD-017~022）

> 来源：TD-010/015/016 实施与 CR 过程的衍生发现。均为小项，进入 Execute 前按需补 Spec（TD-017/018 可走 FAST 通道后回写）。

### TD-017：`memory_limit_mb` 配置存在但工厂未透传

**问题**：`SandboxConfig.memory_limit_mb`（`config.py:301-307`）用户可配置，但 `create_sandbox_backend`（`sandbox/__init__.py:33-90`）不透传，`DockerSandboxBackend.__init__` 的 `mem_limit` 永远是默认值——用户配置被静默忽略。TD-010 调研时发现。**修法**：工厂透传一行 + 测试一例。

**修复记录（2026-08-22，FAST 通道回写）**：`DockerSandboxBackend.__init__` 新增 `mem_limit: str | None = None`（原参数本不存在；docker 风格字符串，None=不限制），`_do_create_container` 以其为默认 `mem_limit`（调用方显式传参优先）；工厂两个 docker 分支（含 bind）透传 `f"{memory_limit_mb}m"`，config 缺省镜像默认值 256。测试：`test_sandbox.py` +2（实例默认生效/显式覆盖）、`test_sandbox_factory.py` +3（透传/默认/bind 分支）。`docs/configuration.md` 字段说明同步。全量 929 passed / 1 skipped，mypy/ruff 全绿。

### TD-018：容器加固缺 `cap_drop` / `no-new-privileges`

**问题**：容器加固现状为 non-root + read_only + tmpfs + seccomp（可选），但没有 `--cap-drop ALL` 和 `security_opt: no-new-privileges`（TD-010 CR 🟡-3 登记）。行业标准加固件。**修法**：`_do_create_container` 的 create_kwargs 加 `cap_drop=["ALL"]`、`security_opt` 追加 `no-new-privileges`；验证既有测试不碎（mock 断言需同步）；真实 Docker 冒烟一次。

**修复记录（2026-08-22，FAST 通道回写）**：create_kwargs 加 `cap_drop=["ALL"]` + `security_opt=["no-new-privileges"]`（seccomp 走 setdefault 追加，合并非覆盖）。**实测发现的交互**：`cap_drop=ALL` 使 EVAL-010 的 root exec `chown /workspace` 因缺 CAP_CHOWN 报 EPERM（volume 模式下 workspace 将不可写）——故回加 `cap_add=["CHOWN"]`（最小集合；载荷以 nobody 运行本无 cap，`no-new-privileges` 阻断 setuid/file-caps 提权，实测 `capsh` 语义下 nobody 无法获得 CHOWN）。实验证据：`docker run --cap-drop ALL` chown → EPERM；`--cap-add CHOWN` 后 chown 成功且 /workspace 变为 nobody:nogroup。测试：全参断言/默认加固断言同步 +3 处，seccomp 用例改断言合并。真实 Docker 冒烟：建容器执行 `print(1)` 输出 1，HostConfig 实测 CapDrop=[ALL]/CapAdd=[CHOWN]/SecurityOpt=[no-new-privileges]/Memory=256MiB，put_file→get_file 跨调用一致。全量 929 passed / 1 skipped，mypy/ruff 全绿。

### TD-019：MCP server 超时降级后无重连机制

**问题**：TD-016 CR Y3——server 超时降级后所有调用快速失败，唯一的恢复途径是重启 Agent。长会话里一次网络抖动就永久失去该 server。**修法**：降级状态加 TTL（如 60s）过期后下次调用先尝试重连（新 ClientSession），重连成功清标记；或提供显式 `mcp__reconnect` 管理入口。需小 Spec 定口径。

**修复记录（2026-08-22，FAST 通道回写）**：采用"降级 TTL + 惰性重连"口径（不做显式管理入口，不做后台线程）。`MCPConfig` 新增 `degrade_ttl: int = 60`；`mcp_client.py` 降级表改为 `server → (原因, monotonic 时间戳)`，`_wrap_tool` handler 改为调用时经 `_sessions` 动态解析 session（重连后旧 ToolSpec 自动指向新 session，无需重新注册工具）；新增 `_degrade_gate`（TTL 内快速失败 → 过期后在 `_reconnect_lock` 内双重检查并惰性重连）、`_reconnect_server`（旧生命周期任务先 stop 回收再在同一事件循环建新的专属任务，满足 anyio cancel scope 任务绑定）与 `_reconnect_lifecycle`（复用初次连接的 `_open_session` 路径，不重新发现工具）；`close()/aclose()` 置 `_closed` 禁止关闭后再重连。**实测坑**：SSE 形态下 MCPServer 单例在活跃连接被 kill 后内部状态污染同实例重启的 app（新连接触发 ASGI duplicate response.start 崩溃）——故 kill→重启实测走 stdio 子进程（`FAKE_MCP_PID_FILE` + `os.kill` SIGTERM，重连重新拉起子进程）。测试：`tests/test_mcp_tools.py` 新增 `TestDegradeReconnect` 5 例（TTL 配置默认/自定义、TTL 内不重连、过期重连成功、重连失败刷新时间戳、stdio kill→重连恢复），时间控制经 monkeypatch `mcp_client._monotonic` 假时钟。`docs/configuration.md` mcp 段补 `degrade_ttl` 字段与重连行为。全量 934 passed / 1 skipped，mypy 52 文件零错误，ruff 全绿。

### TD-020：`OpenAIClient` 无流式输出

**问题**：`llm/client.py` 只支持非流式 `chat()`；长任务里用户盯着空白终端等几十秒。CLI chat 体验缺口。**修法**：`stream=True` + SSE 解析逐 token 回调，CLI render 增量渲染；EchoClient 同步支持；注意 tool_calls 在流式下的聚合解析。

### TD-021：bind 模式缺会话内 `/undo` `/diff` git 交互

**问题**：TD-015 Non-Goal 遗留——bind 模式回滚目前要靠用户手动 `git reset --hard <sha>`；快照 sha 只在启动横幅出现一次，会话中不可见。**修法**：chat 模式加 `/undo`（reset 到快照）`/diff`（显示 Agent 改动）斜杠命令，仅在 bind 模式可用。

### TD-022：Web UI 无写操作确认面板

**问题**：TD-008 遗留——Web 无确认界面，导致 bind 模式下 Web 只能拒绝启动或显式关审批（风险自担）。**修法**：chat 端点遇审批请求时返回待确认状态，前端弹确认框，用户选择后重放调用。需小 Spec 定交互。

---

## 4. 下一步选择

请从上方选择**下一个要进入 SDD-RIPER-ONE 流程**的技术债，回复格式例如：

> “先处理 TD-001，请按 sdd-riper-one 给出完整 Spec 并等待 Plan Approved。”

选中后，我会为该项产出完整 Spec（Research / Plan），并在你批准后再进入 Execute。
