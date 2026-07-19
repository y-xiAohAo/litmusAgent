# 评测日志（Evaluation Log）

> **本文件是 Litmus Agent 项目的“实验记录本”。**
>
> 用途：
> 1. 记录每次真实 LLM 端到端测试的结果。
> 2. 记录 Bug 发现、根因分析与修复状态。
> 3. 记录优化前后的量化指标，形成可追溯的量化证据。
>
> 维护规则见 `.kimi/vibe_specs/evaluation-spec.md`。

---

## 项目基线

| 项 | 当前值 | 备注 |
|---|---|---|
| 测试总数 | 679 passed, 1 skipped | 跳过项为 `tiktoken` 未安装 |
| 类型检查 | `mypy src/` 零错误 | 46 source files（2026-07-19 复测；web 模块后增 2 文件） |
| Lint | `ruff check src/ tests/` 全绿 | — |
| 覆盖率 | `pytest --cov=src/agent` **91%**（3136 语句，272 未覆盖） | 首次测量 2026-07-18 |
| 当前 LLM 支持 | OpenAI 兼容端点 | 已验证 DeepSeek |
| 沙箱后端 | Docker + Subprocess 双后端 | TD-002/TD-003 已修复：`config.sandbox.backend` 生效，未知值警告回退 subprocess；完整技术债清单见 `.kimi/vibe_specs/technical-debt-spec.md` |
| 已知阻塞 | Docker Hub 拉取受限（TD-007） | 部分网络环境无法直接拉取 `python:3.11-slim`；已有 subprocess fallback 兑底 |

---

## 测试环境

| 环境项 | 值 |
|---|---|
| OS | Windows 10/11 |
| Python | 3.11.9 |
| 虚拟环境 | `C:\Users\msn\AppData\Local\hermes\hermes-agent\venv\` |
| 当前模型 | `deepseek-chat` |
| Base URL | `https://api.deepseek.com/v1` |
| Docker daemon | 当前环境可达，但无法连接 Docker Hub |

---

## 端到端测试结果

