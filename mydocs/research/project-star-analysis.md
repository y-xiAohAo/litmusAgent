# 项目方向 STAR 分析

---

## 方向 A：Agent 可观测性平台

### Situation（背景与困境）

大模型 Agent 正在从实验品走向生产环境。当 Agent 出现以下问题时，开发者几乎无法定位：

```
用户：帮我分析这份财报并生成摘要
Agent：好的，让我先读取文件...

[5 分钟过去了]

Agent：抱歉，我无法完成这个任务。
```

**你作为开发者，能回答以下问题吗？**

- Agent 到底在第几步出错了？
- 是 LLM 返回了错误的 tool call，还是 tool 执行失败了？
- 这次调用消耗了多少 token？花了多少钱？
- 同样的输入昨天能跑通，今天为什么不行？

现实是：**不能。** Agent 执行过程是一个黑盒。

所有 Agent 框架（LangChain、CrewAI、AutoGen）都在解决"怎么让 Agent 跑起来"，但没人在认真解决"Agent 跑起来之后怎么观测和调试"。

市面上 LangSmith 能做到部分，但它：
- 是商业闭源产品，价格昂贵（$39/开发者/月起步）
- 数据存在 LangChain 云端，企业不敢用
- 和 LangChain 深度绑定

**困境总结**：Agent 开发调试极度痛苦，开源可观测性工具几乎空白。

### Task（目标任务）

构建一个开源、自部署的 Agent 可观测性平台，让开发者能：

1. **看见** Agent 每一步的执行轨迹（类似分布式系统的 trace）
2. **量化** 每次调用的 token 消耗和成本
3. **定位** 错误发生在哪一步、哪个 tool call
4. **对比** 不同配置/模型的 Agent 表现
5. **回放** 历史执行，复现 bug

### Action（技术方案）

核心架构三层：

```
┌─────────────────────────────────┐
│  Python SDK (agent-trace)       │  ← 用户 pip install 即可
│  @trace_agent() 装饰器          │
│  自动拦截 LLM call + tool call  │
└──────────────┬──────────────────┘
               │ HTTP/WebSocket
┌──────────────▼──────────────────┐
│  Trace Collector (FastAPI)      │  ← 接收、存储、聚合 trace
│  OpenTelemetry 兼容             │
│  SQLite / PostgreSQL            │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│  Web Dashboard (React)          │  ← 可视化界面
│  Trace 瀑布图 / 树图            │
│  Token 成本仪表盘               │
│  错误分析面板                   │
└─────────────────────────────────┘
```

**关键技术点**：

| 模块 | 技术选型 | 核心挑战 |
|------|----------|----------|
| SDK 拦截层 | Monkey-patch httpx / openai client | 无侵入地拦截所有 LLM 调用 |
| Trace 模型 | Span Tree（借鉴 Jaeger/Zipkin） | 设计适合 Agent 循环的 span 结构 |
| 实时推送 | WebSocket / SSE | trace 流式展示 |
| 成本归因 | 模型价格表 + token 计数 | 精确匹配各模型的计费方式 |
| 可视化 | React + D3.js / visx | 树形 trace 渲染 + 时间轴 |

**MVP 范围（2-3 周）**：
- SDK：`@trace_agent()` 装饰器，支持 OpenAI API
- 后端：FastAPI + SQLite，存储 trace
- 前端：单个 trace 的树形展示页面

### Result（预期成果）

**使用前 vs 使用后**：

```
Before:
  $ python agent.py
  Agent 跑崩了...不知道哪里出问题
  只能加 print() 一行行调试

After:
  $ python agent.py
  $ open http://localhost:8000
  一眼看到：
    Turn 1: LLM 调用 → tool:read_file ✓ (0.3s, 234 tokens)
    Turn 2: LLM 调用 → tool:analyze   ✗ (NameError: 'df' not defined)
  
  点击 ✗ 展开：完整 traceback + 上下文
  问题定位时间：从 30 分钟 → 30 秒
```

**简历亮点**：
- "设计并实现了兼容 OpenTelemetry 的 Agent trace 系统，支持 span tree 可视化"
- "通过 monkey-patch 实现零侵入 SDK，一行装饰器即可接入"
- "开源项目，GitHub XXX stars"（发布后的目标）

---

## 方向 B：代码沙箱 Agent

### Situation（背景与困境）

大模型最强大的能力之一是**写代码**。如果能让 LLM 写出代码并直接执行、看到结果、修正错误，Agent 的能力边界将大幅扩展。

但执行 AI 生成的代码有致命安全隐患：

```
Agent: import os; os.system("rm -rf /")  ← 谁敢让它跑？
Agent: 发送你的 SSH 私钥到这个地址...    ← 谁敢让它联网？
Agent: while True: fork()                 ← 谁敢不限资源？
```

现有方案的问题：

| 方案 | 问题 |
|------|------|
| 不做沙箱 | 相当于给 AI root 权限，纯自杀 |
| Docker 容器 | 配置复杂，冷启动慢（2-5 秒），需要 Docker daemon |
| E2B 云服务 | 商业产品，要钱，数据上云 |
| WebAssembly | 只支持特定语言，生态不成熟 |
| `eval()` / `exec()` | 安全灾难 |

**困境总结**：所有人都知道"让 AI 写代码并执行"是 Killer Feature，但因为安全问题和工程复杂度，绝大多数项目止步于"生成代码让你自己复制粘贴运行"。

### Task（目标任务）

构建一个代码沙箱 Agent，它能够：

