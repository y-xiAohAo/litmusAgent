# Progress Spec — Hermes Agent 跨会话开发进度

> **本文件是跨会话开发的“唯一真相源”。**
> 
> 每个新 session 启动时，必须先读：
> 1. `docs/progress-spec.md`（本文件）—— 当前状态与下一步任务
> 2. `CODEMAP.md`—— 代码地图与模块职责
> 3. `docs/session-context.md`—— 教学模式与工程规范
> 4. `docs/plans/2026-04-28-code-sandbox-agent.md`—— 完整阶段计划原文
>
> **说明**：本 spec 基于 `docs/plans/2026-04-28-code-sandbox-agent.md` 拆解而来，把静态计划转化为可跟踪、可更新的活文档。
>
> 最后更新：2026-07-16（Phase 4.7 已同步）

---

## 1. 项目锚点

| 项 | 值 |
|---|---|
| 项目路径 | `D:\djh\hermes\project1` |
| 项目目标 | 构建具备自我纠错能力的代码沙箱 Agent |
| 完整阶段计划 | `docs/plans/2026-04-28-code-sandbox-agent.md` |
| 当前分支 | `master` |
| Python | >= 3.10（推荐 3.11） |
| 虚拟环境 | `C:\Users\msn\AppData\Local\hermes\hermes-agent\venv\` |
| 安装命令 | `python -m pip install -e ".[dev]"` |
| 质量门禁 | `python -m pytest tests/` + `python -m mypy src/` + `python -m ruff check src/ tests/` |

---

## 2. 当前状态快照

### 2.1 任务级完成度

本表从完整阶段计划拆解，每个 Task 对应一个 commit 粒度。

#### Phase 1: 修地基

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 1.1 | 安装 dev 依赖并验证工具链 | ✅ | `pyproject.toml`, `requirements.txt` | `learning-journal.md` Phase 1.1 |
| 1.2 | 拆分 `core/types.py` | ✅ | `src/agent/core/types.py`, `tests/test_imports.py` | Phase 1.2 |
| 1.3 | 添加 structlog + pyyaml + docker 依赖 | ✅ | `pyproject.toml`, `requirements.txt` | Phase 1.3 |
| 1.4 | 创建 `config.py` | ✅ | `src/agent/config.py`, `tests/test_config.py` | Phase 1.4 |
| 1.5 | 配置 structlog 日志 | ✅ | `src/agent/logging.py`, `tests/test_logging.py` | Phase 1.5 |

#### Phase 2: Agent 核心引擎

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 2.1 | Agent 主循环 — 单轮无工具对话 | ✅ | `src/agent/core/engine.py`, `tests/test_agent_loop.py` | Phase 2.1 |
| 2.2 | Agent 主循环 — Tool Call 执行 | ✅ | `src/agent/core/engine.py` | Phase 2.2 |
| 2.3 | State 状态管理 | ✅ | `src/agent/core/state.py`, `tests/test_state.py` | Phase 2.3 |
| 2.4 | Error Handler | ✅ | `src/agent/core/error_handler.py`, `tests/test_error_handler.py` | Phase 2.4 |
| 2.5 | Planner 任务分解 | ✅ | `src/agent/core/planner.py`, `tests/test_planner.py` | Phase 2.5 |
| 2.6 | Tool Router | ✅ | `src/agent/core/tool_router.py`, `tests/test_tool_router.py` | Phase 2.6 |
| 2.7 | 集成 Agent + Planner + ErrorHandler | ✅ | `src/agent/core/engine.py`, `tests/test_integration.py` | Phase 2.7 |
| 2.8 | LLM Client 增强（重试、超时） | ✅ 完成 | `src/agent/llm/client.py`, `tests/test_llm_client.py` | `learning-journal.md` Phase 2.8 |

#### Phase 3: 沙箱层（待开始）

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 3.1 | Docker 连接与健康检查 | ✅ | `src/agent/sandbox/__init__.py`, `src/agent/sandbox/docker_backend.py` | ✅ 已更新 |
| 3.2 | 容器创建与销毁 | ✅ | `docker_backend.py` | ✅ 已更新 |
| 3.3 | 代码执行与结果捕获 | ✅ | `docker_backend.py` | ✅ 已更新 |
| 3.4 | 安全限制（cgroup, seccomp, 超时） | ✅ | `docker_backend.py` | ✅ 已更新 |
| 3.5 | 文件注入与提取 | ✅ | `docker_backend.py` | ✅ 已更新 |
| 3.6 | 容器预热池（可选） | ✅ | `docker_backend.py` | ✅ 已更新 |

#### Phase 4: 工具链与集成（已完成）

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 4.1 | `sandbox_exec` Tool | ✅ | `src/agent/tools/sandbox_exec.py`, `src/agent/tools/__init__.py`, `src/agent/core/engine.py`, `tests/test_tools.py` | 已更新 |
| 4.2 | `file_read` / `file_list` Tools | ✅ | `src/agent/tools/file_read.py`, `src/agent/tools/file_list.py`, `src/agent/tools/__init__.py`, `tests/test_tools.py` | 已更新 |
| 4.3 | `finish` Tool | ✅ | `src/agent/tools/finish.py`, `src/agent/tools/__init__.py`, `src/agent/core/engine.py`, `tests/test_tools.py` | 已更新 |
| 4.4 | 端到端集成测试 | ✅ | `tests/test_integration.py` | 已更新 |
| 4.5 | 错误恢复场景测试 | ✅ | `tests/test_integration.py` | 已更新 |
| 4.6 | 配置驱动的 Tool 加载 | ✅ | `src/agent/config.py`, `src/agent/tools/__init__.py`, `src/agent/core/engine.py`, `tests/test_config.py` | 已更新 |
| 4.7 | `file_write` / `file_edit` Tools | ✅ | `src/agent/tools/file_write.py`, `src/agent/tools/file_edit.py`, `src/agent/tools/__init__.py`, `src/agent/core/engine.py`, `src/agent/core/default_security_rules.yaml`, `src/agent/core/tool_router.py`, `tests/test_tools.py`, `tests/test_tool_security.py`, `docs/configuration.md` | 已更新 |

#### Phase 5: 核心机制扩展 — Agent Trace

> Phase 5 聚焦执行轨迹（Agent Trace）：记录 Agent 运行的完整事件流，并把 `AgentState` 接入 `Agent.run()` 主循环。`ExecutionContext` 保持已实现但暂不接入，作为独立技术债后续处理。
>
> Phase 6~10 已规划为后续独立 Phase，本次 session 不实现，仅作为未来目标写入 spec：
> - Phase 6: 反思式错误恢复
> - Phase 7: 上下文压缩
> - Phase 8: 长期记忆机制
> - Phase 9: 安全策略引擎
> - Phase 10: CLI、演示与文档

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 5.1 | Agent Trace（执行轨迹记录 + State 接入主循环） | ✅ 完成 | `src/agent/core/trace.py`、`src/agent/core/engine.py`、`tests/test_trace.py` | 已更新 |

#### Phase 6: 反思式错误恢复（已完成）

> 在 `ErrorHandler` 基础上增加主动反思层：当同类错误反复出现时，Agent 主动总结失败模式并调整恢复策略。

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 6.1 | 错误模式账本（ErrorPatternLedger） | ✅ 完成 | `src/agent/core/error_pattern.py`、`tests/test_error_pattern.py` | ✅ 已更新 |
| 6.2 | 反思策略生成器（ReflectiveAdvisor） | ✅ 完成 | `src/agent/core/reflective_advisor.py`、`tests/test_reflective_advisor.py` | ✅ 已更新 |
| 6.3 | 接入 Agent 主循环与 Trace | ✅ 完成 | `src/agent/core/engine.py`、`tests/test_reflective_integration.py` | ✅ 已更新 |
| 6.4 | 修复 ReflectiveAdvisor 尊重 ErrorClassifier 输出 | ✅ 完成 | `src/agent/core/reflective_advisor.py`、`tests/test_reflective_advisor.py` | ✅ 已更新 |

#### Phase 7: 上下文压缩（✅ 已完成）

> 当对话历史接近 LLM 上下文窗口上限时，对旧消息进行摘要、裁剪或优先级筛选。工具结果外迁到本地 Markdown 缓存，LLM 可通过 `context_read` 按需读回。

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 7.1 | Token 估算与压缩配置 | ✅ 完成 | `src/agent/core/token_estimator.py`、`src/agent/config.py`、`tests/test_context_compression.py` | ✅ 已更新 |
| 7.2 | ContextCache 与 ToolResultExternalizer | ✅ 完成 | `src/agent/core/context_cache.py`、`src/agent/core/tool_result_externalizer.py` | ✅ 已更新 |
| 7.3 | 小模型摘要器 | ✅ 完成 | `src/agent/core/summarizer.py` | ✅ 已更新 |
| 7.4 | context_read 工具 | ✅ 完成 | `src/agent/tools/context_read.py`、`src/agent/core/engine.py`、`src/agent/tools/__init__.py` | ✅ 已更新 |
| 7.5 | HybridCompressor 与主循环接入 | ✅ 完成 | `src/agent/core/compressor.py`、`src/agent/core/engine.py`、`tests/test_context_compression.py` | ✅ 已更新 |
| 7.6 | 配置、测试、文档同步 | ✅ 完成 | `src/agent/config.py`、`tests/test_context_compression.py`、相关文档 | ✅ 已更新 |

#### Phase 8: 长期记忆机制（已完成）

> 跨任务/跨会话保留关键信息（如已安装包、已生成文件、用户偏好），支持持久化存储与检索。默认关闭，不破坏 Phase 1~7 行为。

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 8.1 | 存储层：数据模型 + MemoryStore + MemoryConfig | ✅ 完成 | `src/agent/core/memory.py`、`src/agent/config.py`、`tests/test_memory_store.py`、`.kimi/vibe_specs/long_term_memory-spec.md` | 待写 |
| 8.2 | MemoryExtractor + MemoryManager（默认规则提取） | ✅ 完成 | `src/agent/core/memory.py`、`tests/test_memory_extractor.py`、`tests/test_memory_manager.py` | 待写 |
| 8.3 | 主循环集成：`memory_read` + 注入 system prompt | ✅ 完成 | `src/agent/core/engine.py`、`src/agent/tools/memory_read.py`、`src/agent/tools/__init__.py`、`src/agent/core/memory.py`、`tests/test_memory_integration.py` | 待写 |
| 8.4 | 记忆审计与用户反馈 | ✅ 完成 | `src/agent/core/memory.py`、`src/agent/cli/memory_cli.py`、`scripts/hermes-memory.py`、相关测试 | 待写 |

#### Phase 9: 安全策略引擎（进行中）

> 目标：把代码执行、文件操作、网络访问、记忆读写等安全规则系统化，形成可配置的策略引擎。详细计划见 `docs/plans/phase-9-plan.md`。

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 9.1 | 策略核心：`PolicyEngine` / `PolicyRule` / `PolicyDecision` | ✅ 完成 | `src/agent/core/security.py`、`src/agent/core/default_security_rules.yaml`、`tests/test_security_policy.py` | 待写 |
| 9.2 | 配置扩展：`SecurityConfig` | ✅ 完成 | `src/agent/config.py`、`tests/test_config.py` | 待写 |
| 9.3 | 工具执行策略拦截 | ✅ 完成 | `src/agent/core/engine.py`、`tests/test_tool_security.py` | 待写 |
| 9.4 | `sandbox_exec` 代码静态扫描 | ✅ 完成 | `src/agent/core/engine.py`、`tests/test_sandbox_security.py` | 待写 |
| 9.5 | 文件操作路径策略 | ✅ 完成 | `src/agent/core/engine.py`、`src/agent/core/default_security_rules.yaml`、`tests/test_tool_security.py` | ✅ 已更新 |
| 9.6 | 记忆读写策略 | ✅ 完成 | `src/agent/core/memory.py`、`src/agent/core/engine.py`、`tests/test_memory_security.py` | ✅ 已更新 |
| 9.7 | 文档同步 | ✅ 完成 | `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md` | ✅ 已更新 |


#### Phase 10: CLI、演示与文档（进行中）

> 原 Phase 5/6 内容整体后移。构建用户可交互的 CLI、示例脚本、README 与架构文档。

| Task | 内容 | 状态 | 产出文件 | 教程更新 |
|------|------|------|---------|---------|
| 10.1 | CLI 入口 — argparse | ✅ 完成 | `src/agent/cli/agent_cli.py`、`src/agent/cli/__main__.py`、`tests/test_cli.py`、`pyproject.toml` | ✅ 已更新 |
| 10.2 | Rich 美化输出 | ✅ 完成 | `src/agent/cli/render.py`、`src/agent/cli/agent_cli.py`、`tests/test_cli.py` | ✅ 已更新 |
| 10.3 | 交互模式 | ✅ 完成 | `src/agent/cli/chat.py`、`src/agent/cli/agent_cli.py`、`src/agent/cli/render.py`、`tests/test_cli_chat.py` | ✅ 已更新 |
| 10.4 | 示例场景脚本 | ✅ 完成 | `examples/simple_agent.py`、`examples/run_once.py`、`examples/with_config.py`、`examples/config.yaml`、`tests/test_examples.py` | ✅ 已更新 |
| 10.5 | Docker 一键启动 | ✅ 完成 | `scripts/setup-docker.py`、`docker-compose.yml`、`tests/test_docker_launch.py` | ✅ 已更新 |
| 10.6 | README 重写 | ✅ 完成 | `README.md`、`tests/test_readme.py` | ✅ 已更新 |
| 10.7 | 架构图（ASCII） | ✅ 完成 | `docs/architecture.md`、`tests/test_architecture.py` | ✅ 已更新 |
| 10.8 | 使用文档 | ✅ | `docs/usage.md`、`docs/configuration.md`、`tests/test_usage_docs.py` | ✅ 已更新 |
| 10.9 | Demo 脚本与录制准备 | ✅ | `examples/demo_real_llm.py`、`tests/test_demo.py`、`docs/demo.md` | ✅ 已更新 |

### 2.2 质量状态

```bash
# 测试结果
python -m pytest tests/ -q
# → 541 passed, 1 skipped

