# 配置指南

Litmus Agent 使用 YAML 文件管理配置，并通过 [Pydantic](../src/agent/config.py) 进行类型校验。本文档详细说明每个配置字段的含义、默认值与使用建议。

---

## 配置文件结构

一个完整的配置文件由以下顶层节点组成：

```yaml
llm:       # LLM 后端配置
agent:     # Agent 运行时配置
sandbox:   # 代码沙箱配置
security:  # 安全策略配置（可选）
tools:     # 工具启用配置（可选）
```

未提供的节点会自动使用默认值，因此最小配置文件可以只有几行：

```yaml
llm:
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
```

> 注意：YAML 本身不支持 `${OPENAI_API_KEY}` 这种环境变量插值。示例中这样写是为了提示你应该把真实 Key 填入，或者通过 `OPENAI_API_KEY` 环境变量提供，由 `OpenAIClient.from_env()` 自动读取。

---

## llm

控制 LLM 后端的所有参数。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | `str` | `openai` | 提供商标识，例如 `openai`、`deepseek`、`anthropic`。 |
| `model` | `str` | `gpt-4o` | 模型名称。 |
| `api_key` | `str` | `""` | API 密钥。建议通过环境变量 `OPENAI_API_KEY` 提供。 |
| `base_url` | `str` | `https://api.openai.com/v1` | OpenAI 兼容端点地址。 |
| `temperature` | `float` | `0.7` | 生成温度。代码任务建议 `0.1–0.3`。 |
| `max_tokens` | `int` | `4096` | 每次回复的最大 token 数。 |

示例：

```yaml
llm:
  provider: openai
  model: gpt-4o
  base_url: https://api.openai.com/v1
  temperature: 0.2
  max_tokens: 4096
```

---

## agent

控制 Agent 的运行时行为。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_turns` | `int` | `20` | 最大对话轮数，防止无限循环。 |
| `system_prompt` | `str` | 见代码 | Agent 的人格设定，作为首条消息发给 LLM。 |

### compression（上下文压缩）

上下文压缩在 Phase 7 引入，默认关闭，避免静默改变行为。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否启用上下文压缩。 |
| `context_window` | `int` | `8192` | 上下文窗口总 token 预算。 |
| `reserve_tokens` | `int` | `1024` | 预留 token 数，用于下轮生成。 |
| `summary_model` | `str` | `gpt-4o-mini` | 压缩摘要使用的模型。 |
| `summary_max_tokens` | `int` | `512` | 摘要最大 token 数。 |

### planner（自动规划，Auto-Planner）

自动规划默认关闭。启用后 `Agent.run()` 会先调用一次 LLM 把任务分解为有序步骤（编号列表），构建 `TaskPlan` 并注入进度到 system prompt，显著提升多步任务的完成可靠性。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否启用自动规划。 |
| `max_steps` | `int` | `6` | 分解步骤数上限。 |

- 规划失败或无法解析时静默降级为直接执行，不阻塞任务。
- 外部手工注入的 planner 优先，不会被自动规划覆盖。
- 代价：每次 `run()` 多一次 LLM 调用。CLI 可用 `--plan` 旗标强制启用。

### human_approval（写操作人工确认，TD-008）

人工确认在 TD-008 引入。启用后，仅当运行前端注入了确认 callback（如 CLI 的 `agent run/chat --approve`）时，列入 `tools` 的工具执行前才会询问用户。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool \| null` | `null` | 是否启用人工确认。`null` 表示未显式配置：普通模式按不启用处理；`sandbox.host_dir`（bind）模式下按 `true` 生效（TD-015 单元 C 默认保险）。 |
| `tools` | `list[str]` | `[file_write, file_edit]` | 需要确认的工具名列表。 |

- 交互语义（CLI）：`y`=本次允许；`n`=拒绝（工具返回“用户拒绝”失败，Agent 可换方案）；`a`=本会话该工具免确认。
- 非交互环境（无 TTY / 管道）：无法询问用户，审批回调默认**拒绝**写操作，拒绝原因作为工具结果回传 LLM（TD-015 单元 C）。
- Web UI 无确认界面：`sandbox.host_dir` 模式下未显式设 `enabled: false` 时 Web 入口拒绝启动并报错引导；显式 `false` 放行（风险自担）。
- 优先级：`--approve` 旗标 > 配置文件。
- 未启用或未注入 callback 时，行为完全不变。

### memory（长期记忆）

