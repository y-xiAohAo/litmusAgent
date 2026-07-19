# CODEMAP — Litmus Agent 项目代码地图

> 本文件由 AI 代理在 2026-07-02 生成，2026-07-12 更新。用于快速理解项目结构、模块职责和开发边界。
> 生成时项目状态：Phase 6 已完成；229 个测试通过，0 失败，mypy 零错误，ruff 零错误。
> 更新时项目状态：Phase 10.9 已完成；516 个测试通过，1 个跳过，mypy 零错误，ruff 零错误。

---

## 1. 项目总览

| 项目 | 说明 |
|------|------|
| 名称 | Litmus Agent / Code Sandbox Agent |
| 定位 | 具备自我纠错能力的 LLM Agent 框架：写代码 → 执行 → 观察结果 → 修正 → 交付产物 |
| 当前路径 | `D:\djh\hermes\project1` |
| Python | >= 3.10，建议使用 3.11 |
| 包管理 | `pyproject.toml` + `requirements.txt` |
| 布局 | src-layout（源码在 `src/agent/`） |
| 分支 | `master`，共 20 个 commit |

---

## 2. 目录结构

```
D:\djh\hermes\project1
├── .github/workflows/ci.yml     # GitHub Actions CI（lint / mypy / test）
├── docs/
│   ├── architecture.md          # ASCII 架构图与组件说明（Phase 10.7）
│   ├── usage.md                 # CLI 与 Python API 使用指南（Phase 10.8）
│   ├── configuration.md         # YAML 配置完整参考（Phase 10.8）
│   ├── demo.md                  # Demo 运行指南（Phase 10.9）
│   ├── evaluation-log.md        # 评测结果、Bug、优化记录
│   ├── session-context.md       # 跨会话交接上下文（必读）
│   ├── plans/
│   │   └── 2026-04-28-code-sandbox-agent.md   # 完整实施计划 Phase 1-6
│   └── pr-description-windows-cwd.md          # 遗留 PR 描述（与当前项目无直接关联）
├── examples/
│   ├── simple_agent.py          # 最小可运行示例：EchoClient + 自定义 tool（Phase 10.4）
│   ├── run_once.py              # 单次任务示例：模拟 agent run（Phase 10.4）
│   ├── with_config.py           # 配置驱动示例：从 YAML 加载配置（Phase 10.4）
│   ├── config.yaml              # 示例配置文件（Phase 10.4）
│   ├── demo_real_llm.py         # 真实 LLM 演示脚本（Phase 10.9）
│   ├── e2e_suite.py             # 真实 LLM 场景联调套件（S1-S12，evaluation-log 产出通道）
│   ├── batch_e2e.py             # 批量评测 Runner：三机制臂对照 + 混合判分 + 工具路径断言（2026-07-19）
│   ├── batch_tasks.py           # 任务集 b1：20 基线任务（L1-L3）
│   ├── batch_tasks_b2.py        # 任务集 b2：20 高难任务，显式分步形态（L3-L4）
│   ├── batch_tasks_b3.py        # 任务集 b3：20 开放任务，零步骤枚举 + 工具路径断言
│   └── docker/                  # Docker 示例配置
├── scripts/
│   ├── setup.sh                 # 一键创建 venv 并安装依赖（Linux/Mac）
│   ├── hermes-memory.py         # 记忆管理 CLI 入口（Phase 8.4）
│   └── setup-docker.py          # Docker 环境检查与默认镜像准备（Phase 10.5）
├── docker-compose.yml           # Docker Compose 运行配置（Phase 10.5）
├── src/agent/                   # 核心源码
│   ├── __init__.py              # 对外导出 Agent, Message, ToolCall, ToolResult
│   ├── cli/                     # CLI 子包（Phase 8.4；未来 Phase 10 可扩展）
│   │   ├── __init__.py          # 导出 main
│   │   └── memory_cli.py        # 记忆管理 CLI 实现（list/show/delete/feedback/audit/export）
│   ├── config.py                # Pydantic + YAML 配置系统
│   ├── logging.py               # structlog 结构化日志配置
│   ├── core/                    # 核心引擎
│   │   ├── __init__.py          # 重导出核心类型
│   │   ├── engine.py            # Agent 主循环 + ToolRegistry（含策略拦截）
│   │   ├── types.py             # Message, ToolCall, ToolResult, ToolSpec
│   │   ├── state.py             # AgentState + ExecutionContext
│   │   ├── trace.py             # AgentTrace + TraceEvent（Phase 5.1）
│   │   ├── error_handler.py     # 错误分级与恢复策略
│   │   ├── error_pattern.py     # 错误模式账本（Phase 6.1）
│   │   ├── reflective_advisor.py # 反思策略生成器（Phase 6.2）
│   │   ├── security.py          # 安全策略引擎（Phase 9.1）
│   │   ├── default_security_rules.yaml  # 默认宽松规则集（Phase 9.1）
│   │   ├── token_estimator.py   # Token 估算器（Phase 7.1）
│   │   ├── context_cache.py     # 工具结果本地缓存（Phase 7.2）
│   │   ├── tool_result_externalizer.py # 工具结果外迁器（Phase 7.2）
│   │   ├── summarizer.py        # 文本摘要器（Phase 7.3）
│   │   ├── compressor.py        # 上下文压缩器（Phase 7.5）
│   │   ├── planner.py           # TaskPlan / PlanStep 任务规划器
│   │   └── tool_router.py       # 工具选择提示生成器
│   ├── llm/                     # LLM 客户端适配器
│   │   ├── __init__.py          # 重导出
│   │   ├── base.py              # BaseLLMClient 抽象 + EchoClient 测试桩
│   │   └── client.py            # OpenAI 兼容客户端（httpx）
│   ├── sandbox/                 # 沙箱执行层
│   │   ├── __init__.py          # 导出 DockerSandboxBackend
│   │   └── docker_backend.py    # Docker 连接、镜像准备、容器管理（Phase 3）
│   └── tools/
│       ├── __init__.py          # 提供 register_default_tools，默认注册所有工具
│       ├── sandbox_exec.py      # sandbox_exec Tool 实现（调用 Docker 后端）
│       ├── file_read.py         # file_read Tool 实现
│       ├── file_write.py        # file_write Tool 实现（Phase 4.7）
│       ├── file_list.py         # file_list Tool 实现
│       ├── file_edit.py         # file_edit Tool 实现（Phase 4.7）
│       ├── finish.py            # finish Tool 实现
│       └── context_read.py      # 读取 hermes://context/ 缓存内容（Phase 7.4）
├── tests/                       # 测试集（532 用例，1 跳过）
│   ├── test_imports.py
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_core.py
│   ├── test_agent_loop.py
│   ├── test_state.py
│   ├── test_error_handler.py
│   ├── test_planner.py
│   ├── test_tool_router.py
│   ├── test_integration.py
│   ├── test_sandbox.py
│   ├── test_tools.py
│   ├── test_trace.py             # Agent Trace（Phase 5.1）
│   ├── test_architecture.py      # 架构文档验证（Phase 10.7）
│   ├── test_usage_docs.py        # 使用与配置文档验证（Phase 10.8）
│   ├── test_demo.py              # Demo 脚本验证（Phase 10.9）
│   ├── test_evaluation_log.py    # 评测日志结构验证
│   ├── test_readme.py            # README 验证（Phase 10.6）
│   ├── test_examples.py          # 示例脚本验证（Phase 10.4）
│   ├── test_docker_launch.py     # Docker 启动脚本验证（Phase 10.5）
│   ├── test_error_pattern.py     # 错误模式账本（Phase 6.1）
│   ├── test_reflective_advisor.py # 反思策略生成器（Phase 6.2）
│   ├── test_reflective_integration.py # 反思式错误恢复集成（Phase 6.3）
│   ├── test_context_compression.py # 上下文压缩（Phase 7.1）
│   ├── test_memory_store.py      # 记忆存储层（Phase 8.1）
│   ├── test_memory_extractor.py  # 记忆提取（Phase 8.2）
│   ├── test_memory_manager.py    # 记忆管理 / 注入排序（Phase 8.2 / 8.4）
│   ├── test_memory_integration.py # 记忆主循环集成（Phase 8.3）
│   ├── test_memory_feedback.py   # 用户反馈 API（Phase 8.4）
│   ├── test_memory_conflict.py   # 冲突检测与审计（Phase 8.4）
│   ├── test_memory_cli.py        # 记忆 CLI（Phase 8.4）
│   ├── test_security_policy.py   # 策略引擎（Phase 9.1）
│   ├── test_tool_security.py     # 工具执行安全（Phase 9.3）
│   ├── test_sandbox_security.py  # 沙箱代码安全（Phase 9.4）
│   ├── test_memory_security.py   # 记忆读写安全（Phase 9.6）
│   └── test_security_integration.py  # 安全策略主循环集成测试（Phase 9）
├── CODEMAP.md                   # 本文件
├── Makefile                     # 常用命令封装
├── pyproject.toml               # 包配置 + 工具链配置
├── README.md                    # 项目入口文档（Phase 10.6 重写）
└── requirements.txt             # 依赖清单
```