# 类型检查
python -m mypy src/
# → Success: no issues found in 42 source files

# Lint
python -m ruff check src/ tests/
# → All checks passed!
```

### 2.3 已知问题

1. **完整技术债清单见** `.kimi/vibe_specs/technical-debt-spec.md`，9 项债务已全部关闭（TD-001~009，2026-07-18 清零）。

---

## 3. 架构速查

详细模块说明见 `CODEMAP.md`。核心关系如下：

```
用户输入
    ↓
Agent.run() ──→ Agent.messages（对话历史）
    ↓
_build_openai_messages() ──→ Planner 进度注入 system prompt
    ↓
LLMClient.chat(messages, tools)
    ↓
ToolRegistry.execute(ToolCall) ──→ ErrorClassifier（失败时分类）
    ↓
ToolResult 追加回 messages
```

关键文件：
- `src/agent/core/engine.py` — Agent 主循环
- `src/agent/core/types.py` — `Message`, `ToolCall`, `ToolResult`, `ToolSpec`
- `src/agent/llm/client.py` — `OpenAIClient`（Phase 2.8 目标文件）
- `src/agent/core/error_handler.py` — 错误分类
- `src/agent/core/planner.py` — 任务规划

---

## 4. Phase 4 工具链详细 Spec

> 本节记录 Phase 4 各 Task 的规格与状态。已完成任务保留历史规格，当前任务用"待开始/进行中"标注。

---

### 4.1 sandbox_exec Tool

> **状态：已完成。**

#### 目标
实现 `sandbox_exec` Tool，让 Agent 能通过 Tool 调用在沙箱中执行 Python 代码。

#### 必须做
1. **创建 Tool 实现**
   - 在 `src/agent/tools/` 下新增 `sandbox_exec.py`。
   - 实现 `sandbox_exec` 函数，接收 `code: str` 参数。
   - 内部使用 `DockerSandboxBackend.execute_code()` 执行代码。
   - 返回 `ToolResult`，包含 `success`、`content`（stdout）、`error`（stderr）。

2. **注册到 ToolRegistry**
   - 修改 `src/agent/tools/__init__.py` 或提供注册函数。
   - 让 `Agent` 默认加载 `sandbox_exec` Tool。

3. **测试**
   - 新增 `tests/test_tools.py`。
   - 覆盖：执行成功返回 stdout、执行失败返回 stderr、ToolSpec 参数正确。

#### 严禁做
- 不实现 `file_read` / `file_list` / `finish`（留给 Phase 4.2-4.3）。
- 不修改 Agent 主循环的核心逻辑（只扩展 tools 注册）。
- 不写依赖真实 Docker daemon 的单元测试。

#### 涉及文件
- 新增：`src/agent/tools/sandbox_exec.py`
- 修改：`src/agent/tools/__init__.py`
- 新增：`tests/test_tools.py`

#### 验收标准
- `python -m pytest tests/test_tools.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新函数有完整类型标注和中文 docstring。