1. **安全执行** AI 生成的 Python/Shell/SQL 代码
2. **隔离环境**：每次执行有独立的文件系统、网络管控、资源限制
3. **实时反馈**：Agent 能看到 stdout/stderr/返回值，从而自我修正
4. **工具集成**：沙箱本身作为 agent 的一个 tool，可被任意框架调用

### Action（技术方案）

```
┌────────────────────────────────────────────┐
│              Agent (任意框架)               │
│  "帮我用 Python 分析这个 CSV"               │
│                                            │
│  → tool: sandbox_exec(code="import...")    │
│  ← result: {stdout:"...", stderr:"",       │
│             files:["chart.png"]}           │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────▼─────────────────────────┐
│           Sandbox Manager (Python)          │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Docker Container (per execution)    │   │
│  │  - 独立文件系统 (tmpfs)              │   │
│  │  - 内存限制 256MB                    │   │
│  │  - CPU 限制 1 核/30秒               │   │
│  │  - 网络：白名单/NONE                 │   │
│  │  - 进程数限制 50                     │   │
│  │  - 禁止挂载宿主机目录               │   │
│  │  - 预装：Python, pandas, numpy,     │   │
│  │    matplotlib, sqlite3               │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  容器池（预热容器，秒级响应）               │
│  ┌──────┐ ┌──────┐ ┌──────┐               │
│  │ idle │ │ idle │ │ idle │  ...           │
│  └──────┘ └──────┘ └──────┘               │
└─────────────────────────────────────────────┘
```

**安全层设计（核心壁垒）**：

| 维度 | 措施 | 说明 |
|------|------|------|
| 文件系统 | tmpfs + 白名单目录 | 执行完即销毁，无法访问宿主机 |
| 网络 | 默认关闭，按域名白名单 | 允许 `pip install` 但禁止外传数据 |
| 资源 | cgroup v2 限制 CPU/内存/进程 | 防 fork 炸弹和内存耗尽 |
| 时间 | 30 秒超时强制 kill | 防死循环 |
| 系统调用 | seccomp profile | 禁止 mount、ptrace 等危险调用 |
| Python | AST 静态分析 + RestrictedPython | 阻止 `import os; os.system(...)` |

**关键技术点**：

| 模块 | 核心挑战 |
|------|----------|
| 容器预热池 | 冷启动 2s → 预热 < 100ms，需要管理容器生命周期 |
| 文件注入/提取 | 如何把用户文件安全地放入沙箱，把结果安全地取出来 |
| Python 安全分析 | AST 级别拦截危险调用，但不影响正常科学计算库 |
| 多语言支持 | Python 之外如何支持 Shell、SQL、JS |
| 会话保持 | 同一轮对话共享同一个容器（安装的包不丢失） |

**MVP 范围（2-3 周）**：
- Docker 容器沙箱，支持 Python 代码执行
- 资源限制（内存、CPU、时间、网络）
- Agent tool 接口：`sandbox_exec(code, files?) → result`
- 示例：让 Agent 分析 CSV 并生成图表

### Result（预期成果）

**演示场景**：

```
用户：帮我分析 sales.csv，画一个月度趋势图

Agent：
  Turn 1: sandbox_exec("import pandas as pd; df = pd.read_csv('sales.csv'); print(df.describe())")
  → stdout: [统计数据表格]
  
  Turn 2: sandbox_exec("import matplotlib.pyplot as plt; df.groupby('month')['revenue'].sum().plot(); plt.savefig('trend.png')")
  → files: { "trend.png": <base64> }
  
  Turn 3: 根据数据回答："您的销售额在 3 月达到峰值 120 万..."
```

**和现有方案的区别**：

| 对比 | E2B (云服务) | 我们 |
|------|-------------|------|
| 部署 | 云端 | 本地 Docker |
| 价格 | $0.01/次 | 免费 |
| 数据隐私 | 数据上云 | 数据不出本地 |
| 自定义 | 受限 | 完全可控 |
| Python 安全 | 基础 | AST 级深度防护 |

**简历亮点**：
- "设计并实现了多层安全防护的代码执行沙箱（seccomp + cgroup + AST 分析）"
- "通过容器预热池将代码执行延迟从 2 秒降至 <100ms"
- "开源项目，GitHub XXX stars"
- "可演示的杀手场景：Agent 自主完成数据分析全流程"

---

## A vs B 对比总结

| 维度 | A. 可观测性平台 | B. 代码沙箱 |
|------|----------------|------------|
| 技术新颖度 | ⭐⭐⭐⭐ OpenTelemetry + Agent trace | ⭐⭐⭐⭐⭐ Docker/安全 + Agent |
| 痛点真实度 | ⭐⭐⭐⭐⭐ 每个 Agent 开发者都遇到 | ⭐⭐⭐⭐⭐ 安全是"房间里的大象" |
| 展示效果 | ⭐⭐⭐⭐ 可视化仪表盘很直观 | ⭐⭐⭐⭐⭐ Demo 效果炸裂 |
| 技术广度 | Web全栈 + 分布式trace + 可视化 | 容器安全 + 系统编程 + Agent |
| 工程复杂度 | 中等（CRUD + 前端） | 较高（Docker API + 安全层） |
| 竞品数量 | 少（LangSmith 闭源，LangFuse 简单） | 极少（E2B 闭源） |
| 前沿论文支撑 | 有（Agent tracing 是热点） | 有（AI safety 是大方向） |
| 大厂面试加分 | ⭐⭐⭐⭐⭐ 系统设计常考题 | ⭐⭐⭐⭐⭐ 安全/基础设施 |