长期记忆在 Phase 8 引入，默认关闭。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否启用长期记忆。 |
| `backend` | `str` | `structured` | 记忆存储后端，当前仅支持 `structured`。 |
| `memory_root` | `str` | `.hermes/memory` | 记忆持久化目录。 |
| `retrieval_top_k` | `int` | `5` | 每次检索返回的最大条目数。 |
| `recency_fallback` | `bool` | `True` | L0 兜底：字面检索零命中时注入最近 N 条记忆（防止“失忆”）。 |
| `semantic_retrieval` | `bool` | `False` | L2：字面检索未命中时调用 LLM 对候选记忆做语义重排（每次注入多一次 LLM 调用，失败降级 L0）。 |
| `inject_max_entries` | `int` | `5` | 注入 system prompt 的最大条目数。 |
| `llm_extraction_enabled` | `bool` | `False` | TD-013：是否启用 LLM 对话事实提取。开启后每轮运行结束时从对话中提取用户事实（PREFERENCES）与任务摘要（TASK_SUMMARIES），用户口头陈述的事实也能进入记忆。代价：每 `run()` 最多多一次 LLM 调用（预过滤跳过无实质输入的轮次）。 |
| `store_backend` | `str` | `jsonl` | 记忆存储后端：`jsonl`（默认，本地文件）或 `sql`（SQLAlchemy Core，SQLite 测试 / MySQL 部署）。SQL 后端与 JSONL 行为一致性由契约测试套件双后端复验。 |
| `sql_url` | `str \| null` | `null` | `store_backend=sql` 时的数据库连接串，如 `sqlite:////path/memory.db` 或 `mysql+pymysql://user:pass@host:3306/hermes?charset=utf8mb4`。 |
| `cache_enabled` | `bool` | `False` | Redis 注入结果缓存：每轮 `inject()` 的检索结果按 generation 键缓存（写入/清理自动失效，TTL 300s）；Redis 不可达时静默降级为原路径。 |
| `redis_url` | `str` | `redis://localhost:6379/0` | `cache_enabled` 时的 Redis 连接串。 |
| `query_expansion_enabled` | `bool` | `False` | 查询扩展（Multi-Query Expansion）：`memory_search` 原查询字面检索失配时，调用 LLM 生成 3-5 个同义搜索变体逐一再检索并合并。仅在失配时触发（命中零成本），LLM 失败静默降级为原行为。修复硬 paraphrase 查询（如「发布用的编号」→「构建标签」）的检索失败。 |
| `max_age_days` | `int \| null` | `null` | TD-013：记忆最大保留天数，超过的条目在清理时删除。`null` 表示不做时间清理（默认行为不变）。 |
| `cleanup_on_exit` | `bool` | `False` | 是否在 Agent 关闭时执行记忆清理（配合 `max_age_days` 生效）。 |

示例：

```yaml
agent:
  max_turns: 30
  system_prompt: "你是一个严谨的 Python 工程师，所有代码都要在沙箱中验证后再返回。"
  compression:
    enabled: true
    context_window: 8192
    reserve_tokens: 1024
  memory:
    enabled: true
    memory_root: .hermes/memory
```

---

## sandbox

控制代码执行沙箱。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `backend` | `str` | `docker` | 沙箱后端。`docker` 使用 Docker 容器隔离（最安全）；`subprocess` 使用本地子进程（轻量 fallback，无 Docker 时可用，安全性较低）。未知值警告并回退 `subprocess`。 |
| `image` | `str` | `python:3.11-slim` | Docker 镜像（仅 `docker` 后端使用）。 |
| `image_registry` | `str \| null` | `null` | 镜像源地址（TD-007，如 `docker.m.daocloud.io`）。配置后 `ensure_image()` 从该源拉取并打标回原名；官方镜像自动补 `library/` 前缀。`null` 表示从 Docker Hub 拉取。 |
| `timeout` | `int` | `30` | 单次代码执行超时时间（秒）。 |
| `memory_limit_mb` | `int` | `256` | 容器内存上限（MB，仅 `docker` 后端）。工厂透传为 Docker `mem_limit`（TD-017，如 `256` → `"256m"`）；`subprocess` 后端无隔离语义，不生效。 |
| `volume_name` | `str \| null` | `null` | 持久工作区卷名（TD-015 单元 B，仅 `docker` 后端）。配置后使用固定 Docker 卷 `litmus-ws-<volume_name>`，跨会话保留 `/workspace` 文件且关闭时不删除；`null` 时使用随机卷并在关闭时清理。只允许字母、数字、`_`、`.`、`-`。 |
| `host_dir` | `str \| null` | `null` | 宿主机目录 bind 挂载（TD-015 单元 C）。配置后 Agent 直接操作宿主机真实项目目录（容器内 `/workspace` → `host_dir`），与 `volume_name` 互斥。详见下方"bind 工作区模式"警示。 |
| `network_mode` | `str` | `none` | 容器池网络模式（TD-010，仅 `docker` 后端），原样透传给 Docker（`none`/`bridge`/...）。默认 `none` 禁网。注意 `bridge` 等模式可经 docker0 网关访问宿主机内网（含云 metadata 169.254.169.254），内网敏感环境慎用。 |
| `allow_setup_network` | `bool` | `False` | 安装阶段自动放行（TD-010，仅 `docker` 后端）。为 `True` 时，`sandbox_exec` 检测到 `pip install` 意图的执行改用有网（`bridge`）临时容器（同一 workspace 卷/bind 挂载，其余加固不变），用完即销毁不入池；其余执行仍走禁网池。是便利开关而非安全边界——pip 意图是字符串/正则级启发式，可被 prompt injection 诱导、也会被代码里的字面量（如 `x = "pip install curl"`）误触发；且 bridge 容器可经 docker0 网关访问宿主机内网（含云 metadata 169.254.169.254），bind 模式下开启会打 warning（攻击面叠加），公网/内网敏感环境慎用。 |