---

## 3. 模块职责速查

### 3.1 配置与基础设施

| 文件 | 核心类/函数 | 职责 |
|------|------------|------|
| `src/agent/config.py` | `LLMConfig`, `AgentRuntimeConfig`, `SandboxConfig`, `SecurityConfig`, `AgentConfig`, `load_config()` | YAML 配置加载与类型校验；Phase 9 新增 `SecurityConfig` |
| `src/agent/logging.py` | `configure_logging()`, `get_logger()` | structlog 结构化日志（开发/生产双模式） |

### 3.2 核心引擎（`src/agent/core/`）

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `types.py` | `Message`, `ToolCall`, `ToolResult`, `ToolSpec` | 跨模块基础数据类型 |
| `engine.py` | `ToolRegistry`, `Agent` | Agent 主循环、工具注册与执行（已集成反思式错误恢复与 ExecutionContext 注入）；内部工具依赖由 RuntimeServices 装配（TD-005） |
| `runtime.py` | `RuntimeServices` | 内部工具运行时依赖集合：三槽位 + `from_config()` 工厂（TD-005） |
| `state.py` | `AgentState`, `ExecutionContext` | 执行阶段、产物、环境上下文 |
| `error_handler.py` | `ErrorSeverity`, `RecoveryAction`, `ErrorClassifier` | 异常 → 严重级别 + 恢复策略 |
| `error_pattern.py` | `ErrorPattern`, `ErrorPatternLedger` | 记录并识别重复错误模式（Phase 6.1） |
| `reflective_advisor.py` | `ReflectiveAdvisor`, `ReflectionAdvice` | 根据错误模式生成反思提示和策略升级（Phase 6.2） |
| `token_estimator.py` | `TokenEstimator`, `CharTokenEstimator`, `TiktokenEstimator` | 估算消息列表的 token 占用（Phase 7.1） |
| `context_cache.py` | `ContextCache`, `CacheEntry` | 本地文件缓存，按 session/run 存储工具结果（Phase 7.2） |
| `tool_result_externalizer.py` | `ToolResultExternalizer` | 把过长工具结果外迁到缓存，消息中只留引用（Phase 7.2） |
| `summarizer.py` | `Summarizer`, `StaticSummarizer`, `LLMSummarizer` | 文本摘要：规则摘要 + 小模型摘要（Phase 7.3） |
| `compressor.py` | `ContextCompressor`, `HybridCompressor`, `CompressionResult` | 消息历史压缩：保护头尾 + 摘要中间（Phase 7.5） |
| `memory.py` | `MemoryCategory`, `MemoryEntry`, `MemoryStore`, `StructuredMemoryStore`, `MemoryManager`, `MemoryConflictDetector`, `MemoryConflict` | 长期记忆数据模型、存储、注入、记录、审计、冲突检测；Phase 9 接入 `memory/category` 读写策略 |
| `security.py` | `PolicyAction`, `PolicyEngine`, `PolicyRule`, `PolicyDecision` | 安全策略引擎（Phase 9.1） |
| `default_security_rules.yaml` | 默认规则集 | 开箱即用的宽松安全规则（Phase 9）；含 file/path write 的 workspace 边界三件套（TD-006） |
| `planner.py` | `StepStatus`, `PlanStep`, `TaskPlan` | 任务步骤状态机与进度注入（进度显示已封顶）；配合 `agent.planner.enabled` 自动 LLM 规划（Auto-Planner） |
| `tool_router.py` | `ToolRouter` | 生成工具使用说明，启发式工具类别建议 |