---

### 4.2 file_read / file_list Tools

> **状态：已完成。**

#### 目标
实现 `file_read` 与 `file_list` 两个 Tools，让 Agent 能通过 Tool 调用查看沙箱内的文件内容与目录列表。

#### 必须做
1. **新增 Tool 实现**
   - `src/agent/tools/file_read.py`：调用 `DockerSandboxBackend.get_file()` 读取文件并解码为文本。
   - `src/agent/tools/file_list.py`：通过 `DockerSandboxBackend.execute_code()` 执行 `os.listdir(path)` 列出目录。

2. **注册到默认工具集**
   - 修改 `src/agent/tools/__init__.py` 的 `register_default_tools()`，追加注册 `file_read` 和 `file_list`。
   - 两个 ToolSpec 的参数 schema 均只包含必填字段 `path: string`。

3. **测试**
   - 扩展 `tests/test_tools.py`。
   - 覆盖：读取成功、读取失败、列出目录、列出失败、schema 正确。

#### 严禁做
- 不实现 `finish`（留给 Phase 4.3）。
- 不修改 Agent 主循环核心逻辑。
- 不写依赖真实 Docker daemon 的单元测试。

#### 涉及文件
- 新增：`src/agent/tools/file_read.py`
- 新增：`src/agent/tools/file_list.py`
- 修改：`src/agent/tools/__init__.py`
- 修改：`tests/test_tools.py`

#### 验收标准
- `python -m pytest tests/test_tools.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新函数有完整类型标注和中文 docstring。

---

### 4.3 finish Tool

> 详细实施计划见 `docs/plans/2026-04-28-code-sandbox-agent.md` 的 "Task 4.3" 一节。

> **状态：已完成。**

#### 目标
实现 `finish` Tool，让 Agent 能显式标记任务完成并交付最终产物，同时终止 Agent 主循环。

#### 必须做
1. **创建 Tool 实现**
   - 在 `src/agent/tools/` 下新增 `finish.py`。
   - 实现 `finish(result: str)` 函数，接收 `result` 参数作为最终答案。
   - 返回 `ToolResult(success=True, content=result)`。

2. **注册到默认工具集并识别终止信号**
   - 修改 `src/agent/tools/__init__.py`，在 `register_default_tools()` 中追加注册 `finish`。
   - 修改 `src/agent/core/engine.py` 的 `Agent.run()`：当某一轮工具调用中出现 `finish` 时，立即返回其 `result.content`，终止循环。
   - 如果存在 Planner，调用 `finish` 前将当前步骤标记为完成。

3. **测试**
   - 扩展 `tests/test_tools.py`。
   - 覆盖：`finish` 返回正确结果、schema 正确、Agent 收到 `finish` 后立即停止循环。

#### 严禁做
- 不实现 Phase 4.4/4.5/4.6 的内容。
- 不改变其他 Tool 的现有行为。
- 不写依赖真实 Docker daemon 的单元测试。

#### 涉及文件
- 新增：`src/agent/tools/finish.py`
- 修改：`src/agent/tools/__init__.py`
- 修改：`src/agent/core/engine.py`
- 修改：`tests/test_tools.py`

#### 验收标准
- `python -m pytest tests/test_tools.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新函数有完整类型标注和中文 docstring。

