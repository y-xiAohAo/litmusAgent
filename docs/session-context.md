## 当前任务状态

- **已完成**：Phase 4.7 —— `file_write` / `file_edit` Tools，补齐文件写/编辑能力
- **已完成**：Phase 9 安全策略引擎全部完成（9.1~9.7）；Phase 10.1 CLI 入口完成；Phase 10.2 Rich 美化输出；Phase 10.3 交互模式；Phase 10.4 示例场景脚本；Phase 10.5 Docker 一键启动；Phase 10.6 README 重写
- **已完成**：Phase 10.8 —— 使用文档（usage.md / configuration.md）
- **已完成**：Phase 10.9 —— Demo 脚本与录制准备（demo_real_llm.py / test_demo.py / demo.md）
- **已完成**：评测日志体系（evaluation-log.md / evaluation-spec.md / test_evaluation_log.py）
- **质量门禁**：`pytest tests/` + `mypy src/` + `ruff check src/ tests/` 全绿
- **测试基线**：786 passed，1 skipped（跳过项为 tiktoken 未安装）
- **Git 状态**：`master` 分支，有未提交修改（评测日志体系）
- **当前任务**：记忆存储升级完成（SQL 后端契约双后端 22 项全绿 + Redis 缓存 generation 失效；真实 MySQL/Redis 容器验收 + b6 子集 mem-sql 端到端 PASS）；下一步候选：简历"存储与缓存工程"bullet 并入（R3）、Batch 7（T73 显著性/提取审计）、TD-010
- **当前规格**：`mydocs/specs/2026-08-04_09-30_memory-sql-redis.md`（SDD-RIPER-ONE）

---

## 评测日志体系完成摘要

新增评测日志体系，质量门禁全部通过：

- `pytest tests/`：**516 passed, 1 skipped**
- `mypy src/`：38 source files 零错误
- `ruff check src/ tests/`：全绿

### 修改文件

- `docs/evaluation-log.md`：项目基线、测试环境、端到端测试结果、Bug 清单、优化记录、Action Items。
- `.kimi/vibe_specs/evaluation-spec.md`：评测日志的规格与跨会话维护规则。
- `tests/test_evaluation_log.py`：7 个结构测试，防止日志文档腐烂。

### 关键设计决策

- **文档即资产**：把测试、Bug、优化记录集中在一处，避免散落在聊天记录或临时文件中。
- **可量化**：每次优化必须记录前后指标，形成可追溯的量化证据。
- **跨会话可读**：新 session 启动时按顺序阅读 `progress-spec` → `session-context` → `evaluation-log` → `CODEMAP`。
- **防腐烂**：用测试强制关键章节存在。

## Phase 4.7 完成摘要

Phase 4.7 已完整交付：

- `pytest tests/`：**532 passed, 1 skipped**
- `src/agent/tools/file_write.py`、`src/agent/tools/file_edit.py` 已创建。
- `file_write` / `file_edit` 已注册到默认工具集，并接入 `file/path` write 安全策略。

### 修改文件

- `src/agent/tools/file_write.py`：新增文件写入工具。
- `src/agent/tools/file_edit.py`：新增基于 `old_string` / `new_string` 的精确文件编辑工具。
- `src/agent/tools/__init__.py`：注册新工具。
- `src/agent/core/engine.py`：增加 `file_write` / `file_edit` 的参数级策略检查映射。
- `src/agent/core/default_security_rules.yaml`：补充敏感路径 write 拒绝规则。
- `src/agent/core/tool_router.py`：更新工具使用指导。
- `tests/test_tools.py`：新增 8 个测试场景。
- `tests/test_tool_security.py`：新增 2 个策略拒绝测试。
- `docs/configuration.md`：更新工具列表与配置示例。

### 关键设计决策

- **唯一匹配语义**：`file_edit` 要求 `old_string` 在目标文件中唯一出现，防止歧义替换。
- **复用后端能力**：工具层只做读取/替换/写回，文件注入/提取仍由 `DockerSandboxBackend` 负责。
- **写操作也走策略**：`file_write` / `file_edit` 与读取工具共享 `file/path` 资源，通过 `write` operation 做权限控制。
- **当前规格**：`.kimi/vibe_specs/technical-debt-spec.md`（技术债清单）

## Phase 10.9 完成摘要

Phase 10.9 已完整交付：

- `pytest tests/`：**509 passed, 1 skipped**
- `examples/demo_real_llm.py`、`tests/test_demo.py`、`docs/demo.md` 已创建。

### 修改文件

- `examples/demo_real_llm.py`：新增真实 LLM 端到端演示脚本，支持 `--prompt` / `--config` / `--model` / `--echo`，无 Key 时打印友好提示。
- `tests/test_demo.py`：新增 3 个测试，覆盖 `--help`、`--echo` 模式与无 Key 提示。
- `docs/demo.md`：新增 Demo 运行指南，说明真实 LLM 与 `--echo` 两种用法、预期输出和常见问题。
- `.kimi/vibe_specs/demo-spec.md`：Phase 10.9 规格文件。

### 关键设计决策

- **今天就能跑，明天配 Key 后自动升级**：脚本在无 Key 时通过 `--echo` 或可运行的提示保持可测试；明天你提供 `OPENAI_API_KEY` 后，同一脚本直接调用真实 LLM。
- **不引入新依赖**：复用已有的 `Agent`、`OpenAIClient.from_env()`、`load_config()`。
- **真实 LLM 是展示核心**：Demo 默认使用真实 LLM，只有这样才能验证 tool call 质量与自我纠正能力。
- **测试不依赖外部服务**：`--help`、`--echo`、无 Key 提示三个路径均可离线验证。

