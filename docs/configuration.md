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

人工确认在 TD-008 引入，默认关闭。启用后，仅当运行前端注入了确认 callback（如 CLI 的 `agent run/chat --approve`）时，列入 `tools` 的工具执行前才会询问用户。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | `bool` | `False` | 是否启用人工确认。 |
| `tools` | `list[str]` | `[file_write, file_edit]` | 需要确认的工具名列表。 |

- 交互语义（CLI）：`y`=本次允许；`n`=拒绝（工具返回“用户拒绝”失败，Agent 可换方案）；`a`=本会话该工具免确认。
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
| `memory_limit_mb` | `int` | `256` | 容器内存上限（MB）。 |

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
| `enabled` | `bool` | `False` | 是否启用安全策略引擎。 |
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