### 3.6 CLI 层（`src/agent/cli/`）

| 文件 | 核心类/函数 | 职责 |
|------|------------|------|
| `agent_cli.py` | `build_parser()`, `main()`, `cmd_run()`, `cmd_config()`, `cmd_chat()` | Agent 主 CLI：run / config / chat / --version（Phase 10.1 / 10.3） |
| `render.py` | `render_config()`, `render_result()`, `render_error()`, `render_tool_summary()` | CLI 输出渲染：Rich 表格/面板/工具摘要与 `--plain` 回退（Phase 10.2 / 10.3） |
| `chat.py` | `run_chat_loop()`, `_read_user_input()`, `_handle_command()`, `_extract_tool_summary()` | 交互式对话循环：`agent chat` 多轮对话、特殊命令、工具摘要（Phase 10.3） |
| `memory_cli.py` | `build_parser()`, `main()`, `cmd_*()` | 记忆管理 CLI：list/show/delete/feedback/audit/export（Phase 8.4） |
| `__main__.py` |  | `python -m agent.cli` 入口（Phase 10.1） |

### 3.3 LLM 适配器（`src/agent/llm/`）

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `base.py` | `BaseLLMClient`, `EchoClient` | 抽象接口与测试桩 |
| `client.py` | `OpenAIClient` | OpenAI 兼容 API 调用（httpx，带重试/超时/from_env） |