> **⚠️ bind 工作区模式（host_dir）风险警示**
>
> bind 模式下 Agent 的写操作**直接落在宿主机真实目录**，误写、误删不再有沙箱兜底。启用前请确认理解以下四道保险与限制：
>
> 1. **git 强制快照**：`host_dir` 必须已是 git 仓库（否则拒绝启动，引导 `git init`）；启动时若工作区 dirty，自动在当前分支提交快照（信息 `litmus: pre-agent snapshot`，署名 `litmus-agent`，通过 env 级 `GIT_AUTHOR_*` 兜底，不改你的 git 配置）。docker 与 subprocess 后端同样强制。
> 2. **写确认默认开启**：未显式配置 `agent.human_approval.enabled` 时按 `true` 生效（`file_write`/`file_edit` 执行前询问 `y/n/a`）；非交互环境（无 TTY / 管道）下默认**拒绝**写操作。显式设 `false` 可关闭，但会打 warning，风险自担。**Web UI 无确认界面**：检测到 `host_dir` 且未显式关闭审批时拒绝启动并提示。
> 3. **敏感文件 read deny**：默认注入优先级 90 的读拒绝规则：`**/.env*`、`**/.ssh/**`、`**/*.{pem,key}`、`**/id_rsa*`、`**/.git/**`。`security.enabled` 未显式配置时按 `true` 生效；显式关闭打 warning。注意该策略约束的是**工具层**访问（`grep`/`glob` 内嵌脚本另按同口径硬编码兜底过滤）；容器内 `sandbox_exec` 执行的代码**不受策略约束**——bind 模式的真实边界是**挂载点 + git 快照 + 写确认**三件套，read deny 仅为辅助。
> 4. **容器加固维持**：network=none、read_only 根文件系统 + tmpfs、`cap_drop=ALL`（仅回加 `CHOWN` 供 workspace chown）+ `no-new-privileges`（TD-018）、不挂 docker.sock；bind 模式容器设 `HOME=/tmp`，POSIX 下以宿主 `uid:gid` 运行（保证写出文件属主正确）并跳过 chown；Windows 维持 nobody（Docker Desktop 文件共享层自动映射属主）。
>
> **⚠️ 追加警示（TD-010）**：bind 模式下再显式开启 `allow_setup_network: true` 属于攻击面叠加——pip 意图的执行会在**有网（bridge）容器中直写宿主目录**，工厂会打 warning。且 bridge 容器可经 docker0 网关访问宿主机内网（含云 metadata 服务 169.254.169.254），内网敏感环境同样慎用。除非你明确需要"边装依赖边改宿主机代码"的场景，否则不要在 bind 模式开启它。
>
> 其他限制：
> - **Docker 不可用即报错，不降级** subprocess（降级等于在宿主机弱隔离裸跑，更危险）。显式配置 `backend: subprocess` + `host_dir` 视为自担风险的 opt-in。
> - **禁止两个 Agent 同时挂载同一个 `host_dir`**（不加锁，属过度设计）。
> - Windows 路径转换与属主映射为尽力支持（经 Docker Desktop 文件共享层）。
> - Web UI 的 YAML 配置经环境变量 `AGENT_CONFIG` 指定（与 CLI `--config` 同格式）；bind 模式下 Web 的审批限制见上方第 2 条。
>
> **回滚**：快照提交在当前分支，回滚与审计命令——
>
> ```bash
> git -C <host_dir> status                    # 查看 Agent 改动
> git -C <host_dir> diff                      # 查看具体差异
> git -C <host_dir> reset --hard <快照sha>    # 回到启动前快照（横幅会打印该命令）
> ```
>
> 启动时 CLI 会打印横幅，包含挂载路径、快照 sha、写确认状态与回滚命令提示。