---

### 4.4 端到端集成测试

> **状态：已完成。**

#### 目标
编写覆盖完整 Agent 工作流（计划 → 执行 → 观察 → 交付）的集成测试，验证 Phase 4 工具链在真实多轮交互中的协同行为。

#### 必须做
1. **扩展 `tests/test_integration.py`**
   - 新增端到端测试类 `TestEndToEndWorkflow`。
   - 覆盖两个完整工作流场景：
     - **无 Planner 场景**：`sandbox_exec` 写文件 → `file_list` 列目录 → `file_read` 读文件 → `finish` 交付结果。
     - **带 Planner 场景**：`TaskPlan` 分步骤推进，最终所有步骤完成并交付结果。

2. **增强 Mock 沙箱后端**
   - 新增 `StatefulMockBackend`，通过 AST 解析代码片段模拟写文件、列目录、读文件。
   - 全部在内存中完成，不连接真实 Docker daemon。

3. **中文 docstring 与注释**
   - 新增 Mock 类、测试类、辅助函数均有中文 docstring。

#### 严禁做
- 不修改四个 Tool 的实现（`sandbox_exec.py`、`file_read.py`、`file_list.py`、`finish.py`）。
- 不修改 `Agent.run()` 核心逻辑。
- 不写依赖真实 Docker daemon 的测试。
- 不超出 Phase 4.4 范围（不做 Phase 4.5/4.6）。

#### 涉及文件
- 新增：`StatefulMockBackend`、`EndToEndMockClient`、`PlannerAwareMockClient`（均位于 `tests/test_integration.py`）
- 新增测试类：`TestEndToEndWorkflow`（位于 `tests/test_integration.py`）

#### 验收标准
- `python -m pytest tests/test_integration.py::TestEndToEndWorkflow -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 167。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新增代码有完整类型标注和中文注释。

---

### 4.5 错误恢复场景测试

> **状态：已完成。**

#### 目标
编写覆盖 Agent 错误恢复路径的集成测试，验证 Agent 在完整工作流中遇到各类错误时，能否根据 `ErrorClassifier` 的提示进行自我修正、降级处理或正确终止。

#### 必须做
1. **扩展 `tests/test_integration.py`**
   - 新增错误恢复测试类 `TestErrorRecoveryWorkflow`。
   - 至少覆盖 4 个场景：
     - **代码错误自我修复**：`sandbox_exec` 抛 `SyntaxError` → LLM 看到恢复建议 → 修正代码 → 成功。
     - **环境探查后修复**：`sandbox_exec` 抛 `NameError` → LLM 用 `file_read` 检查环境 → 再次执行 → 成功。
     - **资源耗尽降级**：`sandbox_exec` 超时或内存不足 → LLM 收到 `DEGRADE` 建议 → 简化任务 → 成功。
     - **FATAL 错误终止**：`sandbox_exec` 抛 `PermissionError` → Agent 停止并报告错误。

2. **验证错误分类信息正确传递到 LLM**
   - 断言 tool result 内容包含 `[工具执行失败]`、严重级别名、恢复策略名、提示。

3. **验证 Planner 在错误场景下的状态**
   - `FATAL` 错误：当前步骤被标记为 `FAILED`。

4. **使用 Mock，不依赖真实 Docker**
   - 新增 `ErrorInjectionBackend`，按调用顺序返回预设结果。

#### 严禁做
- 不修改 `ErrorClassifier` 的现有规则映射（除非测试暴露规则确实缺失）。
- 不修改 `Agent.run()` 的核心错误处理逻辑，除非测试暴露必要缺陷且修改是最小必要改动。
- 不写依赖真实 Docker daemon 的测试。
- 不超出 Phase 4.5 范围（不做 Phase 4.6 配置驱动，不做 Phase 5 核心机制扩展）。

#### 涉及文件
- 新增：`ErrorInjectionBackend`、`SyntaxErrorRecoveryClient`、`NameErrorRecoveryClient`、`TimeoutRecoveryClient`、`FatalErrorClient`（均位于 `tests/test_integration.py`）
- 新增测试类：`TestErrorRecoveryWorkflow`（位于 `tests/test_integration.py`）

#### 验收标准
- `python -m pytest tests/test_integration.py::TestErrorRecoveryWorkflow -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 171。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新增代码有完整类型标注和中文注释。

---

### 4.6 配置驱动的 Tool 加载

> **状态：已完成。**

#### 目标
让 Agent 加载哪些 Tool 可以通过配置控制，而不是在代码中写死。用户可以根据场景决定启用哪些能力（例如只启用 `sandbox_exec` 和 `finish`，禁用文件操作）。

#### 必须做
1. **扩展 `AgentConfig`**
   - 新增 `ToolsConfig` 配置类，包含 `enabled: list[str] | None = None`。
   - `enabled` 为 `None` 时启用所有默认工具；为列表时只启用列表中的工具。
   - 将 `tools: ToolsConfig` 加入 `AgentConfig`。

2. **实现配置驱动的工具注册函数**
   - 在 `src/agent/tools/__init__.py` 中新增 `register_tools_from_config(registry, backend, config)`。
   - 根据 `config.tools.enabled` 决定注册哪些工具。
   - 未知工具名应被忽略，并记录日志警告。

3. **修改 `Agent.__init__`**
   - 增加可选参数 `config: AgentConfig | None = None`。
   - 传入 `config` 时，根据配置注册工具。
   - 未传 `config` 时，保持向后兼容，调用 `register_default_tools()` 注册所有工具。

4. **测试覆盖**
   - 配置 `enabled=None` 时注册所有默认工具。
   - 配置 `enabled=["sandbox_exec", "finish"]` 时只注册这两个工具。
   - 配置包含未知工具名时，已知工具正常注册，未知工具被忽略。
   - 通过 YAML 加载配置并验证工具注册行为。

#### 严禁做
- 不修改四个 Tool 的实现（`sandbox_exec.py`、`file_read.py`、`file_list.py`、`finish.py`）。
- 不修改 `Agent.run()` 主循环核心逻辑。
- 不引入复杂插件系统或动态导入机制。
- 不写依赖真实 Docker daemon 的测试。