## Phase 10.8 完成摘要（供参考）

Phase 10.8 已完整交付：

- `pytest tests/`：**506 passed, 1 skipped**
- `docs/usage.md`、`docs/configuration.md`：新增中文使用与配置文档。
- `tests/test_usage_docs.py`：新增 10 个测试。

### 关键设计决策

- 文档与代码同步，所有示例均使用当前实际 API。
- 无 API Key 也可验证，示例优先展示 `--echo` / `EchoClient`。
- 诚实记录 `subprocess` 后端未真正实现的技术债。

## Phase 10.7 完成摘要（供参考）

Phase 10.7 已完整交付：

- `pytest tests/`：**496 passed, 1 skipped**
- `docs/architecture.md`：全面重写为中文，新增 4 张 ASCII 图。
- `tests/test_architecture.py`：新增 5 个测试。

### 关键设计决策

- 用 ASCII 而非 Mermaid：避免引入新依赖，兼容所有 Markdown 渲染环境。
- 图的宽度控制在 80 字符以内，便于在终端和窄屏设备上查看。

---

## Phase 10.4 / 10.5 / 10.6 完成摘要（供参考）

- **Phase 10.4**：新增 3 个示例脚本 + `examples/config.yaml` + `tests/test_examples.py`。
- **Phase 10.5**：新增 `scripts/setup-docker.py` + `docker-compose.yml` + `tests/test_docker_launch.py`。
- **Phase 10.6**：重写 `README.md` + `tests/test_readme.py`。
- **已知阻塞**：当前开发机无法直接连接 Docker Hub 拉取 `python:3.11-slim`（代理/网络问题），未来需要支持镜像源配置或 subprocess 后端 fallback。

---

## Phase 10 已完成

Phase 10 全部 9 个 Task（10.1 - 10.9）均已交付。后续可选方向：

1. **功能增强**：完善 `subprocess` 沙箱后端、镜像源配置、流式输出等。
2. **架构优化**：将 `ExecutionContext` 真正接入工具签名。
3. **面试准备**：整理项目亮点、准备口述介绍、优化 README 首页。
4. **真实 LLM 联调**：已使用 DeepSeek API Key 成功运行 `python examples/demo_real_llm.py`，5 轮完成 fibonacci 任务；待 Docker 镜像就绪后验证真实沙箱执行。

### 当前决策

- 保持核心引擎稳定，不再扩展新 Phase。
- 所有已知技术债已记录在 `CODEMAP.md` 中。

### 严禁做

- 不在没有明确需求的情况下重构核心循环。
- 不引入新依赖。
- 不为了面试添加过度复杂的演示脚本。

---

## 项目结构速查

```
D:\djh\hermes\project1
├── src/agent/
│   ├── cli/                 # Phase 8.4 记忆 CLI + Phase 10 Agent CLI
│   ├── config.py            # 配置系统（含 SecurityConfig）
│   ├── core/
│   │   ├── engine.py        # Agent + ToolRegistry（含策略拦截）
│   │   ├── memory.py        # 记忆系统（读写策略接入点）
│   │   ├── security.py      # 策略引擎
│   │   ├── default_security_rules.yaml  # 默认规则集
│   │   └── ...
│   ├── sandbox/
│   │   └── docker_backend.py # Docker 沙箱
│   └── tools/
│       ├── sandbox_exec.py   # 代码执行
│       ├── file_read.py      # 文件读取
│       ├── file_write.py     # 文件写入
│       ├── file_list.py      # 文件列表
│       ├── file_edit.py      # 文件编辑
│       └── ...
├── examples/                 # Phase 10.4 示例脚本
├── scripts/                  # Phase 10.5 Docker 一键启动 + 其他脚本
├── docker-compose.yml        # Phase 10.5 Docker Compose 配置
├── README.md                 # Phase 10.6 重写后的项目入口文档
├── docs/
│   ├── architecture.md        # Phase 10.7 ASCII 架构图
│   ├── usage.md               # Phase 10.8 使用指南
│   ├── configuration.md       # Phase 10.8 配置参考
│   ├── demo.md                # Phase 10.9 Demo 指南
│   ├── evaluation-log.md      # 评测结果、Bug、优化记录
│   ├── plans/
│   ├── session-context.md     # 本文件
│   └── progress-spec.md       # 进度总览
├── tests/
│   ├── test_architecture.py   # Phase 10.7 架构文档验证
│   ├── test_usage_docs.py     # Phase 10.8 使用与配置文档验证
│   ├── test_demo.py           # Phase 10.9 Demo 脚本验证
│   ├── test_evaluation_log.py # 评测日志结构验证
│   ├── test_readme.py         # Phase 10.6 README 验证
│   ├── test_examples.py       # Phase 10.4 示例验证
│   ├── test_docker_launch.py  # Phase 10.5 Docker 启动脚本测试
│   └── ...
└── ...
```

---

## 恢复开发状态

```bash
cd /d/djh/hermes/project1
python -m pytest tests/ -q       # 确认 516 passed, 1 skipped
python -m mypy src/              # 确认无类型错误
python -m ruff check src/ tests/ # 确认 lint 通过
```

---

## 参考

- Phase 9 详细计划：`docs/plans/phase-9-plan.md`
- Phase 8.4 计划：`docs/plans/phase-8.4-plan.md`
- Phase 8.4 评审报告：`docs/reviews/peer-review-phase-8.4.md`
- 完整阶段计划：`docs/plans/2026-04-28-code-sandbox-agent.md`
- 代码地图：`CODEMAP.md`
- Phase 10.9 / 评测日志规格：`.kimi/vibe_specs/evaluation-spec.md`