| 日期 | 场景 | 模型 | 轮数 | 结果 | 耗时 | 关键问题 |
|---|---|---|---|---|---|---|
| 2026-07-15 | 编写并验证 `fibonacci(n)` | deepseek-chat | 5 | 成功 | ~12s | 初始脚本忽略 `OPENAI_BASE_URL` / `OPENAI_MODEL`，已修复（已被 2026-07-18 S1 复跑覆盖并验证） |
| 2026-07-18 | S1 fibonacci 编写+验证（Docker 真实沙箱复跑） | deepseek-chat (v4-flash) | 3 | ✅ 成功 | 8.2s | file_write→sandbox_exec→finish；沙箱输出含 55；**覆盖 7/15 存疑记录** |
| 2026-07-18 | S2 CSV 文件工作流 | deepseek-chat | 1 | ❌ FAIL | 5.5s | LLM 用 sandbox_exec 一把梭，跳过 file_write/file_read（重跑行为稳定） |（修复 EVAL-010 后重跑：权限错误消除，剩余 FAIL 为 LLM 工具偏好）
| 2026-07-18 | S3 numpy 自愈（禁网） | deepseek-chat | 5 | ✅ 成功 | 23.1s | 禁网下 pip 不可用时 Agent 成功降级完成任务 |
| 2026-07-18 | S4 多工具链+file_edit | deepseek-chat | 3 | ❌ FAIL | 11.4s | 稳定跳过 file_edit（重跑 2 轮仍跳过），改用 sandbox_exec 改文件 |
| 2026-07-18 | S5 策略拦截（写 /etc） | deepseek-chat | 4 | ✅ 成功 | 9.7s | TD-006 边界真实生效：策略拒绝→Agent 换方案并说明 |
| 2026-07-18 | S1-sub 对照（subprocess 后端） | deepseek-chat | 8 | ✅ 成功 | 12.0s | fallback 等价性验证通过；工具使用更丰富（file_list/file_read） |
| 2026-07-18 | S3b 对照（预置 numpy 镜像） | deepseek-chat | 3 | ✅ 成功 | 8.5s | 模式 1 预置镜像验证：numpy 直接可用，比 S3 快 63% |
| 2026-07-18 | S4p 对照（S4 + TaskPlan 分步推进） | deepseek-chat | 3 runs | ✅ 3/3 | ~10s/run | **框架补偿模型弱点实证**：file_edit 3/3、标题正确 3/3、计划步骤 12/12；对照无 Planner 的 S4 为 0/8 |
| 2026-07-18 | S4-auto（自动规划，无手工计划） | deepseek-chat | 2 runs | ✅ 2/2 | ~10s/run | **自动规划端到端验证**：LLM 自生成 5-6 步计划，file_edit 2/2、标题正确 2/2；达到手工计划同等效果 |
| 2026-07-18 | S6 记忆叙事（修复后复验） | deepseek-chat | 2 runs | ✅ 2/2 | ~20s/run | **分层检索修复实证**：路径级 2/2 + 内容级 2/2（修复前 0/2）；L0 recency 兜底 + 内容快照注入生效 |
| 2026-07-18 | memory_search 真实行为复验 | deepseek-chat | 1 run | ✅ | ~20s | **search-then-read 模式生效**：LLM 自然使用 memory_search（自然语言 query）→ memory_read（正确 URI）→ 答出代号；零 URI 猜测错误 |
| 2026-07-18 | S9 人工确认（批准 y） | deepseek-chat | 2 | ✅ 成功 | 5.2s | **TD-008 真实验证**：批准后 file_write 真实执行（补全交付后的联调缺口） |
| 2026-07-18 | S9b 人工确认（拒绝 n） | deepseek-chat | 2 | ✅ 成功 | 3.8s | 拒绝后工具被拦截，Agent 收到"用户拒绝"文案并换方案说明 |
| 2026-07-18 | S10 沙箱代码安全扫描 | deepseek-chat | 3 | ✅ 成功 | 10.1s | import os 被策略拒绝，Agent 换安全方式完成（sandbox/code 规则真实生效） |
| 2026-07-18 | S11 context_read 外迁读回 | deepseek-chat | 3 | ✅ 成功 | 11.7s | 大输出外迁后 LLM 真实使用 context_read 读回缓存并答出第 38 行内容 |
| 2026-07-18 | S12 LLM 摘要器压缩 | deepseek-chat | 4 | ✅ 成功 | 9.4s | LLMSummarizer 路径：压缩后暗号'夜航西飞'正确回忆 |
| 2026-07-18 | Web UI 端点真实联调 | deepseek-chat | 2 轮 | ✅ 成功 | ~10s | 修复 EVAL-011 后：sandbox_exec 工具事件 + 多轮上下文（42→50）全部正确 |
| 2026-07-18 | CLI chat 多轮真实联调 | deepseek-chat | 2 轮 | ✅ 成功 | ~8s | 修复 EVAL-012/013 后：多轮上下文保持（falcon-9），环境变量优先级与事件循环复用生效 |
| 2026-07-19 | 反思层 A/B 实验 v3（EVAL-014 修复后） | deepseek-chat | 5v5 对照 | ✅ 有效 | — | **反思开启：轮数 5.0 / 失败 8.6 / 反思事件 33；反思关闭：轮数 7.4 / 失败 11.6 / 0——无效调用 -26%、轮数 -32%** |
| 2026-07-19 | 反思层 A/B 实验 v1/v2/v3初跑 | deepseek-chat | 3 组 | ⚠️ 无效数据 | — | 反思零触发（模型降权快/战术多变/错误文案不含异常名）→ 暴露 EVAL-014 |

### 详细说明

**任务**：

```text
请编写一个 Python 函数 fibonacci(n)，在沙箱中验证它对于 n=10 返回 55，然后返回该函数的源码。
```

**观察**：