> **工作区生命周期（TD-015）**：CLI（run/chat）与 Web UI 退出时会调用 `agent.close()` 关闭自建沙箱 backend，默认模式下随机卷随之删除（修复孤儿卷泄漏）；`volume_name` 模式卷保留，手动删除用 `docker volume rm litmus-ws-<name>`。存量孤儿卷可经 `docker volume ls -f name=hermes-workspace` 查看并手动清理。

> 说明：`backend: subprocess` 为轻量 fallback（TD-002 已实现）。它使用本地子进程 + 实例临时目录作为 workspace，不提供 Docker 级隔离（无 cgroup/seccomp/网络禁用）；沙箱内 POSIX 路径（如 `/workspace/main.py`）会映射到实例临时目录内，不触碰宿主机真实路径。仅在无 Docker 环境下使用。

示例：

```yaml
sandbox:
  backend: docker
  image: python:3.11-slim
  timeout: 60
  memory_limit_mb: 512
```

---

## security

安全策略在 Phase 9 引入，默认关闭。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否启用安全策略引擎。`sandbox.host_dir`（bind）模式下未显式配置时按 `true` 生效，并自动注入敏感文件 read deny（TD-015 单元 C，详见 sandbox 节警示框）。 |
| `default_action` | `str` | `allow` | 默认动作：`allow` 或 `deny`。 |
| `rules` | `list[dict]` | `[]` | 自定义策略规则列表。 |
| `workspace_path` | `str` | `/workspace` | `file/path` write 的允许根（TD-006）。仅默认规则集下生效。 |

当 `enabled` 为 `true` 且未提供 `rules` 时，使用内置宽松默认规则集。

> **写操作 workspace 边界（TD-006）**：默认规则集下，`file_write` / `file_edit` 只允许写入 `workspace_path` 之下（默认 `/workspace`），其余路径（如 `/tmp`）与含 `..` 的逃逸路径一律拒绝；敏感路径（`/etc/passwd`、`.ssh` 等）保持原有高优先级拒绝。修改 `workspace_path`（如 `/app`）后边界随之迁移，`/workspace` 不再允许。提供自定义 `rules` 时边界不注入，由自定义规则完全接管。

---

## tools

控制默认工具的启用范围。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `list[str] \| null` | `null` | 启用的工具名列表。`null` 表示启用所有默认工具。 |

可用工具名：

- `sandbox_exec`：在沙箱中执行 Python 代码。
- `file_read`：读取沙箱内文件内容。
- `file_write`：在沙箱内创建或覆盖文件。
- `file_list`：列出沙箱内目录内容。
- `file_edit`：精确编辑沙箱内已有文件的局部内容。
- `grep`：在沙箱内按正则搜索文件内容。
- `glob`：在沙箱内按文件名模式匹配文件。
- `finish`：标记任务完成并返回结果。

> 注意：`context_read`、`memory_read` 与 `memory_search` 分别是上下文压缩和长期记忆的内部配套工具，不受 `tools.enabled` 控制；只要启用了对应功能，Agent 会自动注册它们。`memory_search` 支持自然语言搜索记忆（search-then-read），返回候选含 uri 供 `memory_read` 精读。

示例（仅允许执行代码和结束任务）：

```yaml
tools:
  enabled:
    - sandbox_exec
    - finish
```

---

## mcp（MCP 工具接入，TD-016）

接入 MCP（Model Context Protocol）server 提供的工具。需要先安装可选依赖：

```bash
pip install agent[mcp]   # 或 pip install mcp
```