#### 涉及文件
- 新增/修改：`src/agent/config.py`（`ToolsConfig`）
- 新增/修改：`src/agent/tools/__init__.py`（`register_tools_from_config`、`_build_tool_specs`）
- 修改：`src/agent/core/engine.py`（`Agent.__init__` 增加 `config` 参数）
- 测试：`tests/test_config.py`

#### 验收标准
- `python -m pytest tests/test_config.py -v` 新增测试全部通过。
- `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 178。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新增代码有完整类型标注和中文注释。

---

### 4.7 `file_write` / `file_edit` Tools

> **状态：已完成。**

#### 目标

补齐 Coding Agent 最基础的文件修改能力：让 Agent 能在沙箱内创建/覆盖文件（`file_write`）和做精确片段替换（`file_edit`），从而完成"写代码 → 改代码 → 运行验证"的最小闭环。

#### 必须做

1. **新增 `file_write` Tool**
   - 文件：`src/agent/tools/file_write.py`
   - 实现 `file_write(path: str, content: str, backend: DockerSandboxBackend) -> ToolResult`。
   - 将 `content` 按 UTF-8 编码后写入沙箱内 `path`（创建或覆盖）。

2. **新增 `file_edit` Tool**
   - 文件：`src/agent/tools/file_edit.py`
   - 实现 `file_edit(path: str, old_string: str, new_string: str, backend: DockerSandboxBackend) -> ToolResult`。
   - 读取文件，要求 `old_string` 唯一出现，替换为 `new_string` 后写回。
   - `old_string` 出现 0 次或多次时返回失败，避免歧义替换。

3. **注册到默认工具集**
   - 修改 `src/agent/tools/__init__.py`，在 `_build_tool_specs()` 中追加两个工具。
   - `register_default_tools()` 和 `register_tools_from_config()` 自动生效。

4. **接入安全策略**
   - 修改 `src/agent/core/engine.py`，在 `ToolRegistry._PARAMETRIC_CHECKS` 中增加 `file_write` / `file_edit` 的 `file/path` write 映射。
   - 修改 `src/agent/core/default_security_rules.yaml`，补充敏感路径的 write 拒绝规则。

5. **测试覆盖**
   - 写入、覆盖、写入失败。
   - 精确替换、旧字符串缺失、旧字符串不唯一、目标文件不存在。
   - ToolSpec schema 校验。
   - 危险路径写入/编辑被策略拒绝。

6. **文档与路由提示**
   - 更新 `docs/configuration.md` 中的工具列表与配置示例。
   - 更新 `src/agent/core/tool_router.py` 的使用指导。

#### 严禁做

- 不实现 `file_delete`。
- 不实现多文件 patch / diff、行号编辑、正则替换。
- 不修改 `Agent.run()` 主循环核心逻辑。
- 不写依赖真实 Docker daemon 的单元测试。

#### 涉及文件

- 新增：`src/agent/tools/file_write.py`
- 新增：`src/agent/tools/file_edit.py`
- 修改：`src/agent/tools/__init__.py`
- 修改：`src/agent/core/engine.py`
- 修改：`src/agent/core/default_security_rules.yaml`
- 修改：`src/agent/core/tool_router.py`
- 测试：`tests/test_tools.py`、`tests/test_tool_security.py`
- 文档：`docs/configuration.md`

#### 验收标准

- `python -m pytest tests/test_tools.py tests/test_tool_security.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 532。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 文档与代码实现一致。

---

## 5. Phase 5 核心机制扩展详细 Spec

> Phase 5 只实现 **Agent Trace**，其余方向（反思、压缩、记忆、安全）已规划为独立 Phase，本次 session 不实现。

---

### 5.1 Agent Trace

> **状态：已完成。**

#### 目标

实现 Agent Trace（执行轨迹记录），让 Agent 的每次运行都能生成可观测、可复盘的执行轨迹，并把 `AgentState` 接入 `Agent.run()` 主循环。`ExecutionContext` 不纳入本次 Task。

#### 必须做

1. **新增 Trace 数据模型**
   - 创建 `src/agent/core/trace.py`。
   - 定义 `AgentTrace`、`TraceStep`、`TraceEvent` 等 dataclass。
   - 每个 `TraceStep` 对应 Agent 主循环的一轮迭代。
   - 每个 `TraceEvent` 记录一个具体事件：LLM 请求、LLM 响应、工具执行、状态变化、错误分类、反思事件等。

2. **把 AgentState 接入主循环**
   - 修改 `src/agent/core/engine.py` 的 `Agent` 类。
   - 让 `Agent` 持有 `AgentState` 实例，并在 `run()` 中按阶段更新 `phase`、`current_step`。
   - 在 State 变化时记录 `state_transition` Trace 事件。
   - 注意：`ExecutionContext` 已实现但暂不接入；它需要在 future 改造工具签名/注册机制后才能被 tools 使用。

3. **在关键节点记录 Trace**
   - 每轮循环开始时记录当前 State 快照。
   - LLM 调用前记录请求消息与可用工具。
   - LLM 返回后记录响应内容或 tool_calls。
   - 每个 Tool 执行后记录结果（成功/失败）与耗时。
   - `ErrorClassifier` 分类后记录 severity 与 action。
   - `Planner` 步骤状态变化时记录事件。

4. **提供导出能力**
   - `AgentTrace.to_dict()` / `AgentTrace.to_json()`，方便调试与持久化。
   - `Agent` 暴露 `get_trace()` 方法，供外部获取本次运行轨迹。

5. **测试覆盖**
   - 新增 `tests/test_trace.py`（11 个测试）。
   - 基础覆盖：Trace 能记录多轮循环、包含 LLM 输入输出、包含 Tool 结果、包含错误分类、State 在主循环中被正确更新。
   - 端到端覆盖：带 Planner 的工作流、错误恢复工作流、多 Tool 工作流、Trace JSON 序列化、Artifacts 记录。

#### 严禁做

- 不实现上下文压缩、长期记忆、反思式错误恢复、安全策略引擎（这些是 Phase 6~9）。
- 不改变 `Agent.run()` 的核心语义（只是插入记录点和 State 更新）。
- 不引入外部数据库或持久化层。
- 不修改现有 Tool 的实现。

#### 涉及文件

- 新增：`src/agent/core/trace.py`
- 修改：`src/agent/core/engine.py`
- 新增：`tests/test_trace.py`

#### 验收标准