### 3.4 沙箱层（`src/agent/sandbox/`）

| 文件 | 核心类 | 职责 |
|------|--------|------|
| `docker_backend.py` | `DockerSandboxBackend` | Docker daemon 连接、镜像准备、容器生命周期管理、命名 workspace volume 持久化 |
| `base.py` | `ExecutionResult`, `SandboxBackend(Protocol)` | 沙箱层公共契约（TD-002） |
| `subprocess_backend.py` | `SubprocessSandboxBackend` | 轻量 fallback：临时目录 workspace、POSIX 路径映射、防逃逸（TD-002） |
| `__init__.py` | `create_sandbox_backend()` | 按 `config.sandbox.backend` 选择后端，未知值警告回退 subprocess（TD-003） |

### 3.5 工具层（`src/agent/tools/`）

| 文件 | 核心类/函数 | 职责 |
|------|------------|------|
| `__init__.py` | `register_default_tools()` / `register_tools_from_config()` | 将默认工具注册到 `ToolRegistry`，支持配置驱动加载 |
| `sandbox_exec.py` | `sandbox_exec()` | 在 Docker 沙箱中执行 Python 代码并返回 `ToolResult` |
| `file_read.py` | `file_read()` | 读取沙箱内指定文件内容 |
| `file_write.py` | `file_write()` | 在沙箱内创建或覆盖文件（Phase 4.7） |
| `file_list.py` | `file_list()` | 列出沙箱内指定目录的文件 |
| `file_edit.py` | `file_edit()` | 精确编辑沙箱内已有文件内容（Phase 4.7） |
| `finish.py` | `finish()` | 标记任务完成并返回最终结果 |
| `context_read.py` | `context_read()` | 读取 `hermes://context/...` 缓存内容（Phase 7.4） |