> ⚠️ **供应链风险警示**：MCP server 是宿主机进程（stdio 形态）或远程服务
> （url 形态），其工具在**宿主执行、不经沙箱**——配置即信任声明，信任级别
> 等价于 `pip install`。只接入你信任的 server；默认所有 MCP 工具都会触发
> 人工确认。注意：人工确认需前端注入确认 callback 才真正生效；无确认通道的
> 部署（如裸 Python API 直接调用 `Agent`）MCP 工具将**不经确认直接执行**，
> 请自行评估风险（可用 `trust: true` 白名单化或 `security.rules` 策略收口）。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tool_timeout` | `int` | `30` | 单次 MCP 工具调用强制超时（秒），防 server 僵死 |
| `degrade_ttl` | `int` | `60` | 降级冷却秒数（TD-019）。server 调用超时/失败后进入降级：TTL 内对该 server 的调用快速失败；TTL 过期后下一次调用先惰性重连该 server（新建 ClientSession，走与初次连接相同的传输路径），成功则清除降级并正常执行本次调用，失败则刷新降级时间戳继续快速失败。纯惰性，无后台线程/定时任务 |
| `servers` | `list` | `[]` | server 列表，为空则不激活 |

每个 server 条目（`command` 与 `url` 互斥且必居其一）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | server 名，只允许字母/数字/`_`/`-`，用于工具名前缀 |
| `command` | `str` | stdio 形态：启动命令（Windows 上 `npx`/`uvx` 需 `cmd /c npx ...`） |
| `args` | `list[str]` | stdio 形态：命令参数 |
| `env` | `dict \| null` | stdio 形态：环境变量（给出时整体替换默认环境） |
| `url` | `str` | SSE/HTTP 形态：端点 |
| `headers` | `dict \| null` | SSE/HTTP 形态：静态请求头（如 Authorization） |
| `transport` | `stdio \| sse \| http \| null` | 显式传输判别（默认 `null`）。`null` 时按启发式推断：有 `command` → `stdio`；`url` 路径以 `/sse` 结尾 → `sse`；否则 → `http`（Streamable HTTP）。显式配置时校验一致性：`stdio` 须有 `command`，`sse`/`http` 须有 `url`。 |
| `trust` | `bool` | `false`（默认）该 server 全部工具进人工确认清单；`true` 豁免 |

行为要点：

- **惰性装配**：首次 `run()` 前连接 server 并发现工具，公开 API 不变。
- **命名前缀**：发现的工具注册为 `mcp__<server>__<tool>` 全名，受
  `tools.enabled` 白名单控制（全名匹配）。
- **失败降级**：单 server 连接失败只记 warning 并跳过；全部失败不阻塞 Agent。
- **僵死防护**：调用超时返回 `MCPError: 调用超时...` 失败结果，Agent 继续；
  超时/调用失败后该 server 记入降级表，TTL（`degrade_ttl`，默认 60 秒）内
  后续调用立即返回 `MCPError: server 已降级...` 快速失败；TTL 过期后的
  下一次调用先惰性重连该 server，成功则恢复正常调用，失败则重新计时
  （TD-019，重连仅由调用触发，无后台任务）。
- **策略锚点**：MCP 工具统一映射 resource=`mcp/server`、operation=`call`、
  subject=`mcp/<server>`，可在 `security.rules` 里按此写自定义规则；
  默认规则集不含 MCP 条目（人工确认是主防线）。
- **生命周期**：同步 `agent.close()`（CLI）或异步 `await agent.aclose()`
  （Web shutdown，等待回收完成）回收全部连接与 stdio 子进程。

示例：

```yaml
mcp:
  tool_timeout: 30
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
      trust: false
    - name: remote-search
      url: http://localhost:8000/sse
      headers: {Authorization: "Bearer ..."}
      trust: false
```

---

## 完整示例

下面是一份生产环境可用的完整配置示例：

```yaml
llm:
  provider: openai
  model: gpt-4o
  api_key: ""                  # 建议通过 OPENAI_API_KEY 环境变量提供
  base_url: https://api.openai.com/v1
  temperature: 0.2
  max_tokens: 4096

agent:
  max_turns: 30
  system_prompt: "你是一个严谨的 Python 工程师，优先在沙箱中验证代码。"
  compression:
    enabled: false
  memory:
    enabled: false

sandbox:
  backend: docker
  image: python:3.11-slim
  timeout: 60
  memory_limit_mb: 512

security:
  enabled: false

tools:
  enabled:
    - sandbox_exec
    - file_read
    - file_write
    - file_list
    - file_edit
    - grep
    - glob
    - finish
```

在 Python 中加载配置：

```python
from agent.config import load_config

config = load_config("examples/config.yaml")
print(config.llm.model)
print(config.agent.max_turns)
print(config.sandbox.backend)
```
