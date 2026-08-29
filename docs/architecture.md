# Litmus Agent 架构说明

本文档用 ASCII 图展示 Litmus Agent 的核心组件、数据流与一次完整执行过程，帮助你快速理解系统设计。

---

## 组件架构

Litmus Agent 采用分层设计：CLI 面向用户，Agent Core 编排主循环，ToolRegistry 管理工具，沙箱层负责隔离执行，记忆与安全作为可插拔扩展。

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI 层                               │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│   │ agent run   │  │ agent chat  │  │    agent config     │ │
│   └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└──────────┼────────────────┼────────────────────┼────────────┘
           │                │                    │
           └────────────────┴────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Agent Core                             │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │      Agent      │  │ ToolRegistry │  │    Planner     │  │
│  │    .run()       │◄─┤  + Policy    ├──┤  / State       │  │
│  └────────┬────────┘  └──────┬───────┘  └────────────────┘  │
│           │                  │                               │
│  ┌────────┴────────┐  ┌──────┴──────┐  ┌────────────────┐  │
│  │  ErrorClassifier │  │    Tools    │  │  Reflective    │  │
│  │  + Trace         │  │ sandbox_exec│  │  Advisor       │  │
│  └─────────────────┘  │ grep / glob │  └────────────────┘  │
│                       │ file_read / │                       │
│                       │ file_write /│                       │
│                       │ file_edit / │                       │
│                       │ file_list / │                       │
│                       │ finish      │                       │
│                       └──────┬──────┘                       │
└──────────────────────────────┼──────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   LLM Client    │  │ Docker Sandbox  │  │ MemoryManager   │
│ OpenAI / Echo   │  │   Backend       │  │ + Policy        │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 各层职责

- **CLI 层**：提供 `agent run`、`agent chat`、`agent config` 等人机交互入口。
- **Agent Core**：负责主循环、消息历史、工具路由、计划追踪、错误分类与 Trace 记录。
- **ToolRegistry**：统一管理工具注册，并在执行前通过 PolicyEngine 进行策略检查。
- **MCP 接入层**（`mcp_client.py`）：连接外部 MCP server（stdio / SSE / HTTP），发现的工具包装为 ToolSpec 注册进 ToolRegistry，与内置工具走同一策略 / 审批 / Trace 卡口。
- **Tools**：`sandbox_exec` 执行代码，`grep`/`glob`/`file_read`/`file_list` 检索与查看产物，`file_write`/`file_edit` 写入与编辑，`finish` 终止任务。
- **Docker Sandbox Backend**：在隔离容器中运行 LLM 生成的代码；支持持久工作区（随机卷清理 / `volume_name` 命名卷跨会话 / `host_dir` bind 挂载宿主项目）与可配置网络策略（`network_mode` 默认 none）。
- **LLM Client**：支持 OpenAI 兼容 API 与 EchoClient 测试桩；支持流式输出（SSE 分片聚合 + token/思考链回调旁路）与 DeepSeek V4 思考模式（`thinking` 开关）。
- **MemoryManager / PolicyEngine**：长期记忆与安全策略，默认关闭，可按需启用。

---

## 数据流

下图展示 `Agent.run(user_input)` 的一次完整循环：用户输入进入消息历史，LLM 决定是纯文本回复还是调用工具；如需工具，执行结果再次进入历史，循环继续。

```
                    用户输入
                       │
                       ▼
              ┌─────────────────┐
              │  Agent.run()    │
              │  追加 user 消息  │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  构建 messages   │
              │ system + history │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  LLMClient.chat │
              └────────┬────────┘
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
    ┌─────────────┐         ┌─────────────┐
    │  content    │         │ tool_calls  │
    │  直接返回    │         │ 继续执行    │
    └─────────────┘         └──────┬──────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │ ToolRegistry    │
                          │ .execute(call)  │
                          │ Policy 预检查   │
                          └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
             ┌──────────┐  ┌──────────┐  ┌──────────┐
             │ 成功     │  │ 失败     │  │ 策略拒绝 │
             │ 追加结果 │  │ Error-   │  │ 追加原因 │
             │ 到历史   │  │ Classifier│  │ 到历史   │
             └────┬─────┘  └────┬─────┘  └────┬─────┘
                  │             │             │
                  └─────────────┴─────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  再次调用 LLM    │
                       │  观察工具结果    │
                       └────────┬────────┘
                                │
                                ▼
                       无 tool_calls 时返回最终文本
```