- `python -m pytest tests/test_trace.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 189。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新增 public 函数/类有完整类型标注和中文 docstring。

---

### 5.2 未来 Phase 规划（本次不实现）

以下 Phase 已规划，等待后续 session 实现：

- **Phase 6: 反思式错误恢复**
  - 在 `ErrorHandler` 基础上增加主动反思层，利用错误历史模式触发恢复策略。

- **Phase 7: 上下文压缩**
  - 当对话历史接近 token 上限时，对旧消息做摘要、裁剪或优先级筛选。

- **Phase 8: 长期记忆机制**
  - 跨任务/跨会话保留关键信息，支持持久化存储与检索。

- **Phase 9: 安全策略引擎**
  - 系统化的代码执行、文件操作、网络访问安全规则。

- **Phase 10: CLI、演示与文档**
  - 原 Phase 6 内容整体后移，构建用户可交互的 CLI 与项目文档。

## 6. 开发约定

### 6.1 TDD 节奏
每个 Task 严格遵循：
1. **RED**：写测试，确认失败。
2. **GREEN**：写最简实现，确认通过。
3. **REFACTOR**：整理代码，仍然通过。

### 5.2 代码风格
- 所有函数签名必须有类型标注。
- 所有 public 函数/类必须有中文 docstring。
- `ruff` 一行不超过 100 字符。
- `mypy` 开启 `strict = true`。

### 5.3 Commit 格式
```
type: description

type ∈ {feat, fix, docs, test, chore, refactor}
```

示例：
- `feat: add retry and timeout to OpenAIClient`
- `test: add LLM client retry tests`

### 5.4 跨文件修改原则
- 一个 task 一个 commit。
- 不要一次改多个无关模块。
- 修改后必须跑完整质量门禁。

---

## 7. 教程更新约定

### 7.1 为什么要更新教程

`docs/learning-journal.md` 是项目的重要资产。每个 Task 完成后，必须追加授课内容，原因：
1. 巩固设计决策和踩坑经验。
2. 为后续复习和面试准备素材。
3. 保持文档与代码同步。

### 7.2 更新时机

每个 Task 通过质量门禁后、commit 前，更新 `docs/learning-journal.md`。

### 7.3 更新内容模板

每个新 Task 的教程章节应包含：

```markdown
### X.X: 标题

#### 先理解：这个模块解决什么问题
（用 2-3 段讲清楚背景和动机）

#### 核心设计
（关键类/函数、数据流、设计决策）

#### 代码亮点
（值得学习的实现细节）

#### 踩过的坑
（实现过程中遇到的典型问题和修复）

#### 核心收获
（用 bullet 总结）
```

### 7.4 教程更新记录表

| Task | 教程章节 | 状态 |
|------|---------|------|
| 1.1 - 1.5 | Phase 1：打好地基 | ✅ 已更新 |
| 2.1 - 2.7 | Phase 2：Agent 核心引擎 | ✅ 已更新 |
| 2.8 | LLM Client 增强 | ✅ 已更新 |
| 3.1 | Docker 连接与健康检查 | ✅ 已更新 |
| 3.2 | 容器创建与销毁 | ✅ 已更新 |
| 3.3 | 代码执行与结果捕获 | ✅ 已更新 |
| 3.4 | 安全限制 | ✅ 已更新 |
| 3.5 | 文件注入与提取 | ✅ 已更新 |
| 3.6 | 容器预热池 | ✅ 已更新 |
| 4.1 | sandbox_exec Tool | ✅ 已更新 |
| 4.2 | file_read / file_list Tools | ✅ 已更新 |
| 4.3 | finish Tool | ✅ 已更新 |
| 4.4 | 端到端集成测试 | ✅ 已更新 |
| 4.5 | 错误恢复场景测试 | ✅ 已更新 |
| 4.6 | 配置驱动的 Tool 加载 | ✅ 已更新 |
| 4.7 | file_write / file_edit Tools | ✅ 已更新 |
| 5.1 | Phase 5：Agent Trace | ✅ 已更新 |
| 6.1 | Phase 6.1：错误模式账本 | ✅ 已更新 |
| 6.2 | Phase 6.2：反思策略生成器 | ✅ 已更新 |
| 6.3 | Phase 6.3：接入 Agent 主循环与 Trace | ✅ 已更新 |
| 7.1 | Phase 7：上下文压缩 | ⬜ 待更新 |
| 8.1 | Phase 8.1：长期记忆存储层 | ✅ 已更新 |
| 9.1 | Phase 9：安全策略引擎 | ✅ 已更新 |
| 10.1 - 10.4 | Phase 10：CLI、演示与文档 | ✅ 已更新（10.5~10.9 待后续 Task） |

---

## 10. Phase 8 长期记忆机制详细 Spec

> Phase 8.1~8.3 已完成并通过质量门禁；本节重点记录 Phase 8.4（可选增强）的规划，便于下一 session 接力。

---

### 10.1 背景

Phase 8 目标：跨任务/跨会话保留关键信息（已安装包、已生成文件、用户偏好、失败模式），支持持久化存储与检索。默认关闭，不破坏 Phase 1~7 行为。

核心实现位于：

- `src/agent/core/memory.py`：数据模型、存储层、规则提取器、注入器、管理器。
- `src/agent/core/engine.py`：Agent 主循环集成。
- `src/agent/tools/memory_read.py` + `src/agent/tools/__init__.py`：`memory_read` 内部工具。
- `src/agent/config.py`：`MemoryConfig`。
- `tests/test_memory_*.py`：存储、提取、管理、集成测试。

---

### 10.2 Phase 8.1~8.3 关键设计决策

1. **默认关闭**：`MemoryConfig.enabled = False`。
2. **存储格式**：JSONL，目录结构 `<memory_root>/<category>/<entry_id>.jsonl`。
3. **检索**：简单字符/token 重叠，中文按单字；不引入向量数据库。
4. **注入位置**：system prompt 末尾，planner 进度之后。
5. **记录时机**：`Agent.run()` 结束（finish / fatal / max_turns）时通过 `try/finally` 触发。
6. **失败不阻塞**：`inject` / `record` / `read` / `cleanup` 内部捕获异常。
7. **内部工具**：`memory_read` 不受 `config.tools.enabled` 控制，由 `register_memory_read` 控制。
8. **数量淘汰**：`MemoryManager._enforce_category_limit` 按 `max_entries_per_category` 淘汰最旧条目。

---

### 10.3 Phase 8.4：记忆审计与用户反馈（已完成）

> 完整计划见 `docs/plans/phase-8.4-plan.md`。本节为 spec 层面的浓缩版。

#### 目标

在 MVP 基础上提升记忆质量与可观测性：

- 让用户能给记忆打分（thumbs up/down）。
- 提供 CLI 查看/删除/反馈/审计记忆。
- 检测记忆冲突并建立条目链接。
- 按连续衰减函数降低陈旧记忆的注入优先级。
- 导出人类可读的 Markdown memory-bank。

#### 范围

| 优先级 | 内容 | 说明 |
|--------|------|------|
| P0 | 用户反馈 API + CLI feedback | 保留最新一次 score，递增 feedback_count |
| P0 | CLI list/show/delete | 独立脚本 `scripts/hermes-memory.py` |
| P1 | 注入排序增强 | confidence × feedback_multiplier × stale_multiplier |
| P1 | 冲突检测 + `linked_entry_ids` | 仅 CLI `audit` 触发，不接入 `record()` |
| P1 | 连续衰减降权 | 按 `updated_at` 和 category 阈值指数衰减 |
| P1 | Markdown memory-bank 导出 | 单向导出到 `.hermes/memory-bank/` |

#### 不做

- `access_count`（需要读写分离设计，本次不做）。
- `expires_at`（无设置入口）。
- `detect_conflicts_on_record` 自动触发（避免改动 `record()` 接口和 `engine.py`）。
- LLM 自我审计 / `LLMMemoryExtractor`（移至 **Phase 8.5**）。
- 向量/图数据库。

#### 数据模型扩展

在 `MemoryEntry` 末尾追加可选字段：

```python
feedback_score: int | None = None       # -1 踩 / 0 中性 / 1 赞
feedback_count: int = 0                 # 反馈动作次数
last_feedback_at: datetime | None = None
stale: bool = False                     # 显式标灰
linked_entry_ids: list[str] = []        # 关联条目 id（审计时建立）
```

#### 配置扩展

```python
stale_threshold_days: int = 30          # 通用半衰期（天）
environment_stale_days: int = 7         # environment 类别半衰期（天）
```

#### 新增接口草案

```python
class MemoryManager:
    def record_feedback(self, entry_id: str, score: int) -> bool: ...
    def audit(self) -> tuple[list[MemoryEntry], list[MemoryConflict]]: ...