- DeepSeek 模型正确生成了迭代版 `fibonacci` 函数。
- Agent 在 5 轮内完成任务并返回最终答案。
- 当前环境 Docker Hub 连接受限，沙箱镜像未就绪；函数是否真正在沙箱中执行尚需后续验证。

---

## Bug 与问题清单

| ID | 问题 | 严重度 | 根因 | 修复 | 状态 |
|---|---|---|---|---|---|
| EVAL-001 | `demo_real_llm.py` 忽略 `OPENAI_BASE_URL` / `OPENAI_MODEL` 环境变量 | 高 | 脚本直接用 `config.llm.base_url` / `config.llm.model` 覆盖了 `OpenAIClient.from_env()` 的环境变量读取逻辑 | 改为 CLI 参数 > 环境变量 > 配置文件 > 默认值 | ✅ 已修复 |
| EVAL-002 | Docker Hub 无法拉取镜像 | 中 | 当前环境代理/网络限制 | `image_registry` 配置化（TD-007）+ 实测 daocloud 镜像源可用 | ✅ 已修复（2026-07-18） |
| EVAL-003 | `subprocess` 沙箱后端未真正实现 | 中 | Phase 4 只实现了 `DockerSandboxBackend` | 实现 `SubprocessSandboxBackend` 并接入配置 | ✅ 已修复（2026-07-17） |
| EVAL-004 | Docker 后端文件跨轮持久性 | 高 | `execute_code` / `put_file` 每次从池中取新容器并销毁，文件无法跨调用保留 | 改为每个 backend 实例挂载共享 workspace volume 到 `/workspace` | ✅ 已修复 |
| EVAL-005 | `config.sandbox.backend` 被忽略 | 低 | `Agent.__init__` 始终创建 `DockerSandboxBackend` | 根据配置构造对应后端 | ✅ 已修复（2026-07-17） |
| EVAL-006 | `ExecutionContext` 已实现但未接入工具 | 中 | 当前 `ToolRegistry` 只向 handler 传递固定参数 | 改造工具签名/注册机制，注入 ExecutionContext | ⏳ 待解决 |
| EVAL-007 | 内部工具依赖闭包注入，`Agent.__init__` 成为依赖装配中心 | 中 | `context_read` / `memory_read` 通过闭包注入各自运行时依赖 | 引入通用运行时上下文注入机制或轻量 DI | ⏳ 待解决 |
| EVAL-008 | 文件写操作 workspace 提示 | 中 | 默认 `file/path` write 规则只拒绝敏感路径，未限定允许范围 | 路由提示引导 + TD-006 显式边界：默认仅允许写 `/workspace`（可配置），拒绝 `..` 逃逸 | ✅ 已修复（2026-07-17） |
| EVAL-009 | docker-py 7.x 不支持 `exec_run(timeout=)`，真实 Docker 后端 execute_code 全部失败 | 高 | 测试全部 mock Docker SDK，错误契约被测试固化（3 个用例断言 timeout 传入 exec_run） | 移除该参数，超时改由 `asyncio.wait_for` 外层强制；修正 3 个测试契约并新增超时强制用例 | ✅ 已修复（2026-07-18） |
| EVAL-010 | workspace volume root 属主与容器 nobody 用户冲突，沙箱代码无法写 /workspace | 高 | TD-001 引入 volume 时叠加 Phase 3.4 安全限制产生权限不对称；TD-001 开发期 Docker 不可用无法真实验证，mock 无法表达 uid/gid 语义 | 容器创建后 chown 65534 + put_file tar 条目带 nobody uid/gid | ✅ 已修复（2026-07-18） |
| EVAL-011 | Web UI 忽略 OPENAI_BASE_URL/OPENAI_MODEL 环境变量，始终请求 api.openai.com | 高 | `_create_agent` 把 config 默认值显式传给 from_env，屏蔽环境变量（EVAL-001 同类） | model/base_url 改环境变量优先 | ✅ 已修复（2026-07-18） |
| EVAL-012 | CLI run/chat 同样忽略 OPENAI_* 环境变量 | 高 | `_load_config` 无环境变量层，`_build_llm_client` 显式传 config 默认值 | 优先级改为 CLI 旗标 > 环境变量 > 配置文件 > 默认值 | ✅ 已修复（2026-07-18） |
| EVAL-013 | CLI chat 第二轮起报 "Event loop is closed" | 高 | `run_chat_loop` 每轮 `asyncio.run()` 创建并关闭新循环，httpx client 绑定在首个循环上 | 整个对话循环复用单一事件循环 | ✅ 已修复（2026-07-18） |
| EVAL-014 | 反思链路对非异常文本类工具失败静默失效（零触发） | 高 | `file_read` 等工具失败文案为纯中文（"文件不存在"），`_classify_tool_error` 要求文本含异常类名（\w+Error），导致分类→账本→反思全链断裂 | 工具错误文本附带异常类名前缀（FileNotFoundError/OSError） | ✅ 已修复（2026-07-19） |