Phase 4 工具链基础工具已全部实现。

---

## 4. 核心数据流

```
用户输入
    ↓
Agent.run(user_input)
    ↓
构建 OpenAI 消息（_build_openai_messages）
    - system prompt（可选追加 Planner 进度）
    - 历史 messages
    ↓
LLMClient.chat(messages, tools)
    ↓
解析 response
    ├─ 纯文本 → 返回给用户
    └─ tool_calls → ToolRegistry.execute()
            ↓
        成功 → 结果加入 messages → 继续循环
        失败 → ErrorClassifier 分类 → ErrorPatternLedger 记录 → ReflectiveAdvisor 反思升级 → 附加恢复建议 → 加入 messages → 继续循环
            ↓
        effective FATAL 级别 → 终止循环并返回错误信息
```

---

## 5. 关键设计决策

1. **注册表模式**：`ToolRegistry` 与 `Agent` 分离，工具可独立测试、动态扩展。
2. **依赖注入**：`planner` 和 `error_classifier` 都是可选注入，简单场景无需传入。
3. **内部 dataclass / 外部 dict**：内部用 `Message`/`ToolCall` 保证类型安全，发送给 LLM 时转 OpenAI dict。
4. **错误不抛异常**：工具执行失败返回 `ToolResult(success=False)`，让 LLM 看到错误并自我修正。
5. **保守分类**：未知异常默认 `FATAL + REPORT`，避免盲目重试烧钱。
6. **Advisor 尊重分类器**：`ReflectiveAdvisor` 以 `ErrorClassifier` 输出为当前阶段，仅向上升级，不覆盖、不降级。

---

## 6. 当前进度（对照 `docs/plans/`）

| Phase | 状态 | 备注 |
|-------|------|------|
| Phase 1: 修地基 | ✅ 完成 | 依赖、配置、日志已就位 |
| Phase 2.1-2.6: 核心组件 | ✅ 完成 | 主循环、状态、错误、规划、路由 |
| Phase 2.7: 集成测试 | ✅ 完成 | 6 个集成测试全部通过 |
| Phase 2.8: LLM Client 增强 | ✅ 完成 | 重试、超时、`from_env()` |
| Phase 3.1: Docker 连接与健康检查 | ✅ 完成 | `DockerSandboxBackend` ping / ensure_image |
| Phase 3.2: 容器创建与销毁 | ✅ 完成 | `DockerSandboxBackend` create_container / remove_container |
| Phase 3.3: 代码执行与结果捕获 | ✅ 完成 | `DockerSandboxBackend` execute_code / ExecutionResult |
| Phase 3.4: 安全限制 | ✅ 完成 | `DockerSandboxBackend` memory/network/user/readonly 限制 |
| Phase 3.5: 文件注入与提取 | ✅ 完成 | `DockerSandboxBackend` put_file / get_file |
| Phase 3.6: 容器预热池 | ✅ 完成 | `DockerSandboxBackend` warmup / pool |
| Phase 4: 工具链与集成 | ✅ 完成 | 4.1-4.3 工具实现、4.4 端到端测试、4.5 错误恢复测试、4.6 配置驱动加载、4.7 文件写/编辑工具全部完成 |
| Phase 5: 核心机制扩展 — Agent Trace | ✅ 完成 | 执行轨迹记录 + State 接入主循环 |
| Phase 6: 反思式错误恢复 | ✅ 完成 | 错误模式账本 + 反思策略生成器 + 主循环/Trace 接入 |
| Phase 7: 上下文压缩 | ✅ 完成 | 消息历史摘要 / 裁剪 / 工具结果外迁 |
| Phase 8: 长期记忆机制 | ✅ 完成 | 跨任务持久化记忆 + 用户反馈 + 冲突检测 + CLI 管理 |
| Phase 9: 安全策略引擎 | ✅ 完成 | 策略核心 + 工具拦截 + 沙箱代码扫描 + 文件路径策略 + 记忆读写策略 |
| Phase 10: CLI、演示与文档 | ✅ 完成（10.1 - 10.9） | argparse + Rich + 交互模式 + 示例脚本 + Docker 一键启动 + README + 架构图 + 使用文档 + Demo 脚本全部完成 |