class MemoryConflictDetector:
    def detect(self, store: MemoryStore) -> list[MemoryConflict]: ...
```

#### 冲突检测规则

| 类别 | 冲突类型 | 检测逻辑 |
|------|----------|----------|
| `environment` | `version_mismatch` | 同一 `package.name` 出现不同 `version` |
| `artifacts` | `duplicate` | 同一 `path` 出现多次 |
| `preferences` | `contradiction` | 同一 `key` 出现不同 `value` |
| `failure_patterns` | `recovery_conflict` | 同一 `(tool, exc_type)` 出现不同 `recovery` |

#### CLI 命令

```bash
python scripts/hermes-memory.py list [--category environment] [--limit N]
python scripts/hermes-memory.py show <entry_id>
python scripts/hermes-memory.py delete <entry_id>
python scripts/hermes-memory.py feedback <entry_id> --score 1
python scripts/hermes-memory.py audit [--category environment]
python scripts/hermes-memory.py export
```

#### 连续衰减公式

```python
age_days = (now - entry.updated_at).total_seconds() / 86400
half_life = config.environment_stale_days if category == environment else config.stale_threshold_days
stale_multiplier = 0.5 ** (age_days / half_life)
```

#### 严禁做

- 不引入向量/图数据库。
- 不修改现有 Tool 签名或行为。
- 不改动 `Agent.run()` / `engine.py` 核心逻辑。
- 不替换 `ReflectiveAdvisor` / `ErrorPatternLedger`。
- 不默认开启长期记忆。
- 不让记忆失败阻塞主循环。

#### 验收标准

- `pytest tests/`：**373 passed, 1 skipped**（基线 331 passed, 1 skipped）。
- `mypy src/` / `ruff check src/ tests/` 全绿。
- 新增测试覆盖反馈、CLI、冲突检测、排序、陈旧降权、Markdown 导出。
- 旧 JSONL 记忆文件反序列化不崩溃。

---

## 8. 跨会话交接清单

### 新 session 启动必读
1. `docs/progress-spec.md`（本文件）
2. `CODEMAP.md`
3. `docs/session-context.md`
4. `docs/plans/2026-04-28-code-sandbox-agent.md`（详细实施计划）
5. `docs/learning-journal.md`（已完成的教学内容）

### 恢复开发状态
```bash
cd /d/djh/hermes/project1
python -m pytest tests/ -q      # 确认基线
python -m mypy src/             # 确认类型
python -m ruff check src/ tests/ # 确认 lint
```

### 当前阻塞点
- 无阻塞点。Phase 8.1~8.3 已完成，Phase 8.4 处于规划阶段（详见 `docs/plans/phase-8.4-plan.md`）。

---

## 9. 变更日志

| 日期 | 变更 | 操作人 |
|------|------|--------|
| 2026-07-18 | 完成 memory_search 工具：search-then-read 召回重构（自然语言搜索复用分层检索），实测 LLM 零 URI 猜测错误，新增 8 个测试 | AI Agent |
| 2026-07-18 | 完成记忆分层检索修复：L0 recency 兜底（默认开）+ L2 条件 LLM 语义重排（默认关）+ artifact 内容快照注入，S6 复验 0/2→2/2，新增 11 个测试 | AI Agent |
| 2026-07-18 | 完成 Auto-Planner：run() 自动 LLM 规划（PlannerConfig + 解析 + 降级 + --plan 旗标），真实验证 file_edit 0/8→2/2，新增 12 个测试；修复 planner 进度显示 bug | AI Agent |
| 2026-07-18 | 真实 LLM 联调：新增 examples/e2e_suite.py 场景套件（7 离线测试）+ 预置镜像 Dockerfile；S1-S5+双对照实测 5/7 PASS，632 passed | AI Agent |
| 2026-07-18 | 完成 TD-007：`image_registry` 镜像源配置（拉取+打标回原名），技术债清单 9/9 清零；修复 EVAL-009（docker-py 7.x exec_run timeout 不兼容） | AI Agent |
| 2026-07-18 | 关闭 TD-009：核实 Phase 8.4 已交付（CLI list/show/delete/feedback/export + 反馈乘数 1.5x + Markdown 导出），验收实况 6/6 通过 | AI Agent |
| 2026-07-18 | 完成 TD-008（CLI 部分）：写操作人工确认钩子（HumanApprovalConfig + registry 钩子 + CLI y/n/a + `--approve` 旗标），新增 11 个测试；Web UI 确认留待后续 | AI Agent |
| 2026-07-18 | 完成 TD-005：RuntimeServices 统一装配解耦 `Agent.__init__`（三槽位 + from_config 工厂 + register_internal_tools），新增 9 个测试 | AI Agent |
| 2026-07-17 | 完成 TD-004：ExecutionContext 接入工具签名（register 时签名探测 + 条件注入 + session 级生命周期），sandbox_exec 增加 pip 包记录示例，新增 14 个测试 | AI Agent |
| 2026-07-17 | 完成 TD-006：file/path write 默认 workspace 边界（三件套规则 + `security.workspace_path` 配置），新增 9 个测试 | AI Agent |
| 2026-07-17 | 完成 TD-002+TD-003：SubprocessSandboxBackend 轻量后端 + create_sandbox_backend 工厂 + backend 配置生效，新增 25 个测试 | AI Agent |
| 2026-07-16 | 完成 Phase 4.7：实现 `file_write` / `file_edit` Tools，补齐文件写/编辑能力，新增 8 个测试 | AI Agent |
| 2026-07-16 | 修复 TD-001：Docker 后端引入 workspace volume，实现跨调用文件持久化，重写并新增 9 个 sandbox 测试 | AI Agent |
| 2026-07-15 | 新增评测日志体系：docs/evaluation-log.md、.kimi/vibe_specs/evaluation-spec.md、tests/test_evaluation_log.py | AI Agent |
| 2026-07-15 | 新增评测日志体系：docs/evaluation-log.md、.kimi/vibe_specs/evaluation-spec.md、tests/test_evaluation_log.py | AI Agent |
| 2026-07-12 | 完成 Phase 10.9：Demo 脚本与录制准备，新增 examples/demo_real_llm.py、tests/test_demo.py、docs/demo.md | AI Agent |
| 2026-07-12 | 完成 Phase 10.8：使用文档，新增 docs/usage.md、docs/configuration.md 与 tests/test_usage_docs.py | AI Agent |
| 2026-07-12 | 完成 Phase 10.7：ASCII 架构图，重写 docs/architecture.md，新增 tests/test_architecture.py | AI Agent |
| 2026-07-12 | 完成 Phase 10.6：README 重写，修正错误示例，新增 tests/test_readme.py | AI Agent |
| 2026-07-12 | 完成 Phase 10.5：Docker 一键启动脚本，新增 setup-docker.py、docker-compose.yml、8 个测试 | AI Agent |
| 2026-07-12 | 完成 Phase 10.4：示例场景脚本，新增 3 个示例 + 1 个配置文件 + 7 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 8.3：长期记忆主循环集成，新增 `memory_read` 工具与 `memory_recorded` Trace 事件 | AI Agent |
| 2026-07-04 | 完成 Phase 8.2：MemoryExtractor / MemoryManager（规则提取、注入、清理、敏感过滤、数量淘汰） | AI Agent |
| 2026-07-04 | 完成 Phase 8.1：长期记忆存储层与数据模型 | AI Agent |
| 2026-07-04 | 规划：新增 Phase 8.4 接力文档 `docs/plans/phase-8.4-plan.md` | AI Agent |
| 2026-07-04 | 完成 Phase 9.1~9.2：安全策略核心 `PolicyEngine` / `SecurityConfig`，默认规则集使用 YAML 配置 | AI Agent |
| 2026-07-04 | 完成 Phase 9.3~9.4：`ToolRegistry` 策略拦截 + `sandbox_exec` 代码静态扫描 | AI Agent |
| 2026-07-04 | 完成 Phase 9.5~9.7：文件路径策略、记忆读写策略、文档同步；新增 `tests/test_memory_security.py` | AI Agent |
| 2026-07-04 | 补充 Phase 9 主循环集成测试：`tests/test_security_integration.py`，覆盖文件/沙箱/记忆策略在主循环中的拦截与恢复 | AI Agent |
| 2026-07-04 | 完成 Phase 5.1：Agent Trace + AgentState 接入主循环，新增 11 个测试（含端到端） | AI Agent |
| 2026-07-04 | 规划更新：Phase 5 聚焦 Agent Trace，Phase 6~10 列为未来独立 Phase | AI Agent |
| 2026-07-02 | 清理技术债：修复 Phase 2.7 遗留失败测试 + 全部 ruff 错误 | AI Agent |
| 2026-07-02 | 完成 Phase 2.8：OpenAIClient 超时/重试/from_env，新增 17 个测试 | AI Agent |
| 2026-07-02 | 更新 `docs/learning-journal.md` Phase 2.8 教学内容 | AI Agent |
| 2026-07-02 | 创建本文件，基于完整阶段计划拆解任务表，加入教程更新约定 | AI Agent |
| 2026-07-04 | 修复 Phase 3.6 阻塞问题：close()/__aexit__() 清理预热池，补充 3 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 3.6：轻量容器预热池，新增 6 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 3.5：文件注入与提取，新增 8 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 3.4：安全限制（cgroup、seccomp、网络、用户、只读），新增 8 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 3.3：代码执行与结果捕获，新增 7 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 3.2：容器创建与销毁，新增 7 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 4.3：实现 `finish` Tool，Agent 主循环识别并终止，新增 3 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 4.2：实现 `file_read` / `file_list` Tools，新增 6 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 4.6：配置驱动的 Tool 加载，新增 ToolsConfig 和 register_tools_from_config，新增 7 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 4.5：错误恢复场景测试，覆盖 SyntaxError/NameError/TimeoutError/PermissionError，新增 4 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 4.4：端到端集成测试，覆盖无 Planner / 带 Planner 完整工作流，新增 2 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 4.1：实现 `sandbox_exec` Tool，Agent 默认加载，新增 3 个测试 | AI Agent |
| 2026-07-04 | 完成 Phase 3.1：Docker 连接与健康检查，新增 9 个测试 | AI Agent |
| 2026-07-02 | 清理临时文件与生成目录，提交 `CODEMAP.md` 和 `docs/progress-spec.md` | AI Agent |
| 2026-04-28 | 完成 Phase 2.7 集成测试 | Hermes Agent |


## 技术债处理记录

| 日期 | 技术债 ID | 内容 | 状态 | 负责人 |
|------|----------|------|------|--------|
| 2026-07-04 | TD-001 | Docker 后端文件跨轮持久性：使用命名 workspace volume 挂载到 `/workspace`，池化容器共享工作区 | ✅ 已完成 | AI Agent |

### TD-001 修复摘要

- **问题**：原 `DockerSandboxBackend` 使用临时容器池，容器销毁后文件丢失，导致 `file_write` → `file_read` / `sandbox_exec` 跨调用不可见。
- **方案**：为每个 backend 实例创建命名 Docker volume 并挂载到 `/workspace`；池化容器共享该 volume；backend 关闭时清理 volume。
- **影响文件**：`src/agent/sandbox/docker_backend.py`、`src/agent/core/tool_router.py`、`tests/test_sandbox.py`。
- **测试结果**：`tests/test_sandbox.py` 61 passed；全量 `pytest tests/` 541 passed，1 skipped。
- **使用约定**：需要持久化的文件应写在 `/workspace` 下；`/tmp` 仍保持临时语义，容器销毁后丢失。