---

## 优化记录

| 日期 | 模块 | 优化前 | 优化后 | 提升 | 摘要 |
|---|---|---|---|---|---|
| 2026-07-19 | `tools/file_*.py` + 反思链路（EVAL-014） | 反思式错误恢复机制对文件类工具失败完全静默（679 测试全绿下零触发） | 工具错误文本附带异常类名，反思链路恢复可触发 | 反思机制效果首次量化：无效失败调用 -26%、任务轮数 -32%（5v5 对照） | **S**：需要验证反思层价值。**T**：A/B 对照实验。**A**：实验暴露链路断裂（错误文案缺异常名），修复后重跑。**R**：获得量化证据，实验本身成为缺陷发现工具。 |
| 2026-07-18 | `web/app.py` + `cli/agent_cli.py` + `cli/chat.py`（EVAL-011/012/013 修复） | Web/CLI 两个入口忽略 OPENAI_* 环境变量（始终请求 api.openai.com）；CLI chat 第二轮起事件循环崩溃 | 环境变量优先级修正（CLI 旗标 > env > 配置 > 默认）+ 对话循环复用单一事件循环 | Web 与 CLI 两个入口的真实联调全部打通 | **S**：真实联调发现 Web/CLI 入口在自定义端点下全部不可用。**T**：修复三个入口级 bug。**A**：诊断定位 from_env 参数覆盖链与 asyncio.run 循环复用问题，逐个修复并真实复验。**R**：新增 5 个测试，679 passed；Web 端点与 CLI 多轮真实验证通过。 |
| 2026-07-18 | `core/memory.py` + `tools/memory_search.py`（memory_search 工具） | memory_read 需精确 URI，LLM 只能猜（实测猜错率 100%），记忆详情对 LLM 实质不可达 | 新增 memory_search 工具：自然语言搜索返回结构化候选（id/summary/preview/uri），复用分层检索后端 | LLM 交互从"拼 URI"转为 search-then-read，真实复验零猜测错误 | **S**：URI 可发现性是召回链短板。**T**：让 LLM 按语义发现记忆。**A**：系统化新增搜索工具而非修补 URI，search() 复用 L1/L2/L0 检索。**R**：新增 8 个测试，672 passed；实测 LLM 自然形成 search→read 链路。 |
| 2026-07-18 | `core/memory.py`（记忆分层检索修复） | 中文自然语言查询下记忆检索零命中（字面重叠为 0），Agent 跨会话"失忆"；artifact 只存路径无法回答内容级问题 | L0 recency 兜底（默认开）+ L2 条件 LLM 语义重排（默认关）+ artifact 内容快照注入；新增 `inject_async` 分层入口 | 记忆召回从 0/2 → 2/2（路径级+内容级）；L2 可配置升级 | **S**：联调发现记忆系统存得住取不出。**T**：修复检索召回链。**A**：审计定位三层缺陷，L0/L2/快照三层修复，真实复验对照。**R**：新增 11 个测试，664 passed；S6 内容级回忆 2/2。 |
| 2026-07-18 | `engine.py` + `config.py`（Auto-Planner） | 多步任务需外部手工构造 TaskPlan 才能获得分步推进能力，裸 run() 下模型丢步骤（S4 基线 0/8） | PlannerConfig（默认关）+ run() 自动 LLM 规划 + 宽容解析 + 三层降级 + CLI --plan 旗标 | 多步任务零手工成本获得 Planner 增益；实测 file_edit 0/8 → 2/2 | **S**：S4p 实验证明 Planner 有效但需手工构造计划。**T**：让规划能力默认可得。**A**：run() 前自动 LLM 分解任务为 TaskPlan，失败静默降级。**R**：新增 12 个测试，649 passed；真实验证达到手工计划同等效果。 |
| 2026-07-18 | `docker_backend.py`（EVAL-010 修复） | 工具能写 /workspace 但沙箱内代码写不进（root 属主 volume + nobody 容器用户），S2 联调暴露 PermissionError | 容器创建后 root chown 65534 + put_file tar 条目 uid/gid=65534，权限语义对齐 | 沙箱代码写 workspace 与覆盖工具文件均可用；S2 剩余 FAIL 仅剩 LLM 工具偏好问题 | **S**：真实联调暴露工具与代码的写权限不对称。**T**：让代码与工具对 workspace 权限一致。**A**：溯源定位 TD-001 引入点，chown + tar uid/gid 双修复，真实 Docker 回归验证。**R**：635 passed；S2 失败模式从权限错误转为纯工具偏好。 |
| 2026-07-18 | `config.py` + `docker_backend.py`（TD-007） | Docker Hub 不可达时 ensure_image 拉取必败，用户只能手工打标或改 daemon 配置 | `SandboxConfig.image_registry` 配置化：官方镜像自动补 library/ 前缀、拉取后打标回原名、本地有镜像跳过拉取、工厂全参透传 | 项目自带镜像源能力，技术债 9/9 清零 | **S**：受限网络下 Docker 沙箱无法自助恢复。**T**：镜像源可配置且零手工步骤。**A**：_resolve_pull_image 解析 + 拉后打标 + 工厂透传。**R**：新增 9 个测试，625 passed；删 tag 真实重拉验证通过，execute_code 实测可用。 |
| 2026-07-18 | `src/agent/sandbox/docker_backend.py`（EVAL-009 修复） | docker-py 7.x 下 `exec_run(timeout=)` 抛 TypeError，真实 Docker 沙箱 execute_code 100% 失败；mock 测试把错误契约固化 | 超时控制移至 `asyncio.wait_for` 外层；修正 3 个错误契约测试并新增 1 个超时强制测试 | 真实 Docker 后端首次端到端可用：执行/超时/错误回传/workspace 持久全通 | **S**：真实环境验证发现沙箱执行全挂，mock 全绿形成假安全。**T**：修复 docker-py 兼容性并让超时真实生效。**A**：wait_for 外层强制超时 + 测试契约纠正。**R**：616 passed；真实后端 4 项行为抽查全过。 |
| 2026-07-18 | `engine.py` + `cli/chat.py` + `config.py`（TD-008） | file_write/file_edit 静默修改沙箱文件，用户无法在应用前 review | HumanApprovalConfig + ToolRegistry 确认钩子 + CLI y/n/a 交互（a=本会话免确认）+ `--approve` 旗标 | 写操作可选人工把关，未启用时零行为变化 | **S**：Coding Agent 的写操作静默生效，缺乏人工把关。**T**：提供可选确认钩子且不破坏自动化体验。**A**：复用 TD-004 注入模式在 registry 统一入口加确认钩子；CLI 三选语义；旗标优先于配置。**R**：新增 11 个测试，全量 615 passed；Web UI per-call 确认按 Non-Goal 留待后续单元。 |
| 2026-07-18 | `src/agent/tools/sandbox_exec.py`（FAST：pip 提取增强） | pip 记录启发式仅覆盖行级 `pip install`，真实 subprocess 风格安装（`subprocess.run([sys.executable, '-m', 'pip', ...])`）追踪不到 | 支持行级 / subprocess 列表 / os.system 字符串三种形态 + 包名归一化（去版本钉/extras、过滤选项） | TD-004 评审观察项关闭，真实场景 pip 追踪可用 | **S**：评审发现 pip 记录在真实场景不触发。**T**：覆盖主流 pip 调用形态。**A**：三形态正则 + 归一化函数，保持成功执行才记录的门禁。**R**：新增 6 个测试，全量 604 passed。 |
| 2026-07-18 | `src/agent/core/runtime.py` + `engine.py`（TD-005） | 内部工具依赖（ContextCache/MemoryManager）在 `Agent.__init__` 逐个创建并闭包注入，新增内部工具必须改核心引擎（装配区 ~90 行） | 新增 `RuntimeServices` 三槽位 dataclass + `from_config()` 工厂 + `register_internal_tools()` 统一注册；Agent 装配区收敛为 4 行，4 个私有方法移除 | 新增内部工具零引擎改动；注册函数签名不变，涟漪面仅 2 文件 | **S**：内部工具闭包注入使 `Agent.__init__` 成为依赖装配中心，扩展性差。**T**：解耦内部工具装配，新增工具不改引擎。**A**：引入 RuntimeServices 统一持有依赖并迁入创建逻辑；保留属性委托与注册函数签名实现零涟漪。**R**：新增 9 个测试，全量 598 passed、mypy 45 文件零错误；记忆/压缩/安全集成测试零回归。 |
| 2026-07-17 | `src/agent/core/engine.py` + `tools/sandbox_exec.py`（TD-004） | `ExecutionContext` 已实现但从未接入：工具 handler 只能收到 LLM 传入的固定参数，无法跨 tool call 共享运行时状态 | `ToolRegistry` 在 register 时探测 handler 签名并缓存，execute 时条件注入 `execution_context`；Agent session 级持有、reset() 清空；sandbox_exec 增加 pip 包记录示例 | 有状态工具接入成本归零；为 TD-005/TD-008 奠定注入点 | **S**：Agent 需要维护"已安装包"等跨调用运行时状态，但工具拿不到上下文。**T**：让工具 handler 可选接收 ExecutionContext 且向后兼容。**A**：注册时签名探测缓存（热路径 O(1) 查找）、arguments 未提供才注入的冲突规则、session 级生命周期与 reset() 清空语义。**R**：新增 14 个测试（含主循环跨调用集成），全量 589 passed、mypy/ruff 全绿；未声明参数的工具零变化。 |---|
| 2026-07-17 | `src/agent/core/default_security_rules.yaml` + `config.py`（TD-006） | `file/path` write 只拒绝敏感路径，其余路径（如 `/tmp`）默认放行；`..` 逃逸路径无防护 | 新增边界三件套规则（deny `..` @95 / allow `/workspace` @50 / deny catch-all @1）+ `security.workspace_path` 配置与覆盖规则注入 | 写操作默认限制在 workspace 内，边界可配置迁移 | **S**：LLM 驱动的 Coding Agent 可静默写任意沙箱路径，默认策略只拦敏感文件。**T**：为写操作建立默认 workspace 边界且可配置。**A**：利用 PolicyEngine 优先级首命中语义，以纯规则表达边界（零引擎改动）；`build_policy_engine` 在非默认 workspace 时追加 allow-60/deny-55 覆盖规则。**R**：新增 9 个测试，全量 575 passed；`/tmp` 与 `..` 逃逸默认拒绝，敏感路径优先级不受影响，策略未启用时行为零变化。 |
| 2026-07-17 | `src/agent/sandbox/`（TD-002+TD-003） | 仅 Docker 后端；Docker 不可用时 Agent 完全无法执行代码；`config.sandbox.backend` 配置被忽略 | 新增 `SubprocessSandboxBackend`（临时目录 workspace、POSIX 路径映射、防 `../` 逃逸、async 子进程）；新增 `SandboxBackend` Protocol 抽象与 `create_sandbox_backend` 工厂 | 无 Docker 环境可跑通写→读→改→运行闭环；配置驱动后端选择 | **S**：开发机无法连接 Docker Hub，Docker 沙箱不可用，Coding Agent 闭环断裂。**T**：在无 Docker 环境下恢复「写代码→改代码→运行验证」最小闭环。**A**：引入 Protocol 结构化抽象（`SandboxBackend`）避免绑死 Docker 类型；实现子进程后端与后端工厂；为 `file_list` 增加可选 `list_dir` 能力修复路径映射旁路。**R**：新增 25 个测试（真实子进程执行、无 Docker 依赖），全量 566 passed、mypy 44 文件零错误、ruff 全绿；配置 `backend: subprocess` 即插即用。 |
| 2026-07-16 | `src/agent/sandbox/docker_backend.py`（TD-001） | `execute_code`/`put_file` 每次从预热池取新容器并销毁，文件无法跨调用保留 | 每个 backend 实例创建命名 Docker volume 挂载 `/workspace`，池化容器共享工作区，关闭时清理 | 同一 Agent 会话内形成连续可写工作区 | **S**：Coding Agent 需要跨工具连续操作同一批文件，但容器池化导致文件随容器销毁。**T**：让文件在同一 backend 实例生命周期内持久可见。**A**：引入命名 volume 挂载 `/workspace`，保持 public API 与安全限制不变。**R**：重写并新增 9 个沙箱测试，`test_sandbox.py` 61 passed，全量 541 passed。 |
| 2026-07-15 | `examples/demo_real_llm.py` | 无法使用 DeepSeek 等第三方端点（base_url/model 被 config 默认值锁定） | 支持 `--base-url` / `--model` 参数，并正确优先读取环境变量 | 可切换任意 OpenAI 兼容端点 | **S**：需要在无 OpenAI 访问权限的环境下演示 Agent。**T**：让 Demo 脚本支持 DeepSeek 等兼容端点。**A**：调整参数优先级为 CLI > 环境变量 > 配置 > 默认值。**R**：成功在 DeepSeek 上跑通端到端 fibonacci 任务，耗时约 12 秒，5 轮完成。 |