---

## 7. 常用命令

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/ -v

# 类型检查
python -m mypy src/

# Lint
python -m ruff check src/ tests/

# 格式化
python -m ruff format src/ tests/

# 运行示例
python examples/simple_agent.py
```

---

## 8. 已知问题与技术债

### 8.1 功能缺口

- `OpenAIClient` 缺少：流式输出（重试、超时、`from_env()` 已完成）。
- `src/agent/sandbox/` 已实现 3.1-3.6 完整沙箱层（连接/镜像/容器/安全/执行/文件/预热池）。
- `src/agent/tools/` 已实现 `sandbox_exec`、`file_read`、`file_write`、`file_list`、`file_edit`、`finish`。
- `ExecutionContext` 已接入工具签名（TD-004 已修复）：`ToolRegistry` 在 `register()` 时探测 handler 是否声明 `execution_context` 参数并缓存，`execute()` 时在调用方未显式传入时注入；Agent session 级持有，`reset()` 清空。
- `config.sandbox.backend` 支持 `"docker" / "subprocess"` 并已生效（TD-002/TD-003 已修复）：`subprocess` 为本地子进程轻量 fallback，无 Docker 时可跑通写→读→改→运行闭环；未知 backend 值警告回退 `subprocess`。
- Docker 后端已实现文件跨调用持久化：每个 `DockerSandboxBackend` 实例会创建命名 volume 挂载到 `/workspace`，`file_write` → `file_read` / `sandbox_exec` 可共享文件；`/tmp` 仍保持临时语义。
- Docker Hub 镜像拉取依赖网络环境：部分环境（如当前开发机）因代理/防火墙/IPv6 问题无法直接拉取 `python:3.11-slim`；`scripts/setup-docker.py` 已输出排查建议，但长期需要支持镜像源配置或自动 fallback 机制。

---

## 9. 开发边界与约定

- **注释语言**：中文（按 `docs/session-context.md` 要求）。
- **TDD**：先写失败测试，再写实现。
- **Commit 格式**：`type: description`，如 `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`, `chore: ...`
- **质量门禁**：pytest + mypy + ruff 全部通过方可提交。
- **当前任务**：Phase 10 已完成。下一步由用户决定：功能增强、架构优化、面试整理或真实 LLM 联调。已完成规格见 `.kimi/vibe_specs/demo-spec.md`。

---

## 10. 清理记录

2026-07-02 本次会话清理了以下无用文件/目录：

- 临时输出文件：`_diag.py`, `_env_check.txt`, `_git_cmt.txt`, `_git_cmt2.txt`, `_git_cmt3.txt`, `_git_stat.txt`, `_mypy.txt`, `_pwd_test.txt`, `_ruff.txt`, `_select_test.txt`, `_t_all.txt`, `_t_eh1.txt`, `_t_full.txt`, `_test_eh.txt`, `_test_result.txt`, `_wsl_install.txt`, `_wsl_ver.txt`
- 生成/缓存目录：`.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `src/agent.egg-info/`, 所有 `__pycache__/`
- 索引中已删除但未提交的文件：`_fetch.py`