### 关键设计点

1. **循环直到无 tool_calls**：Agent 不会在一次 LLM 调用后就停止，而是持续循环，直到 LLM 给出纯文本回复或达到 `max_turns`。
2. **错误作为消息回传**：工具执行失败不抛异常，而是把错误信息包装成 `ToolResult` 追加到历史，让 LLM 自己决定如何修正。
3. **策略拒绝对 LLM 可见**：PolicyEngine 拦截高危操作时，拒绝原因会返回给 LLM，便于其调整请求。

---

## 执行序列

下图展示一次典型的自我纠错过程：用户请求写排序算法 → LLM 生成有 bug 的代码 → 沙箱执行失败 → 错误分类 → LLM 修正 → 成功执行 → 返回结果。

```
User    Agent    LLMClient  ToolRegistry  Sandbox  ErrorClassifier
 │         │          │            │          │          │
 │────────►│          │            │          │          │  1. run("写快速排序")
 │         │─────────►│            │          │          │  2. chat()
 │         │◄─────────│            │          │          │  3. 返回代码 + tool_call
 │         │          │            │          │          │     (sandbox_exec)
 │         │─────────────────────►│          │          │  4. execute()
 │         │          │            │─────────►│          │  5. execute_code()
 │         │          │            │◄─────────│          │  6. SyntaxError
 │         │          │            │          │─────────►│  7. classify()
 │         │          │            │◄─────────│          │  8. RECOVERABLE
 │         │◄─────────────────────│          │          │  9. ToolResult(错误)
 │         │─────────►│            │          │          │ 10. 再次 chat()
 │         │◄─────────│            │          │          │ 11. 返回修正后代码
 │         │─────────────────────►│          │          │ 12. execute()
 │         │          │            │─────────►│          │ 13. execute_code()
 │         │          │            │◄─────────│          │ 14. 成功输出
 │         │◄─────────────────────│          │          │ 15. ToolResult(结果)
 │         │─────────►│            │          │          │ 16. 最终 chat()
 │         │◄─────────│            │          │          │ 17. 返回最终答案
 │◄────────│          │            │          │          │ 18. 输出给用户
```

### 时序说明

1. **步骤 1-3**：Agent 把用户请求发给 LLM，LLM 决定生成 Python 代码并请求 `sandbox_exec`。
2. **步骤 4-6**：ToolRegistry 执行工具，Docker Sandbox 运行代码，返回 `SyntaxError`。
3. **步骤 7-9**：ErrorClassifier 判断错误为 `RECOVERABLE`，并附加恢复建议，结果作为 tool 消息回传。
4. **步骤 10-15**：Agent 再次调用 LLM，LLM 看到错误后修正代码，第二次执行成功。
5. **步骤 16-18**：LLM 根据执行结果生成最终回答，Agent 返回给用户。

---

## 记忆与安全扩展

当启用长期记忆和安全策略时，Agent 主循环的扩展方式如下：

```
Agent.run() 开始
    │
    ▼
MemoryManager.inject() ──► 把相关记忆注入 system prompt
    │
    ▼
主循环执行（见上方数据流）
    │
    ▼
MemoryManager.record() ──► 把本次运行关键信息持久化
    │
PolicyEngine.evaluate() ──► 工具执行前策略拦截
```

### 说明

- **记忆注入**：每次 `run()` 开始前，MemoryManager 从本地存储检索相关记忆，追加到 system prompt 末尾。
- **记忆记录**：任务结束（finish / fatal / max_turns）时，Agent 触发 MemoryManager 记录环境、产物、偏好与失败模式。
- **策略拦截**：ToolRegistry 在执行任何 tool 前，先调用 PolicyEngine 评估资源/操作/主体，拒绝时返回原因给 LLM。

---

## 参考资料

- 核心实现：`src/agent/core/engine.py`
- 沙箱后端：`src/agent/sandbox/docker_backend.py`
- 工具定义：`src/agent/tools/`
- CLI 实现：`src/agent/cli/`
- 完整计划：`docs/plans/2026-04-28-code-sandbox-agent.md`