---

## 下一步 Action Items

- [x] 修复 Docker 后端文件跨轮持久性问题，确保 `file_write` / `file_edit` / `file_read` / `sandbox_exec` 可共享工作区（`TD-001` ✅）。
- [x] 实现 `subprocess` 后端，并让 `config.sandbox.backend` 真正生效，作为 Docker 不可用时的 fallback（`TD-002`/`TD-003` ✅，2026-07-17）。
- [ ] 解决 Docker Hub 拉取问题（配置镜像源或预置本地镜像，`TD-007`），确保 Docker 沙箱能真正执行代码。
- [x] 在真实沙箱执行条件下重新跑端到端场景（2026-07-18 E2E Suite：S1-S5 + 双对照，5/7 PASS），记录真实 tool 执行成功率。
- [ ] 将 `ExecutionContext` 接入工具签名，支持跨 tool call 共享运行时状态。
- [ ] 重构内部工具（`context_read` / `memory_read`）的注入方式，避免 `Agent.__init__` 过度膨胀。
- [ ] 为 `file/path` write 增加 workspace 边界限制，提升默认安全性。
- [x] 验证框架补偿能力：S4p 实验证明 TaskPlan 可将多步任务成功率从 0/8 提升到 3/3（2026-07-18）。
- [ ] 优化工具使用引导：联调发现 DeepSeek 偏好 sandbox_exec 通吃（S2）；已证明 Planner 有效，候选：多步任务默认启用 Planner / system prompt 引导 / 工具描述强化。
- [ ] 实现 TD-010：沙箱网络策略增强（两阶段网络 + network_mode 配置化），支撑 pip 安装类自愈场景。
- [ ] 记录 token 消耗与响应延迟，建立成本基准。
