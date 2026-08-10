# 学习日志：代码沙箱 Agent 项目

> **教学方式**：每个 Phase 先讲「我们在做什么、为什么这样做」，再动手。文档侧重原理和设计思想，而非操作记录。
>
> **学生**：msn | **导师**：Hermes Agent

---


## 目录

- [Phase 1：打好地基——为什么工程规范比写代码更重要](#phase-1)
- [Phase 2：Agent 核心引擎](#phase-2) ✅ 完成
- [Phase 3：沙箱层](#phase-3)
- [Phase 4：工具链与集成](#phase-4)
- [Phase 5：核心机制扩展——为什么 Agent Trace 是其他机制的地基](#phase-5) ✅ 完成
- [Phase 6：反思式错误恢复](#phase-6) ✅ 完成
- [Phase 6 修复：ReflectiveAdvisor 尊重 ErrorClassifier](#phase-6-fix) ✅ 完成
- [Phase 7.1：上下文压缩第一步 —— Token 估算与配置](#phase-71) ✅ 完成
- [Phase 7.2：工具结果外迁 —— ContextCache 与 ToolResultExternalizer](#phase-72) ✅ 完成
- [Phase 7.3：小模型摘要器](#phase-73) ✅ 完成
- [Phase 10.1：CLI 入口 —— argparse](#phase-101) ✅ 完成
- [Phase 10.2：Rich 美化输出](#phase-102) ✅ 完成
- [Phase 10.3：交互模式](#phase-103) ✅ 完成
- [Phase 10.4：示例场景脚本](#phase-104) ✅ 完成
- [Phase 10.5：Docker 一键启动](#phase-105) ✅ 完成
- [Phase 10.6：README 重写](#phase-106) ✅ 完成
- [Phase 10.7：架构图（ASCII）](#phase-107) ✅ 完成
- [Phase 10.8：使用文档](#phase-108) ✅ 完成
- [Phase 10.9：Demo 脚本与录制准备](#phase-109) ✅ 完成
- [评测日志体系](#evaluation-log) ✅ 完成

## Phase 1：打好地基——为什么工程规范比写代码更重要 {#phase-1}

### 开篇：先理解"地基"是什么

很多同学开始一个项目时，第一反应是"赶紧写代码"。但一个有经验的工程师第一反应是：

> **"这个项目三个月后还能维护吗？别人能看懂吗？改了代码敢不敢不手动测一遍就上线？"**

这三个问题对应的答案就是 Phase 1 要建立的三个地基：

| 问题 | 答案 | 工具 |
|------|------|------|
| 能维护吗？ | 统一的目录结构、类型标注、配置管理 | src-layout, mypy, Pydantic |
| 别人能看懂吗？ | 自动化代码风格检查、结构化日志 | ruff, structlog |
| 改了敢上线吗？ | 每次改动都有测试验证 | pytest + TDD |

Phase 1 不写任何 Agent 逻辑，它只做一件事：**让这个项目成为一个"成年人"的项目，而不是一个"玩具demo"**。

面试官看到一个项目，第一眼看的不是你的 Agent 多聪明，而是：
- 有测试吗？（pytest）
- 有类型标注吗？（mypy）
- 代码风格统一吗？（ruff）
- 能一键安装运行吗？（pyproject.toml + `pip install -e .`）

这些是"专业"和"业余"的分界线。

---

### 1.1 项目骨架：src-layout 与 pyproject.toml

#### 什么是 src-layout？

Python 项目有两种目录布局：

```
# 扁平布局（不推荐）
project/
├── agent/
│   └── ...
├── tests/
└── setup.py

# src-layout（推荐）
project/
├── src/
│   └── agent/
│       └── ...
├── tests/
└── pyproject.toml
```

**为什么要 src-layout？** 防止一个常见陷阱：你在项目根目录运行 `python`，然后 `import agent`——导入的是当前目录的源码，而不是你 pip install 的版本。这会导致"在我机器上能跑"的问题。src-layout 强制你通过 `pip install -e .` 安装后才能导入，避免了路径混淆。

#### pyproject.toml 是什么？

`pyproject.toml` 是 Python 项目的"身份证"。以前 Python 项目需要三个文件（setup.py + setup.cfg + requirements.txt），现在一个 pyproject.toml 全搞定：

```toml
[build-system]          # 怎么构建这个包
[project]               # 包的基本信息
dependencies = [...]    # 运行时依赖
[project.optional-dependencies]
dev = [...]             # 开发时依赖（测试/lint/类型检查）
[tool.pytest.ini_options]  # pytest 配置
[tool.mypy]                # mypy 配置
[tool.ruff]                # ruff 配置
```

**为什么重要？** 一个文件定义一切，新成员 clone 项目后只需 `pip install -e ".[dev]"` 就能得到完全相同的环境。这叫"可复现的开发环境"。

---

### 1.2 测试框架：pytest 与 TDD 方法论

#### pytest 比 unittest 好在哪？

Python 标准库自带了 `unittest`，但几乎没人用。pytest 的优势：

```python
# unittest 写法（啰嗦）
import unittest
class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)

# pytest 写法（简洁）
def test_add():
    assert add(1, 2) == 3
```

pytest 的核心哲学：**测试应该是普通的 Python 函数，不是类的方法。** 用 `assert` 而不是 `self.assertEqual`，读起来像自然语言。

三个配套工具的作用：

| 工具 | 解决的问题 |
|------|-----------|
| pytest-asyncio | Agent 的 `async def run()` 必须用异步测试 |
| pytest-cov | "哪些代码被测试覆盖了？"——面试时可以展示 85%+ 覆盖率 |
| pytest -v | 显示每个测试的名字和结果，而不是简单的 `....` |

#### TDD 不只是"先写测试"

TDD（Test-Driven Development）经常被误解为"先写测试再写代码"。这太表面了。TDD 真正教给你的是：

**你在写测试的时候，其实是在设计接口。**

```python
def test_agent_responds_to_user():
    agent = Agent(llm_client=EchoClient())
    response = await agent.run("hello")
    assert "hello" in response
```

写这个测试时，你被迫回答以下设计问题：
- Agent 怎么创建？（构造函数需要什么参数？）
- Agent 怎么调用？（`agent.run()` 对吗？）
- Agent 返回什么？（字符串？对象？）

这些问题的答案就是你的 API 设计。如果测试写起来很痛苦，说明你的接口设计有问题。TDD 让你在写代码之前先"使用"自己的代码，从而发现设计缺陷。

**Red-Green-Refactor 循环的本质**：

```
RED:   写测试 → 跑 → 失败（证明你确实在测试"还没实现的功能"）
GREEN: 写最简代码 → 跑 → 通过（证明你写对了一个最小单元）
REFACTOR: 整理代码 → 跑 → 仍然通过（证明你没改坏任何东西）
```

每一步都必须跑测试，因为测试是你唯一的安全网。没有安全网的编程叫"赌命编程"。

---

### 1.3 类型系统：mypy 与 Python type hints

#### 动态类型的代价

Python 是动态类型语言，这是它的灵活性，也是它的致命弱点：

```python
def process(config):
    return config["max_turns"] * 2  # config 是什么？dict？对象？
```

这段代码在运行前完全不知道对不对。可能 `config` 是 dict，也可能是个对象需要 `config.max_turns`。只有跑到这一行才会报错——可能在线上环境才第一次跑到。

#### type hints 解决什么问题

```python
from pydantic import BaseModel

class AgentConfig(BaseModel):
    max_turns: int = 20

def process(config: AgentConfig) -> int:
    return config.max_turns * 2  # IDE 自动补全 + mypy 提前检查
```

现在：
- IDE 知道 `config.max_turns` 是 int，能自动补全
- mypy 在你不运行代码的情况下检查类型错误
- 你的同事（或三个月后的你）一眼就知道 `process` 接受什么、返回什么

**类型标注不是"给弱类型语言打补丁"，而是"给代码加可执行的文档"。**

#### mypy strict 模式的意义

我们在 pyproject.toml 里配置了 `strict = true`。这意味着每个函数都必须标注参数类型和返回类型。这很严格，但值得：

- 不写类型标注 = mypy 报错
- 用 `Any` 逃避标注 = mypy 报错
- 函数没写返回值类型 = mypy 报错

这听起来很烦，但它的作用是**把 bug 从运行时移到编码时**。一个 typo 导致的类型错误，在保存文件 3 秒后就被 mypy 揪出来，而不是在凌晨 3 点的线上事故中才发现。

---

### 1.4 代码风格：ruff

#### lint 工具是干什么的

Lint 工具检查代码中的"坏味道"：

```python
import os, sys, json  # ruff: 请不要在一行导入多个模块

def f(x,y):  # ruff: 逗号后面要加空格
    pass

import requests
import json  # ruff: import 顺序不对，应该按字母排列
```

这些问题不影响功能，但影响可读性和一致性。团队协作时，如果每个人代码风格不同，代码库会变成大杂烩。

#### 为什么用 ruff 而不是 flake8 + isort + black

以前需要三个工具：
- flake8：检查代码质量
- isort：排序 import
- black：格式化代码

ruff 用 Rust 重写了所有这些规则，一个工具全部搞定，速度快 10-100 倍。

**一个面试细节**：如果你的项目用 ruff，面试官（如果懂技术）会认为你关注工程效率，而不是盲目跟风用老工具。

---

### 1.5 配置管理：Pydantic + YAML

#### 为什么配置管理是"地基"的一部分

假设你的 Agent 有这些参数：

```python
agent = Agent(
    llm_client=OpenAIClient(api_key="sk-...", model="gpt-4o", temperature=0.3),
    max_turns=15,
    system_prompt="You are a helpful data analyst.",
)
```

问题：
1. API Key 硬编码在代码里 → git commit 就泄露了
2. 改 temperature 要改代码 → 非开发人员没法调参
3. 部署到不同环境（开发/测试/生产）要改代码

解决方案：**配置与代码分离**。

#### 我们的设计

```
用户写 config.yaml   →  加载为 Pydantic 模型  →  Agent 使用模型对象
（人类友好）              （类型安全）              （IDE 友好）
```

```yaml
# config.yaml — 人类可读
llm:
  model: gpt-4o
  temperature: 0.3

agent:
  max_turns: 15

sandbox:
  timeout: 30
```

```python
# Python 代码 — 类型安全
config: AgentConfig = load_config("config.yaml")
print(config.llm.model)         # "gpt-4o" (str, IDE 自动补全)
print(config.sandbox.timeout)   # 30 (int, IDE 自动补全)
```

Pydantic 的角色：YAML 文件只是字符串，Pydantic 帮你把它变成有类型的 Python 对象。如果 YAML 写错了（比如 temperature 写了 "high" 而不是 0.7），Pydantic 在加载时就报错，而不是等到 Agent 调用 LLM 时才发现。

---

### 1.6 日志系统：从 print 到 structlog

#### print 调试的三个致命问题

```python
print("调用 LLM...")
print(f"返回: {response}")
```

1. **无法控制级别**：上线后你不想看到调试信息，但 print 要么全有要么全无
2. **无法结构化搜索**：找"所有用户 alice 的操作"需要在日志里 grep，痛苦
3. **性能差**：print 是同步阻塞的，高并发下拖慢性能

#### structlog 的设计哲学

structlog 的核心理念：**日志是结构化事件，不是字符串**。

```python
# 传统方式（字符串）
logger.info(f"User {user} completed task {task} in {time}s")

# structlog 方式（结构化事件）
logger.info("task_completed", user=user, task=task, duration=time)
```

第二种方式的优势：
- 可以按 `user` 字段搜索
- 可以统计所有 `task_completed` 事件的平均 `duration`
- 切换到 JSON 输出后，Elasticsearch/Datadog 可以直接索引

#### 双模式设计

```python
# 开发时：彩色终端
configure_logging(json_format=False)
# [info] 2026-04-28 18:00:00 task_completed  user=alice task=analysis duration=3.2

# 生产时：JSON 行
configure_logging(json_format=True)
# {"event":"task_completed","user":"alice","task":"analysis","duration":3.2,"timestamp":"..."}
```

同一个代码，一个开关切换输出格式。这是生产级项目的基本素养。

---

### Phase 1 核心收获

Phase 1 没有写任何 Agent 逻辑，但它建立了四个关键能力：

1. **可复现的环境**：`pip install -e ".[dev]"` 一键部署
2. **自动化的质量门禁**：pytest + mypy + ruff，不合规的代码进不了仓库
3. **类型安全的配置**：Pydantic 模型 + YAML 文件，配置错误加载时就能发现
4. **生产级日志**：structlog 结构化日志，开发/生产双模式

这四个能力加上 TDD 方法论，就是"专业开发者"和"写玩具demo的"之间的分水岭。接下来 Phase 2 开始写 Agent 核心逻辑时，每写一行代码都有测试守护、有类型检查、有风格约束——你可以专注于 Agent 设计本身，而不需要担心低级错误。

---

## Phase 2：Agent 核心引擎

Phase 2 是整个项目的心脏。Phase 1 让我们有了一个"专业的 Python 项目"，Phase 2 让它变成一个"真正的 Agent"。

在这一阶段，我们逐步构建了 8 个 Task（6 个独立模块 + 1 个集成 + 1 个 LLM Client 增强），每个解决 Agent 架构中的一个核心问题：

| 模块 | 解决的问题 |
|------|-----------|
| 2.1 Agent 主循环 | Agent 怎么"思考→行动→再思考"？ |
| 2.2 Tool Call 执行 | LLM 怎么调用工具？Agent 怎么执行并回传结果？ |
| 2.3 State 状态管理 | Agent 怎么记住"我装过 pandas 了"？ |
| 2.4 Error Handler | Agent 面对报错怎么像程序员一样判断和恢复？ |
| 2.5 Planner | Agent 怎么把模糊目标拆成可追踪的步骤？ |
| 2.6 Tool Router | 多个工具时，怎么帮 LLM 选对工具？ |
| 2.7 集成 | 以上模块怎么在 Agent 主循环里协同工作？ |
| 2.8 LLM Client 增强 | 怎么让 LLM 客户端具备生产级可靠性？ |

---

### 2.1 Agent 主循环：Agent 的"心跳"

#### 先理解：Agent 和"调 API 脚本"有什么区别？

很多人写第一个 LLM 应用时，代码是这样的：

```python
response = openai.chat("帮我分析这个 CSV")
print(response)
```

这叫"调 API 脚本"，不是 Agent。区别在哪？

**调 API 脚本**：一次调用，一次回复，结束。LLM 不知道自己做错了什么，也没机会改正。

**Agent**：多次调用，每次 LLM 都能看到"我上一步做了什么、结果是什么"，然后决定下一步。

```
用户: "分析 sales.csv"
  ↓
Agent [第1轮]: 调 LLM → LLM 说"我先看看文件" → 调 file_list 工具
Agent [第2轮]: 把工具结果发给 LLM → LLM 说"用 pandas 读取" → 调 sandbox_exec
Agent [第3轮]: 代码出错！→ 把错误发给 LLM → LLM 说"哦我忘了 import pandas" → 再调 sandbox_exec
Agent [第4轮]: 成功 → LLM 说"数据有 1000 行，3 列" → 返回给用户
```

**Agent 的本质就是一个循环：调 LLM → 看回复 → 有工具调用？执行 → 把结果喂回去 → 再调 LLM**。这个循环让 LLM 从"金鱼记忆"变成了"能自我纠错的执行者"。

#### 为什么循环有上限（max_turns）？

这是一个硬核的工程问题，不是学术问题。LLM 调用是按 token 收费的。如果你的 Agent 陷入死循环——比如 LLM 反复调用同一个工具但每次都失败——它会不停烧钱。

`max_turns` 是一个安全阀：最多循环 N 次，超过就停。默认 20 次已经非常慷慨了，大多数对话 3-5 轮就结束了。

面试时可以提到这个设计细节：它体现了"工程化思维"——不是只考虑 happy path，还考虑了 runaway cost。

#### 为什么 ToolRegistry 要和 Agent 分离？

看一下代码中的设计：

```python
class ToolRegistry:   # 只管工具
    def register(self, spec): ...
    async def execute(self, call): ...

class Agent:           # 只管对话
    def __init__(self, llm_client, ...):
        self.tools = ToolRegistry()  # 组合，不是继承
```

这是一个经典的**注册表模式（Registry Pattern）**。好处：

1. **单一职责**：ToolRegistry 不知道 Agent 的存在，Agent 不关心工具内部怎么实现
2. **可测试**：可以单独测 ToolRegistry 的注册/执行，不用启动整个 Agent
3. **可扩展**：未来如果要从配置文件或数据库动态加载工具，只改 ToolRegistry，Agent 一行不动

#### Message 类型的转换：为什么内部用 dataclass，外部用 dict？

看 `_build_openai_messages()` 这个方法：

```python
# 内部：类型安全的 dataclass
class Message:
    role: str
    content: str
    tool_calls: list[ToolCall] | None

# 外部：LLM API 要的是 dict
{"role": "user", "content": "hello"}
```

这是**内部模型与外部协议的隔离**。内部用 dataclass 获得类型安全和 IDE 补全；外发时转换成 API 要求的格式。如果 OpenAI 改了 API 格式（比如 field 改名），我们只改 `_build_openai_messages()`，其他代码不受影响。

---

### 2.2 Tool Call 执行：LLM 怎么"用"工具？

#### Function Calling 的底层机制

很多人以为 LLM "调用"了 Python 函数。不是的。实际流程是：

```
1. Agent 告诉 LLM："你有这些工具可用"（发 tool schemas）
2. LLM 回复："我想调用 sandbox_exec，参数是 code='print(1+1)'"（LLM 只返回 JSON）
3. Agent 解析这个 JSON，找到对应的 Python 函数，真正执行它
4. Agent 把执行结果（"2"）发回给 LLM
```

**LLM 不执行任何代码。它只是"建议"调用哪个工具。真正执行是 Agent 的 ToolRegistry 做的。**

这个区别非常重要——它意味着：
- LLM 不能访问你的文件系统（安全）
- 工具的实际执行逻辑完全在开发者控制中
- 你可以在工具 handler 里加任何安全检查、日志、限流

#### 消息格式的四种角色

OpenAI API 的对话消息有四种 role：

```
user:      用户说的话
assistant: LLM 的回复（文本 或 tool_call 请求）
tool:      工具执行的结果（必须关联到具体的 tool_call_id）
system:    系统级指令（定义 Agent 的行为边界）
```

我们通过 `Message` dataclass 的字段来支持这四种角色：

```python
@dataclass
class Message:
    role: str          # "user" | "assistant" | "tool"
    content: str
    tool_calls: list[ToolCall] | None = None   # assistant 可能发出 tool call
    tool_call_id: str | None = None            # tool 消息关联到具体 tool call
    name: str | None = None                    # 工具名称
```

#### 工具执行为什么不抛异常而是返回 ToolResult？

```python
async def execute(self, call: ToolCall) -> ToolResult:
    try:
        result = spec.handler(**call.arguments)
        return ToolResult(success=True, content=str(result))
    except Exception as e:
        return ToolResult(success=False, content=f"错误：{e}")
```

关键设计决策：**捕获所有异常，返回 ToolResult 而不是抛出**。

为什么？因为 Agent 需要在"工具失败了"这个信息的基础上继续运行。如果 tool execution 直接抛异常：
- Agent 崩溃，对话终止
- LLM 看不到错误信息，没法自我修正

返回 `ToolResult(success=False)` 后，Agent 把错误信息原样发回 LLM。LLM 看到 "name 'pd' is not defined"，自己意识到"哦，我忘了 import pandas"，然后生成修正代码。**这就是自我纠错能力的基础。**

---

### 2.3 State 状态管理：Agent 的"记忆系统"

#### Message History 不够用吗？

Agent 已经有了 `self.messages`（对话历史），为什么还需要 State？

对话历史是**给 LLM 看的**："用户说了什么，你回复了什么，工具返回了什么"。

State 是**给 Agent 自己用的**："现在执行到哪个阶段了，已经产生了哪些文件，沙箱里装了什么包"。

举个例子：

```
# LLM 视角（message history）：
User: "分析 sales.csv"
Assistant: 调用 sandbox_exec("pip install pandas")
Tool: "安装成功"

# Agent 视角（state）：
phase: "executing"
current_step: "install_dependencies"
context.packages_installed: ["pandas"]  ← 这个信息不在对话历史里！
```

对话历史不会记录 "pandas 已安装"——因为这个信息对于 LLM 对话来说是噪音。但 Agent 需要这个信息来避免重复安装。

#### 两层状态：AgentState vs ExecutionContext

```
AgentState（Agent 级别）           ExecutionContext（沙箱级别）
├── phase: "executing"            ├── packages_installed: ["pandas"]
├── current_step: "load_data"     ├── loaded_files: ["sales.csv"]
├── artifacts: {                  └── working_dir: "/tmp/ws"
│       "chart.png": {...}
│   }
```

**AgentState** 追踪"做什么"——宏观的任务进度。生命周期是整个对话。
**ExecutionContext** 追踪"有什么"——沙箱环境的状态快照。生命周期是单次任务执行。

为什么要分开？因为：
- AgentState 的内容适合展示给用户（"进度：第 2/4 步"）
- ExecutionContext 的内容适合注入 prompt（"当前环境：pandas 已安装，sales.csv 已加载"）
- 两者变化频率不同：phase 很少变，context 每次 tool call 都可能变

#### 为什么用 dataclass 而不是 dict？

```python
# dict 方式（坏）
state = {"phase": "executing"}
state["phase"]  # IDE 不知道这是什么类型，不会补全
state["phaze"]  # typo！运行时才发现

# dataclass 方式（好）
state = AgentState()
state.phase  # IDE 自动补全，mypy 检查类型
state.phaze  # mypy 直接报错，保存文件时就发现
```

同一个原因在 Phase 1.3 里讲过：把 bug 从运行时移到编码时。

---

### 2.4 Error Handler：让 Agent 像程序员一样读报错

#### 这个模块的设计哲学

普通程序的错误处理：

```python
try:
    do_something()
except Exception:
    log.error("失败了")
    sys.exit(1)  # 崩溃
```

Agent 的错误处理：

```python
try:
    do_something()
except NameError:
    # "变量没定义？我可能忘了 import。再执行一次试试。"
    → 重写代码
except MemoryError:
    # "内存不够？那我不全量加载了，分批处理。"
    → 降级策略
except PermissionError:
    # "权限问题？这个我真搞不定，告诉用户。"
    → 报告用户
```

**核心思想：Agent 面对错误时，不能崩溃。它要根据错误类型，像有经验的程序员一样判断严重程度和恢复策略。**

#### 三级严重度 + 四种恢复策略

```
ErrorSeverity（严重程度）            RecoveryAction（恢复策略）
├── RECOVERABLE (1)               ├── REWRITE_CODE
│   语法/类型错误 → 重写就行         │   改代码逻辑后重试
│                                  │
├── DEGRADE (2)                   ├── CHECK_CONTEXT
│   资源耗尽 → 换个方式             │   先看环境里有什么再决定
│                                  │
└── FATAL (3)                     ├── SIMPLIFY_TASK
    权限/未知 → 报告用户            │   换更简单的方法
                                   │
                                   └── REPORT
                                       承认搞不定，告知用户
```

为什么要分三级而不是两级（能恢复/不能恢复）？

因为 DEGRADE 是一个重要的中间态。`MemoryError` 既不是"改一下代码就好"也不是"完全没救"——它意味着"方法方向对了，但规模太大，换个方式就行"。如果只有两级，MemoryError 要么被当成 RECOVERABLE（盲目重试），要么被当成 FATAL（过早放弃），都不对。

#### MRO 遍历：为什么用 `__mro__` 而不是 `isinstance`？

```python
@classmethod
def classify(cls, error: BaseException):
    for exc_type in type(error).__mro__:
        if exc_type in cls._rules:
            return cls._rules[exc_type]
    return (ErrorSeverity.FATAL, RecoveryAction.REPORT)
```

用 `__mro__`（Method Resolution Order）遍历从最具体到最通用的异常类型：

```
FileNotFoundError.__mro__ = (
    FileNotFoundError,   → 先查这个（最具体）
    OSError,             → 再查这个
    Exception,           → 最后查这个
    BaseException,
    object
)
```

如果 `_rules` 里有 `FileNotFoundError` 的专门规则就用它；没有就退到 `OSError`；再没有就退到通用处理。这比 `isinstance` 更精确——你可以为 `FileNotFoundError` 和 `PermissionError` 写不同的规则，即使它们都是 `OSError` 的子类。

#### ClassVar 是什么？为什么这里要用？

```python
_rules: ClassVar[dict[...]] = {...}
```

`ClassVar` 是 typing 模块提供的一个标注，告诉 mypy："这个属性属于类，不属于实例"。

```python
# 没有 ClassVar：mypy 认为每个实例都有自己的 _rules
obj1._rules is obj2._rules  # mypy: 可能不同 → 报错

# 有 ClassVar：mypy 知道这是类级别共享的
obj1._rules is obj2._rules  # mypy: 永远是同一个 → 正确
```

在我们的场景中，`_rules` 是一个查找表，所有 ErrorClassifier 实例共享它就是合理的——错误分类规则不会因为不同实例而变化。

---

### 2.5 Planner：从"想到哪做到哪"到"有计划地执行"

#### 隐式规划 vs 显式规划

LLM 天生就有规划能力。你问它"怎么分析 sales.csv"，它会回答：

> "首先读取 CSV 文件，然后检查缺失值，接着分组统计，最后画图。"

这就是**隐式规划**——LLM 在自己的"脑海"里规划，每次回复里隐含了下一步。

问题在哪？**隐式规划不可观测、不可中断、不可恢复。**

- 用户看不到 Agent 现在做到哪一步了
- 如果第 3 步崩了，不知道前 2 步到底完成没有
- 不能在中间插入一个新的步骤

#### Planner 真正做的事情

Planner 把 LLM 的"内心想法"外化为一个状态机：

```
PENDING → ACTIVE → COMPLETED  (正常流程)
PENDING → ACTIVE → FAILED      (失败流程)
```

```
TaskPlan
├── goal: "分析 sales.csv"
├── steps:
│   ├── [PENDING]   load_data    → "读取 CSV 文件"
│   ├── [ACTIVE]    clean_data   → "清理缺失值"      ← 当前
│   ├── [PENDING]   analyze      → "分组统计"
│   └── [PENDING]   visualize    → "生成图表"
└── current_step → PlanStep("clean_data", ACTIVE)
```

**Planner 不替 Agent 做决策。它只是一个"进度记录器"。** LLM 负责决定"下一步做什么"，Planner 负责记住"已经做了哪些"。这个职责分离很重要：Planner 是确定性的状态机，LLM 是概率性的推理引擎——确定性的事让确定性组件处理。

#### StepStatus 为什么用 Enum 而不是字符串？

```python
class StepStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
```

如果用字符串：

```python
step.status = "done"    # typo！应该是 "completed"
step.status = "complet"  # 又一个 typo
```

用 Enum：

```python
step.status = StepStatus.COMPLETED  # IDE 自动补全，不会写错
step.status = StepStatus.DONE       # mypy 报错：StepStatus 没有 DONE
```

同样是"把运行时错误变成编码时错误"的原则。

#### 空计划的"真空真"陷阱

```python
def is_complete(self) -> bool:
    return len(self.steps) > 0 and all(
        s.status == StepStatus.COMPLETED for s in self.steps
    )
```

注意 `len(self.steps) > 0` 这个条件。如果只写 `all(...)` 会怎样？

Python 中 `all([])` 返回 `True`——这叫做"真空真"（vacuous truth）。空集合的"所有元素满足条件"在逻辑上为真。

但我们的语义是"没有任何步骤被完成"——空计划不应该算"完成"。所以显式加了 `len > 0` 的检查。这是一个经典的 Python 陷阱，面试时提出来会显得你对语言细节有深入理解。

---

### 2.6 Tool Router：帮 LLM 理解"什么时候用什么工具"

#### 这个模块不是 AI 路由器

首先要澄清一个容易误解的地方：ToolRouter **不替 Agent 做工具选择决策**。真正的工具选择是 LLM 通过 function calling 完成的——LLM 看到所有工具的 schema，自己判断该调用哪个。

ToolRouter 的职责更轻：
1. **生成工具说明**：把工具的用途用自然语言写清楚，注入到 system prompt 中
2. **提供启发式建议**：基于关键词匹配，给 Planner 一个初始的工具类别建议

#### 为什么需要 build_routing_prompt()？

OpenAI 的 function calling 机制本身就能让 LLM 知道有哪些工具。但我们额外生成一段自然语言说明，原因是：

LLM 看到 tool schema 是这样的：
```json
{
  "type": "function",
  "function": {
    "name": "sandbox_exec",
    "description": "Execute Python code in sandbox",
    "parameters": {...}
  }
}
```

这些信息分散在多个 JSON 对象里，LLM 需要自己"理解"每个工具的关系。而 `build_routing_prompt()` 生成的是连贯的自然语言：

```
使用指导：
- 需要运行代码或分析数据时，使用 sandbox_exec
- 需要读取或查看文件时，使用 file_list 或 file_read
- 任务完全完成时，调用 finish 交付结果
```

**Tool schema 告诉 LLM "有什么"，routing prompt 告诉 LLM "什么时候用什么"。** 两者互补。

---

### 2.7 集成：Agent + Planner + ErrorHandler = 完整引擎

#### 这个 Task 解决了什么问题？

前面 6 个 Task 各自构建了独立模块，每个都通过了单元测试。但 **"每个零件能转 ≠ 整台机器能跑"**。

集成测试要回答的问题是：**Agent 在真实场景中，Planner + ErrorHandler + Tool Call 这三者能协同工作吗？**

真实场景是这样的：

```
用户说："分析 sales.csv"
  ↓
Planner 生成步骤：[加载数据, 清洗, 分析, 可视化]
Agent 执行 step1 → 调 sandbox_exec → NameError: 'pd' not defined
  ↓
ErrorHandler 判断 → severity=RECOVERABLE, action=CHECK_CONTEXT
Agent 把错误 + 恢复提示发给 LLM → LLM 修正代码 → 重新执行
  ↓
成功 → Planner 标记 step1 完成 → 继续 step2...
```

#### 集成的三个改造点

**改造 1: Planner 注入进度信息**

```python
def _build_openai_messages(self):
    system_content = self.system_prompt
    if self.planner and len(self.planner.steps) > 0:
        system_content += "\n\n" + self.planner.to_progress_prompt()
```

在发给 LLM 的 system prompt 里追加进度信息：
```
Goal: 分析 sales.csv
Progress: Step 2/4 — 清理缺失值
```

这让 LLM 知道"我在做什么、做到哪了"，从而做出更准确的下一步决策。

**改造 2: ErrorHandler 附加恢复建议**

工具执行失败时，不只是把 raw 错误发给 LLM，而是用 ErrorClassifier 分类后附加结构化建议：

```
[工具执行失败]
错误: NameError: name 'pd' is not defined
严重程度: RECOVERABLE
建议恢复策略: CHECK_CONTEXT
提示: 先检查环境中是否有需要的变量/模块
```

**为什么这个设计很重要？** 普通的 Agent 把错误信息原样给 LLM，LLM 需要自己"猜"怎么办。我们的 Agent 把恢复建议结构化地告诉 LLM，让 LLM 的修正更精准、更少走弯路。

**改造 3: FATAL 级别错误立即终止**

```python
if severity.value >= 3:  # FATAL
    fatal_occurred = True
    # ... 给 LLM 最后一轮机会解释，然后退出
```

不是所有的错误都应该重试。权限错误（PermissionError）Agent 解决不了，强行重试只会烧 token。FATAL 级别的错误触发立即退出，节省成本。

#### 集成中踩的坑

**坑 1: ToolRegistry 丢失异常类型名**

原来的代码：
```python
except Exception as e:
    return ToolResult(content=f"错误：{e}")
```

`str(NameError("name 'x' is not defined"))` → `"name 'x' is not defined"` — 没有 "NameError"！

ErrorClassifier 的 regex 匹配不到，所有错误都被当成"未知错误"→ FATAL。

修复：
```python
exc_name = type(e).__name__
return ToolResult(content=f"{exc_name}: {e}")
# → "NameError: name 'x' is not defined"
```

**教训：错误信息的格式对下游组件很重要。** 异常对象携带了结构化信息（类型），但 `str()` 会丢失这些信息。在跨越组件边界时（ToolRegistry → ErrorClassifier），需要显式保留。

**坑 2: 计划步骤的完成时机**

原来的逻辑：每次工具执行后都标记 plan step 为完成。

问题：如果同一个 step 中工具执行失败（但非 FATAL），step 会被错误地标记完成。

修复：引入 `any_failure` 标志——只有本轮所有工具都成功，才推进计划步骤。

```python
any_failure = False
for tc in tool_calls:
    if not result.success:
        any_failure = True

if not any_failure and self.planner:
    self.planner.complete_current()
    self.planner.start_next()
```

#### 集成测试的结构

我们写了 3 组集成测试（共 6 个）：

| 测试组 | 测试内容 | 测试数 |
|--------|---------|--------|
| TestAgentWithPlanner | Planner 注入 prompt、空 planner 兼容、步骤推进 | 3 |
| TestAgentWithErrorHandler | 错误分类附加、FATAL 停止 | 2 |
| TestFullIntegration | 完整流程：plan→error→recover→complete | 1 |

每个测试都用 Mock LLM 客户端模拟真实的多轮对话，不需要真正的 API 调用。

#### 核心收获

1. **集成测试 ≠ 把单元测试跑一遍**。集成测试验证的是组件间的契约：Planner 更新了 step，Agent 的主循环会怎么反应？ErrorClassifier 返回了 FATAL，Agent 会停止吗？

2. **可选的依赖注入让系统灵活**。Planner 和 ErrorHandler 都是 `| None`，简单场景不传也不影响 Agent 工作。这是"渐进式复杂度"——用的时候加上，不用的时候无开销。

3. **错误信息的格式是隐式协议**。跨组件传递错误时，需要约定格式。`str(exception)` 不可靠，显式包含类型名是必要的。

---

### 2.8 LLM Client 增强：从“能跑”到“生产可用”

#### 先理解：为什么需要增强 LLM Client？

之前的 `OpenAIClient` 只是一个“最小可用”实现：构造一个 `httpx.AsyncClient`，发一个 POST 请求，拿到响应就返回。这在 demo 场景没问题，但拿到生产环境会立刻暴露三个问题：

1. **没有超时控制**：如果 LLM 服务端挂起，请求会永远等待，Agent 也会卡住。
2. **没有重试机制**：网络抖动、服务端 5xx 是常态，没有重试就意味着一次失败就任务失败。
3. **配置硬编码**：API Key、模型名、base_url 都只能通过构造函数传入，不方便部署和 CI。

生产级 LLM Client 需要像任何成熟 HTTP 客户端一样：可配置超时、自动重试、支持环境变量。

#### 核心设计

**三个新增能力：**

```
OpenAIClient
├── timeout          # 单次请求超时
├── max_retries      # 最大重试次数
├── backoff_factor   # 指数退避基数
├── from_env()       # 从环境变量读取配置
└── chat()           # 内部带重试循环
```

**重试策略：**

| 异常类型 | 状态码 | 是否重试 | 原因 |
|---------|--------|---------|------|
| HTTPStatusError | 5xx | ✅ | 服务端临时故障 |
| HTTPStatusError | 4xx | ❌ | 请求本身有问题，重试无用 |
| TimeoutException | — | ✅ | 临时网络/服务端慢 |
| NetworkError | — | ✅ | 连接失败等临时问题 |

**退避公式**：`backoff_factor * (2 ** attempt)`

第一次失败后等 0.5s，第二次等 1s，第三次等 2s。这种指数退避能避免在服务端故障时“雪崩式”重试。

#### 代码亮点

**1. 重试循环不耦合在 Agent 里**

```python
for attempt in range(self.max_retries + 1):
    try:
        return await self._do_chat_request(messages, tools, **kwargs)
    except Exception as exc:
        if self._should_retry(exc, attempt):
            await asyncio.sleep(self.backoff_factor * (2 ** attempt))
            continue
        raise
```

Agent 只关心“调用 chat() 拿到结果”；重试是 LLMClient 自己的事。职责分离让两边都可独立测试。

**2. 用 `_should_retry()` 集中决策**

把“什么情况下重试”抽成独立方法，而不是在循环里写一堆 `if`。未来如果要支持自定义重试策略（比如某些 429 也要重试），只需改这一个方法。

**3. `from_env()` 显式参数 + kwargs 覆盖**

```python
@classmethod
def from_env(
    cls,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
) -> OpenAIClient:
    final_api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
    final_model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4o")
    final_base_url = (
        base_url if base_url is not None
        else os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    return cls(api_key=final_api_key, model=final_model, base_url=final_base_url, **kwargs)
```

- 环境变量提供默认值
- 显式参数 `model` / `base_url` 优先级更高
- `kwargs` 可以覆盖 timeout、max_retries 等任意构造参数

#### 踩过的坑

**坑 1：mypy 对 `**dict[str, str]` 的报错**

最初想用一个 `dict` 收集环境变量，再 `update(kwargs)`，最后 `cls(**env_overrides)`。但 mypy 会报错：这个 dict 的值都是 `str`，而构造函数还需要 `int` 和 `float`。

修复：不用通用 dict，而是显式地从环境变量读取 `api_key` / `model` / `base_url`，再通过 `**kwargs` 传入其他参数。

**坑 2：测试重试时不要真的 sleep**

如果测试里真的等 0.5s、1s、2s，测试套件会变很慢。

修复：测试中设置 `backoff_factor=0.0`，这样 `asyncio.sleep(0)` 会立即返回，既验证了重试次数，又不拖慢测试。

#### 核心收获

1. **HTTP 客户端的可靠性是生产化的第一道门槛**。Agent 再聪明，如果调 LLM 动不动就失败，也无法实用。
2. **重试逻辑要自治**。把重试封装在 `OpenAIClient` 内部，Agent 和测试都不需要关心。
3. **用显式参数解决类型安全**。不要为了“通用”而用一个万能 dict，显式参数能让类型检查和 IDE 补全都生效。

---

### Phase 2 小结

Phase 2 构建了 Agent 的 8 个核心 Task（2.1-2.6 组件 + 2.7 集成 + 2.8 LLM Client 增强）。把它们放在一起看，你会发现一个清晰的架构模式：

```
用户输入
  ↓
Agent.run()  ← 主循环（2.1）
  ├── 对话历史 ← Message 类型（2.2）
  ├── 状态管理 ← AgentState + ExecutionContext（2.3）
  ├── 错误处理 ← ErrorClassifier（2.4）→ 2.7 集成
  ├── 任务规划 ← TaskPlan + PlanStep（2.5）→ 2.7 集成
  └── 工具路由 ← ToolRouter（2.6）
  ↓
LLM ← ToolRegistry（2.2）
```

每个模块的职责都是单一且清晰的。它们之间通过简单的接口（方法调用、返回值）通信，没有复杂的继承关系或全局状态。

**面试时可以这样描述这个架构："我设计了一个模块化的 Agent 引擎，核心是一个上下文驱动的决策循环。每个横切关注点——状态、错误恢复、任务规划、工具选择——都是独立的、可测试的组件。在 Phase 2.7 中，我把这些模块集成到主循环里：Planner 注入进度提示、ErrorHandler 对失败工具调用进行分级恢复建议、FATAL 错误立即终止。整个系统共有 85+ 个测试，全部通过，mypy strict 模式零错误。"**

---

## Phase 3：沙箱层 {#phase-3}

> **学习目标：** 理解 Docker 容器隔离、资源限制、安全边界——这是把 Agent 从"玩具"变成"生产工具"的关键一步。

### 3.1 Docker 连接与健康检查

#### 先理解：为什么需要沙箱？

Phase 2 的 Agent 已经能调用工具、规划任务、从错误中恢复。但它还缺一个至关重要的东西：**一个安全的地方来运行 LLM 生成的代码**。

为什么这很重要？因为 LLM 生成的代码可能：

1. **有死循环**：`while True: pass` 会占满 CPU
2. **有恶意操作**：`shutil.rmtree("/")` 会删除宿主机文件
3. **有资源泄漏**：创建大量临时文件或占用大量内存
4. **依赖外部网络**：访问不可信的 URL

如果直接在宿主机上执行这些代码，轻则任务失败，重则系统受损。所以我们需要一个**隔离的执行环境**：

| 隔离维度 | 需求 |
|---------|------|
| 进程隔离 | 代码跑在独立进程里，不影响宿主机 |
| 文件系统隔离 | 代码只能看到沙箱内的文件 |
| 网络隔离 | 可以控制是否允许访问外网 |
| 资源限制 | CPU、内存、执行时间都要可控 |

**Docker 容器是目前最合适的沙箱技术**：它提供进程、文件系统、网络和资源的隔离，同时启动速度比虚拟机快得多，非常适合 Agent 这种频繁创建/销毁执行环境的场景。

#### 核心设计

Phase 3.1 只解决三个最小问题：

```
DockerSandboxBackend
├── ping()           # Docker daemon 还活着吗？
├── ensure_image()   # 执行用的镜像已经准备好了吗？
└── close()          # 用完释放资源
```

**为什么先从"连接检查"开始？**

因为所有后续操作（创建容器、执行代码、销毁容器）都依赖 Docker daemon。如果连 daemon 都连不上，后面的一切都没有意义。把"连接"做成一个独立方法，也让错误处理更清晰：

```python
backend = DockerSandboxBackend()
if not await backend.ping():
    # 明确告诉用户：Docker 没启动，而不是某个神秘的操作失败
    raise RuntimeError("无法连接到 Docker daemon")
```

**为什么接口是 async 的？**

Agent 主循环是 async 的（`Agent.run()` 内部 await LLM 调用）。如果沙箱后端是同步的，调用 `docker pull` 这种可能耗时几十秒的操作会阻塞整个事件循环，导致 Agent 无法同时处理其他任务。

但 docker-py 本身是同步库。解决方案是：**接口保持 async，内部用 `asyncio.to_thread()` 把同步调用扔到线程池**。

```python
async def ping(self) -> bool:
    try:
        return bool(await asyncio.to_thread(self._client.ping))
    except Exception:
        return False
```

这样对外是 async 接口，对内复用了成熟的 docker-py，两全其美。

#### 代码亮点

**1. 把"同步 SDK"包成"异步接口"**

```python
images = await asyncio.to_thread(self._client.images.list, name=self.image)
if images:
    return True
await asyncio.to_thread(self._client.images.pull, self.image)
```

`asyncio.to_thread(func, *args)` 是 Python 3.9+ 的标准做法。它把阻塞调用放到默认线程池执行，返回一个 awaitable。这样主线程的事件循环不会被阻塞。

**2. 错误处理：不抛异常，返回 bool**

```python
async def ping(self) -> bool:
    try:
        return bool(await asyncio.to_thread(self._client.ping))
    except Exception:
        return False
```

为什么用 `bool` 而不是抛异常？

- 连接失败是**预期内的情况**（比如 Docker Desktop 没启动）
- 调用者可以根据返回值给出更友好的错误提示
- 测试更容易：不需要 mock 异常类型，只需断言 `False`

这和 `OpenAIClient` 的重试策略形成对比：那边是"失败了就重试"，这边是"失败了就报告"，因为沙箱连接问题不是靠重试能解决的。

**3. 资源释放用 context manager**

```python
async with DockerSandboxBackend() as backend:
    if await backend.ping():
        await backend.ensure_image()
```

docker-py 的 client 持有 TCP/命名管道连接，用完后要 `close()`。提供 `async with` 支持可以避免调用者忘记释放资源。

#### 踩过的坑

**坑 1：docker-py 的 `images.list(name=...)` 匹配规则**

`docker.from_env().images.list(name="python:3.11-slim")` 会按镜像名过滤。如果镜像存在但 tag 不匹配（比如只有 `python:3.11`），可能返回空列表。Phase 3.1 暂时按完整镜像名匹配；Phase 3.2 执行时如果镜像不存在会由 `ensure_image()` 自动拉取。

**坑 2：async fixture 和 sync mock 的混用**

测试中 `mock_client` 是一个 sync fixture，但测试函数是 `async def`。pytest-asyncio 会自动处理事件循环，sync fixture 在测试前同步执行。只要 fixture 里用 `patch` 把 `docker.from_env()` 替换成返回 mock 的函数，测试函数里新建的 `DockerSandboxBackend` 实例就会拿到这个 mock client。

**坑 3：Windows 上 Docker Desktop 没启动时所有测试都会失败**

为了避免这个问题，Phase 3.1 的测试**全部 mock docker-py**，不依赖真实 Docker。真实 Docker 连接只在手动验证脚本或集成测试中使用。

#### 核心收获

1. **沙箱是 Agent 的安全底线**。没有沙箱，Agent 就是直接在宿主机上运行不可信代码，无法生产化。
2. **asyncio.to_thread() 是桥接 sync SDK 和 async 接口的标准解法**。不需要把同步库重写成 async，也能保持事件循环不被阻塞。
3. **"连接检查"应该独立成方法**。它是最前置、最基础的健康检查，能为后续所有操作提供清晰的失败原因。
4. **测试要隔离真实依赖**。Docker 可能没启动、网络可能不通，单元测试不能依赖这些外部状态。

### 3.2 容器创建与销毁

#### 先理解：为什么要把"创建容器"单独作为一个 Task？

Phase 3.1 已经能连接 Docker 并准备镜像了。你可能会想："那直接执行代码不就行了？"但 Docker 里执行代码有一个关键前提：**必须先有一个正在运行的容器**。

沙箱执行的典型模式是：

```
创建容器 → 在容器内 exec 执行代码 → 获取结果 → 销毁容器
```

为什么用长期运行的容器而不是 `docker run --rm`？

1. **状态可复用**：容器启动后可以保留已安装的包、已写入的文件，Agent 可以分多步执行代码。
2. **执行效率高**：`docker exec` 比反复 `docker run` 启动新容器更快。
3. **便于调试**：容器没销毁前，可以进去查看环境状态。

所以 Phase 3.2 的责任就是：**安全地创建和销毁容器**，不牵涉具体代码执行。

#### 核心设计

新增三个接口：

```
DockerSandboxBackend
├── create_container(command="tail -f /dev/null") → Container | None
├── remove_container() → bool
└── container_id → str | None
```

**容器创建策略：**

- 使用默认命令 `tail -f /dev/null` 让容器长期存活
- `detach=True` 让容器在后台运行
- `stdin_open=True` 为后续 `exec_run` 预留交互能力
- 创建新容器前，如果已存在旧容器，先 `remove_container()` 防止泄漏

**容器销毁策略：**

- 先 `stop()` 再 `remove()`
- 幂等：没有容器时返回 True
- `close()` 和 `__aexit__` 都会触发清理

#### 代码亮点

**1. 创建前自动清理旧容器**

```python
async def create_container(self, ...) -> Container | None:
    await self.remove_container()  # 防止资源泄漏
    container = await asyncio.to_thread(
        client.containers.create,
        image=self.image,
        command=command,
        detach=True,
        stdin_open=stdin_open,
        tty=tty,
    )
    await asyncio.to_thread(container.start)
    self._container = container
    return container
```

这个设计避免了"忘记关容器"导致的垃圾容器堆积。Agent 可能在一次任务中反复创建沙箱，每次创建前先清理，保证系统干净。

**2. 同步 close() 与异步 remove_container() 的分工**

```python
def close(self) -> None:
    # 同步路径：方便非 async 上下文快速释放资源
    if self._container is not None:
        try:
            self._container.stop()
            self._container.remove()
        except Exception:
            pass
        self._container = None
    if self._client is not None:
        self._client.close()
        self._client = None

async def __aexit__(self, *args: Any) -> None:
    # 异步路径：async with 退出时优雅清理
    await self.remove_container()
    self.close()
```

`close()` 是 sync 接口，方便在任意地方调用；`__aexit__` 走 async 路径，更优雅、不会阻塞事件循环。两者都确保容器和 client 被释放。

**3. 用 `container_id` 属性提供只读访问**

```python
@property
def container_id(self) -> str | None:
    if self._container is None:
        return None
    return cast(str, self._container.id)
```

外部调用者不需要直接操作 `_container` 对象，只需通过 `container_id` 获取标识。这是封装的基本原则：内部实现可以变，但接口保持稳定。

#### 踩过的坑

**坑 1：mypy 对 `Container.id` 的 Any 推断**

docker-py 的 `Container.id` 类型标注不完整，mypy 会把它推断为 `Any`，导致 `no-any-return` 错误。

修复：用 `typing.cast(str, self._container.id)` 明确告诉 mypy 返回类型。

**坑 2：MagicMock 的 `container.id` 赋值**

测试里用 `MagicMock(spec=Container)` 模拟容器，但 `id` 是 Python 内置函数名，直接 `mock_container.id = "abc123"` 可以工作，因为 MagicMock 允许属性赋值。但如果用普通对象可能会有冲突。这里选择 MagicMock 是为了灵活打桩。

**坑 3：`close()` 里同步调用 stop/remove 是否安全？**

`close()` 是 sync 方法，如果调用者已经在 async 事件循环里，调用 `self._container.stop()` 会阻塞循环。但我们把它定位为"便捷但非最佳"的释放入口；在 async 上下文中，推荐用 `async with` 或 `await backend.remove_container()`。

#### 核心收获

1. **容器是沙箱的"执行现场"**。创建容器是为代码执行准备隔离环境，销毁容器是防止资源泄漏。
2. **幂等性让接口更健壮**。`remove_container()` 无论有没有容器都能安全调用，上层逻辑更简单。
3. **同步/异步双路径释放**能适应不同调用场景，但 async 路径永远是首选。
4. **docker-py 的类型标注不完整**，遇到 `Any` 推断时要用 `cast` 显式标注，保证 mypy strict 模式通过。

---


### 3.3 代码执行与结果捕获

#### 先理解：为什么需要专门的结果捕获机制？

Phase 3.2 已经能创建容器了。但容器本身不会告诉我们代码执行得怎么样——它只运行着一个 `tail -f /dev/null` 进程。要真正让 Agent 能写代码、跑代码、看结果，我们需要解决三个问题：

1. **怎么把代码送进容器？**
2. **怎么在容器内执行它？**
3. **怎么把 stdout / stderr / exit_code 拿回来？**

这三个问题合起来，就是 Phase 3.3 的核心：**代码执行与结果捕获**。

#### 核心设计

新增两个核心概念：

```
ExecutionResult
├── exit_code: int    # 0 成功，非零失败，-1 执行前失败
├── stdout: str       # 标准输出
├── stderr: str       # 标准错误
└── success: bool     # exit_code == 0

DockerSandboxBackend
└── execute_code(code: str, timeout: int | None) -> ExecutionResult
```

**执行流程：**

```
execute_code(code)
  ↓
没有容器？→ create_container()
  ↓
base64 编码 code
  ↓
container.exec_run("python -c 'exec(base64.b64decode(...))'")
  ↓
解析 (exit_code, (stdout_bytes, stderr_bytes))
  ↓
返回 ExecutionResult
```

#### 代码亮点

**1. 用 base64 解决命令行转义问题**

直接把代码塞进 `python -c "..."` 会遇到引号转义噩梦：

```python
# 如果 code 里有双引号，直接拼接会失败
command = f'python -c "{code}"'
```

更 robust 的做法是先把代码 base64 编码，再在容器里解码执行：

```python
encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
command = f"python -c \"import base64; exec(base64.b64decode('{encoded}'))\""
```

这样无论 code 里有什么引号、换行、特殊字符，都能安全传递。

**2. 自动创建容器**

```python
container = self._container
if container is None:
    container = await self.create_container()
    if container is None:
        return ExecutionResult(
            exit_code=-1,
            stdout="",
            stderr="Failed to create container",
            success=False,
        )
```

上层调用者不需要先手动 `create_container()`，直接 `execute_code()` 即可。这降低了使用门槛，也符合"沙箱后端自我管理"的设计。

**3. `demux=True` 分离 stdout 和 stderr**

docker-py 的 `exec_run` 默认把 stdout 和 stderr 混在一起返回。设置 `demux=True` 后，返回值变成：

```python
(exit_code, (stdout_bytes, stderr_bytes))
```

这样 Agent 能清楚区分"正常输出"和"错误输出"，对错误恢复很重要。

**4. 错误全部收敛到 ExecutionResult**

无论是 Docker client 不可用、容器创建失败、执行超时，还是 exec 本身失败，都不抛异常，而是返回 `success=False` 的 `ExecutionResult`。这让上层 Agent 可以统一处理结果，而不是写一堆 `try/except`。

#### 踩过的坑

**坑 1：`exec_run` 返回的 output 类型不固定**

`demux=True` 时 output 是 tuple，但如果不小心没传 `demux`，output 就是 bytes。为了防御性编程：

```python
stdout_bytes, stderr_bytes = (
    output if isinstance(output, tuple) else (output, b"")
)
```

**坑 2：bytes 解码可能失败**

如果代码输出二进制内容或非 UTF-8 字符，`.decode("utf-8")` 会抛 `UnicodeDecodeError`。

修复：使用 `errors="replace"`，把无法解码的字节替换为 `�`，保证不中断。

**坑 3：同步 close 与容器内正在运行的 exec 的竞态**

`close()` 是同步方法，如果此时容器内正有一个 `exec_run` 在执行，直接 stop/remove 容器可能导致结果不完整。这个风险在 Phase 3.3 测试中用 mock 隔离了；生产环境中建议 async 上下文优先使用 `async with` 或显式 `await remove_container()`。

#### 核心收获

1. **代码执行沙箱的接口设计要尽量简单**：调用者只关心 `code → ExecutionResult`。
2. **base64 是跨进程传递代码的可靠方式**，比引号转义安全得多。
3. **stdout/stderr/exit_code 是 Agent 自我纠错的三要素**：LLM 需要根据它们判断代码是否成功、如何修复。
4. **把所有失败收敛到返回值中**，比抛异常更适合 Agent 这种需要"看结果再决策"的场景。


### 3.4 安全限制

#### 先理解：为什么沙箱不能只是"能跑代码"？

Phase 3.3 已经能让代码在容器里跑了。但"能跑"和"敢跑"是两回事。LLM 生成的代码可能：

1. **死循环或无限递归**：`while True: pass` 占满 CPU
2. **大内存分配**：`[0] * 10**10` 耗尽宿主机内存
3. **网络攻击**：访问恶意 URL、下载病毒
4. **破坏文件系统**：`shutil.rmtree("/")` 或覆盖系统文件
5. **提权操作**：以 root 身份执行敏感命令

如果没有任何限制，这个 Agent 就是一个定时炸弹。**安全限制不是可选项，是生产化的前提。**

#### 核心设计

我们在 `create_container()` 中通过 Docker 原生能力施加四层限制：

```
DockerSandboxBackend.create_container(...)
├── memory_limit: str | None      # cgroup 内存限制
├── network_mode: str | None = "none"  # 默认无网络
├── user: str | None = "nobody"        # 非 root 用户
└── read_only: bool = True             # 根文件系统只读 + tmpfs 可写 /tmp
```

**为什么是这四层？**

| 限制 | 防护对象 | Docker 参数 |
|---|---|---|
| 内存限制 | 大内存分配、OOM | `mem_limit` |
| 网络隔离 | 外网访问、数据外泄 | `network_mode="none"` |
| 非 root 用户 | 提权、系统文件操作 | `user="nobody"` |
| 只读根文件系统 | 恶意删除/修改容器内系统文件 | `read_only=True` + `tmpfs` |

#### 代码亮点

**1. 默认即安全**

```python
async def create_container(
    self,
    command: str = "tail -f /dev/null",
    memory_limit: str | None = None,
    network_mode: str | None = "none",
    user: str | None = "nobody",
    read_only: bool = True,
    tmpfs: dict[str, str] | None = None,
) -> Container | None:
```

默认参数不是"最方便"，而是"最安全"。调用者必须显式覆盖才能放宽限制，这种设计能防止"忘记设限"导致的安全事故。

**2. 只读根文件系统 + tmpfs**

```python
if tmpfs is not None:
    create_kwargs["tmpfs"] = tmpfs
elif read_only:
    create_kwargs["tmpfs"] = {"/tmp": "rw,noexec,nosuid,size=64m"}
```

根文件系统只读，但代码执行需要写临时文件（比如 matplotlib 输出图片）。所以我们在 `/tmp` 挂载一个 tmpfs，特点是：

- 可写：满足临时文件需求
- `noexec`：不能执行二进制
- `nosuid`：不能通过 setuid 提权
- `size=64m`：限制大小

**3. timeout 默认值从 backend 配置流入执行**

```python
self.timeout: int = timeout
...
effective_timeout = timeout if timeout is not None else self.timeout
exec_kwargs["timeout"] = effective_timeout
```

`DockerSandboxBackend` 持有默认 timeout，`execute_code()` 可以覆盖。这样上层 Agent 只需要在创建 backend 时配置一次 timeout，所有执行都自动继承。

#### 踩过的坑

**坑 1：`python:3.11-slim` 镜像里的 `nobody` 用户**

大多数 Linux 镜像都有 `nobody` 用户（UID 65534），权限极低。但如果镜像里没有这个用户，`container.start()` 会失败。

修复方向（未来）：允许通过 `user` 参数指定其他用户，或在自定义镜像中创建专用沙箱用户。

**坑 2：`read_only=True` 时 Python 无法写 `.pyc` 缓存**

Python 导入模块时会尝试写 `__pycache__`。在只读根文件系统上，这会产生警告但不致命（Python 会忽略写入失败）。如果希望完全干净，可以设置 `PYTHONDONTWRITEBYTECODE=1`。

**坑 3：网络隔离与 pip 安装冲突**

默认 `network_mode="none"` 会阻止容器访问外网。如果 LLM 要安装新包，必须先显式开启网络。这个权衡是必要的：默认安全，需要网络时由 Agent 主动请求。

#### 核心收获

1. **安全默认比安全选项更重要**。默认就开启的限制，比让用户勾选的安全选项更有效。
2. **Docker 容器不是天然安全的**。必须显式配置内存、网络、用户、文件系统权限。
3. **每一层限制只解决一类问题**。多层叠加才能形成有效防护。
4. **安全策略需要可覆盖**。完全禁止网络会限制功能，所以通过参数让调用者在必要时放宽。


### 3.5 文件注入与提取

#### 先理解：为什么代码沙箱需要文件操作？

Phase 3.3 已经能执行代码了，但执行的是"裸代码"——没有输入数据，也没有输出文件。真实的 Agent 任务往往需要：

1. **输入数据**：用户给了一个 `sales.csv`，Agent 要读取它进行分析
2. **输出产物**：Agent 生成了 `chart.png` 或 `report.json`，要交付给用户
3. **中间文件**：代码执行过程中需要写入临时数据，供后续步骤使用

如果没有文件注入/提取能力，Agent 就只能在 stdout 里塞所有东西，既不实用也无法处理二进制文件。**文件操作是沙箱从"玩具"变成"生产力工具"的关键。**

#### 核心设计

我们提供两个方法：

```
DockerSandboxBackend
├── put_file(container_path, content: bytes) -> bool
└── get_file(container_path) -> bytes | None
```

**实现方式：tar 归档 + Docker API**

Docker 提供了两个原语：
- `container.put_archive(path, data)`：把 tar 格式的数据解压到容器内 `path` 目录
- `container.get_archive(path)`：把容器内 `path` 文件打包成 tar 返回

为什么用 tar？

1. **原子性**：一次调用可以传整个目录结构
2. **权限保留**：tar 可以保留文件权限、时间戳
3. **官方支持**：docker-py 原生支持，不需要在容器内额外安装工具

**注入流程：**

```
content: bytes
  ↓
打包成 tar（文件名 = container_path 的 basename）
  ↓
put_archive(parent_dir, tar_bytes)
  ↓
容器内出现目标文件
```

**提取流程：**

```
container_path
  ↓
get_archive(container_path) → (tar_stream, stat)
  ↓
读取 tar_stream 并合并 chunks
  ↓
解压 tar，读取第一个文件内容
  ↓
返回 bytes
```

#### 代码亮点

**1. put_file 自动拆分目录和文件名**

```python
parent_dir = os.path.dirname(container_path) or "/"
filename = os.path.basename(container_path)
```

`put_archive` 的 `path` 参数是目标目录，不是文件路径。所以我们把 `/tmp/data.csv` 拆成 `/tmp` 和 `data.csv`，tar 里只放 `data.csv`，解压后自然落在 `/tmp/data.csv`。

**2. 无容器时自动创建**

```python
container = self._container
if container is None:
    container = await self.create_container()
    if container is None:
        return False
```

和 `execute_code()` 保持一致：调用者不需要关心容器是否存在，backend 自己管理。

**3. get_file 处理 generator 返回的 tar 流**

```python
data, _stat = await asyncio.to_thread(container.get_archive, container_path)
chunks = list(data)
tar_bytes = b"".join(chunks)
```

`get_archive` 返回的 `data` 是生成器，yielding chunks。我们把它转成列表再合并，就能得到完整的 tar 字节流。

**4. 失败返回 None / False**

- `put_file` 失败返回 False
- `get_file` 失败返回 None

这样上层 Agent 可以统一判断：

```python
content = await backend.get_file("/tmp/output.png")
if content is None:
    # 文件不存在或读取失败，告诉 LLM
```

#### 踩过的坑

**坑 1：tar 文件名必须和 basename 一致**

如果把 `/tmp/data.csv` 作为 tar 里的文件名，`put_archive("/", tar)` 会把它放到 `/tmp/data.csv`，但前提是 tar 里的路径包含完整目录。更安全的做法是：tar 里只放 `data.csv`，`put_archive("/tmp", tar)`。

**坑 2：`get_archive` 返回的 tar 里只有一个文件**

当 `path` 是文件路径时，返回的 tar 里只有一个成员，就是我们请求的文件。但如果 `path` 是目录，返回的 tar 里会有多个成员。当前实现只读取第一个成员，适用于文件提取场景。

**坑 3：大文件的内存问题**

当前实现把整个 tar 流读入内存。对于大文件（比如几百 MB 的数据集），未来可以考虑流式处理或限制文件大小。Phase 3.5 先保证功能正确，性能优化留给 Phase 3.6 预热池或后续迭代。

#### 核心收获

1. **文件操作让沙箱能处理真实任务**。输入数据、输出产物、中间文件都需要它。
2. **Docker 的 tar API 是文件注入/提取的最可靠方式**。比 `docker cp` CLI 更可控，比 base64 编码更适合二进制文件。
3. **目录/文件路径的拆分要小心**。`put_archive` 接收的是目录，`get_archive` 接收的是文件路径。
4. **和 `execute_code()` 保持一致的失败语义**：put 返回 bool，get 返回 Optional[bytes]。


### 3.6 容器预热池（轻量版）

#### 先理解：为什么要预热容器？

Phase 3.3-3.5 已经能执行代码、传文件、取文件了。但你注意到没有：每次 `execute_code()` 都要先 `create_container()`，而容器创建是**秒级开销**。

对于 Agent 来说，一次任务可能要连续执行很多段代码：

```
加载数据 → 清洗数据 → 分析数据 → 可视化 → 保存结果
```

如果每段代码都要等 1-3 秒创建容器，整体体验会非常卡顿。**预热池的核心思想是：提前创建好一批容器放着，用的时候直接拿。**

#### 核心设计

我们做了一个轻量版预热池，内嵌在 `DockerSandboxBackend` 中：

```
DockerSandboxBackend
├── _pool: list[Container]       # 空闲容器池
├── warmup(count) -> bool        # 预创建 count 个容器
├── _acquire_container()         # 从池取，池空则新建
└── _release_and_replenish()     # 销毁用完的容器，补充新容器
```

**为什么采用"一次一容器"策略？**

容器复用最大的问题是**污染**：
- Task A 安装了 `pandas`，Task B 不希望有 `pandas`
- Task A 写了 `/tmp/secret.txt`，Task B 可能读到

处理污染需要复杂的清理逻辑。轻量版方案选择**用一次就销毁，但立即补充一个新容器到池中**。这样：

- 每次执行仍然用干净的容器
- 池里始终有 N 个预热的容器待命
- 下一次执行时直接从池取，无需等待创建

#### 代码亮点

**1. 职责分离：`_do_create_container()`**

我们把容器创建的核心逻辑抽到私有方法 `_do_create_container()`，这样：

```python
# create_container() 管理 self._container
async def create_container(self, ...):
    await self.remove_container()
    container = await self._do_create_container(...)
    self._container = container
    return container

# 预热池也复用同一套创建逻辑
async def warmup(self, count):
    for _ in range(count):
        container = await self._do_create_container()
        self._pool.append(container)
```

避免了两套创建逻辑重复。

**2. `_acquire_container()` 优先从池取**

```python
async def _acquire_container(self) -> Container | None:
    if self._pool:
        return self._pool.pop()
    return await self._do_create_container()
```

池里有就直接 pop，没有才新建。这是性能优化的核心。

**3. `_release_and_replenish()` 保持池大小稳定**

```python
async def _release_and_replenish(self, container: Container) -> None:
    try:
        await asyncio.to_thread(container.stop)
        await asyncio.to_thread(container.remove)
    except Exception:
        pass

    replacement = await self._do_create_container()
    if replacement is not None:
        self._pool.append(replacement)
```

执行完后：
1. 销毁旧容器（避免污染）
2. 异步创建新容器补充到池中

这样池的大小始终保持稳定，下次执行时容器已经准备好。

**4. `execute_code()` 的 finally 保证释放**

```python
container: Container | None = None
try:
    container = await self._acquire_container()
    # ... 执行代码 ...
finally:
    if container is not None:
        await self._release_and_replenish(container)
```

无论执行成功还是失败，容器都会被释放和补充，避免泄漏。

#### 踩过的坑

**坑 1：补充逻辑让测试断言变复杂**

原来的测试假设 `execute_code()` 只创建一次容器。加入池后，执行完会再创建一次补充容器，导致 `containers.create.call_count` 变成 2。

修复：更新测试断言，明确说明"创建 + 补充"的预期行为。

**坑 2：`container_id` 不再反映执行用容器**

以前 `execute_code()` 会把容器赋给 `self._container`，现在执行用的容器是临时的，执行完就释放。所以 `container_id` 只反映显式 `create_container()` 创建的容器。

这是设计选择：执行用的容器由池管理，不暴露给上层。

**坑 3：池大小和内存占用**

每个 running 容器都占内存。如果 size=2，大约占 100-200MB。实际部署时需要根据机器资源和并发量调整。

#### 核心收获

1. **预热池是性能优化，不是功能必需**。先保证功能正确，再考虑性能。
2. **"用后即弃 + 异步补充"是轻量且安全的策略**。避免了容器污染问题。
3. **把创建逻辑抽到私有方法，让池和公开 API 复用同一套逻辑**，避免重复代码。
4. **性能优化的测试要更新断言**，因为调用次数会变多。

---


### Phase 3 小结

Phase 3 的六个 Task 完成了一个**生产可用的 Docker 沙箱执行层**：

```
连接 Docker → 准备镜像 → 创建容器 → 施加安全限制 → [预热池] → 注入文件 → 执行代码 → 提取文件 → 捕获结果
   3.1          3.1         3.2           3.4            3.6        3.5        3.3         3.5        3.3
```

六个 Task 的分层原则：

1. **3.1 连接层**：Docker daemon、镜像就绪。
2. **3.2 环境层**：创建并维护容器实例。
3. **3.4 安全层**：内存、网络、用户、文件系统、seccomp 限制。
4. **3.5 文件层**：把外部数据传入沙箱，把产物取出沙箱。
5. **3.3 执行层**：在隔离环境中运行代码，捕获 stdout/stderr/exit_code。
6. **3.6 性能层（可选）**：预热池减少容器创建延迟。

**这个设计的面试价值**：

> "我实现了一个模块化的 Docker 沙箱执行层，包含连接、镜像准备、容器创建、安全限制、文件注入提取、代码执行六个阶段。安全策略采用'默认即安全'设计，包括无网络、非 root、只读根文件系统、内存限制和可扩展的 seccomp。文件操作通过 Docker 原生 tar API 实现。为了优化性能，我还实现了一个轻量容器预热池，采用'用后即弃 + 异步补充'策略，在保证容器干净的同时减少执行等待时间。"

接下来 Phase 4 会把这个沙箱层封装成 Agent 可调用的 Tool。



---

### Phase 4.1: sandbox_exec Tool

#### 先理解：这个模块解决什么问题

Phase 3 我们搭好了一个能跑 Python 代码的 Docker 沙箱，但它对 Agent 来说还是“底层能力”——Agent 主循环并不直接认识 `DockerSandboxBackend.execute_code()`。LLM 能调用的东西必须是 `ToolSpec` 描述的工具。

所以 Phase 4.1 要解决的问题是：**如何把沙箱执行能力封装成 LLM 可调用的 Tool？**

封装成 Tool 有两个好处：
1. **统一接口**：Agent 不需要知道沙箱内部是 Docker、K8s 还是本地子进程，它只看到 `sandbox_exec(code)`。
2. **自我纠错**：执行失败时把 stderr 返回给 LLM，LLM 能根据错误信息修正代码再试一次。这是“代码沙箱 Agent”最核心的闭环。

#### 核心设计

```
LLM tool_call(sandbox_exec, {"code": "..."})
            ↓
ToolRegistry.execute() 调用 handler
            ↓
sandbox_exec(code, backend)  await backend.execute_code(code)
            ↓
DockerSandboxBackend 管理容器、执行、返回 ExecutionResult
            ↓
sandbox_exec 把 ExecutionResult 转成 ToolResult(success, content)
            ↓
Agent 把 ToolResult 追加到对话历史，进入下一轮
```

关键类型：
- `ExecutionResult`：沙箱层的原始结果（exit_code / stdout / stderr / success）。
- `ToolResult`：Agent 层的结果（tool_call_id / content / success）。

`sandbox_exec` 是两者之间的适配器。

#### 代码亮点

**1. 用 `functools.partial` 绑定后端**

`ToolRegistry.execute()` 调用 handler 时只传 `**call.arguments`，也就是只有 `code`。但 `sandbox_exec` 还需要 `backend`。我们用 `partial(sandbox_exec, backend=backend)` 把后端预先绑定，注册出来的 handler 签名只剩 `code`，完全匹配 Tool 调用约定。

```python
from functools import partial

registry.register(
    ToolSpec(
        name="sandbox_exec",
        ...,
        handler=partial(sandbox_exec, backend=backend),
    )
)
```

**2. `ToolRegistry.execute()` 支持异步 handler 和 `ToolResult`**

原来的 `execute()` 假设 handler 是同步的，并且返回任意可字符串化的结果。但沙箱执行是异步的，而且我们需要把 `success=False` 传回给 Agent。

改造后的逻辑：
- 如果 handler 返回 coroutine，先 `await`。
- 如果返回的是 `ToolResult`，直接复用 `content` 和 `success`，只补全 `tool_call_id`。
- 否则按原来的字符串化逻辑处理。

这样同步工具（如 `add`）和异步工具（如 `sandbox_exec`）可以共存。

**3. Agent 默认加载沙箱工具**

`Agent.__init__` 现在接受可选的 `sandbox_backend` 参数，未传入时创建默认后端，并调用 `register_default_tools()`。这样新建一个 Agent 就自动具备代码执行能力，符合“代码沙箱 Agent”的默认预期。

#### 踩过的坑

**坑 1：默认注册与旧集成测试冲突**

Phase 2.7 的集成测试里手动注册了一个 mock 版的 `sandbox_exec`。现在 Agent 默认就注册了同名工具，如果测试再手动注册会触发 `ValueError("工具已注册")`。

修复：把集成测试改为通过 `sandbox_backend=MockSandboxBackend(...)` 注入 mock 后端，而不是手动覆盖工具。这样同时验证了“默认加载”路径。

**坑 2：异步 handler 不能直接返回 coroutine**

最初没改造 `ToolRegistry.execute()` 时，异步 handler 返回的 coroutine 被 `str()` 成了 `<coroutine object ...>`，工具永远“成功”但内容是个内存地址。

修复：在 `execute()` 里加 `asyncio.iscoroutine(result)` 判断，确保 coroutine 被真正执行。

**坑 3：handler 返回 `ToolResult` 时 tool_call_id 要补全**

handler 内部拿不到 `ToolCall.id`，所以返回的 `ToolResult.tool_call_id` 是空字符串。`ToolRegistry.execute()` 拿到后必须替换成当前调用的 id，否则对话历史会乱。

#### 核心收获

1. **Tool 是 LLM 与系统能力之间的接口**：沙箱再强，也要包成 Tool 才能被 LLM 调用。
2. **适配器模式**：`sandbox_exec` 只做“参数转换 + 结果映射”，不碰 Docker 细节。
3. **注册时绑定依赖，调用时保持简单**：`partial` 是处理“注册时已知依赖、调用时只传参数”的优雅方式。
4. **执行失败不是异常，而是正常结果**：通过 `ToolResult.success=False` 把错误暴露给 LLM，让 Agent 能自我纠错。
5. **扩展执行引擎要兼顾旧工具**：支持异步和 `ToolResult` 时，不能破坏同步 handler 的行为。

---



---

### Phase 4.2: file_read / file_list Tools

#### 先理解：这个模块解决什么问题

Phase 4.1 让 Agent 能在沙箱里执行代码了，但执行完之后 LLM 怎么知道产生了什么？比如 Agent 执行：

```python
with open("/tmp/result.txt", "w") as f:
    f.write("hello")
```

接下来 LLM 需要：
1. **确认文件是否存在** → `file_list`
2. **读取文件内容** → `file_read`

所以 Phase 4.2 要解决的问题是：**让 Agent 能看见沙箱里的文件系统**，把沙箱从黑盒执行器变成可观察的工作空间。

这是 Agent 自我纠错闭环的重要一环：执行代码 → 观察产物 → 决定下一步。

#### 核心设计

```
LLM tool_call(file_list, {"path": "/tmp"})
            ↓
file_list(path, backend) → backend.execute_code("os.listdir('/tmp')")
            ↓
DockerSandboxBackend 在容器内执行代码，返回 stdout
            ↓
file_list 解析 JSON，转成换行列表，包装成 ToolResult

LLM tool_call(file_read, {"path": "/tmp/result.txt"})
            ↓
file_read(path, backend) → backend.get_file("/tmp/result.txt")
            ↓
DockerSandboxBackend 从容器提取文件 bytes
            ↓
file_read 解码为 UTF-8 文本，包装成 ToolResult
```

两个工具都遵循 Phase 4.1 建立的模式：
- 不直接碰 Docker，调用后端已有 API。
- 失败时不抛异常，返回 `ToolResult(success=False)`，让 LLM 看到错误。

#### 代码亮点

**1. `file_list` 用 `execute_code()` 间接实现列表**

沙箱后端没有专门的 `list_files()` API。如果为了这一个功能去扩展后端，会引入新的抽象和测试。我们选择复用已经稳定的 `execute_code()`，在容器内执行：

```python
import json, os
path = "/tmp"
print(json.dumps(os.listdir(path)))
```

这样做的好处：
- 不修改 Phase 3 沙箱层，降低回归风险。
- 用 `json.dumps()` 对路径做安全转义，避免引号注入。
- 返回结构化数据，工具层再转成 LLM 易读的文本。

**2. `file_read` 只做解码和错误包装**

`DockerSandboxBackend.get_file()` 返回 `bytes | None`。工具层负责：
- `None` → 文件不存在，返回失败。
- `bytes` → UTF-8 解码，返回文本内容。

这种后端管 IO、工具管呈现的分层让两边都保持简单。

**3. 默认工具集扩展**

`register_default_tools()` 现在注册三个工具：
- `sandbox_exec`
- `file_read`
- `file_list`

Agent 一创建就具备执行加观察的完整能力。

#### 踩过的坑

**坑 1：`file_read` 和 `file_list` 看到的容器可能不一致**

当前后端有两条容器路径：
- `get_file()` 读取的是 `self._container`（需要显式创建并保留的容器）。
- `execute_code()` 和 `file_list` 使用的是预热池/临时容器，执行完就释放。

这意味着：如果 `sandbox_exec` 在临时容器里写了文件，`file_read` 可能读不到。

**当前处理**：Phase 4.2 先按现有后端能力实现工具，把问题暴露出来。后续 Phase 4.4/4.5 做端到端集成时，需要统一工作容器语义。

**坑 2：测试 mock 需要同时支持 `execute_code` 和 `get_file`**

Phase 4.1 的 `MockSandboxBackend` 只覆盖了 `execute_code`。Phase 4.2 需要同时模拟 `get_file` 和不同场景下的 `execute_code` 返回值。我们把 mock 改成按参数配置：

```python
MockSandboxBackend(
    execute_responses=[...],
    files={"/tmp/result.txt": b"hello"},
)
```

这样 file 工具和 exec 工具可以共用一个 mock。

#### 核心收获

1. **Agent 需要观察文件系统**：执行只是第一步，看到产物才能继续决策。
2. **复用后端已有能力**：没有现成 API 时，可以用 `execute_code()` 做轻量桥接。
3. **工具层只做呈现**：读取 bytes、解码、格式化列表，这些都不该污染后端。
4. **mock 设计要可扩展**：一个统一的 `MockSandboxBackend` 能覆盖多个工具测试。
5. **暴露设计缺陷是好事**：file_read 与 sandbox_exec 容器不一致的问题现在被看见了，而不是隐藏到后面再爆雷。

---



---

### Phase 4.3: finish Tool

#### 先理解：这个模块解决什么问题

Phase 4.1 和 4.2 让 Agent 能执行代码、读取文件、列出目录了。但 Agent 怎么知道"可以停了"？

目前 Agent 主循环的终止条件是：
1. LLM 返回纯文本（没有 tool_call）。
2. 达到 `max_turns` 上限。

第一个条件很被动——LLM 可能误以为自己说完了，也可能在还有工具要调的时候就返回文本。我们需要一个**显式的、机器可识别的终止信号**：`finish` Tool。

`finish` 的语义是："我已经完成了任务，这是最终答案。"Agent 收到后应该立即结束循环并把这个答案返回给用户。

#### 核心设计

```
LLM tool_call(finish, {"result": "最终答案"})
            ↓
ToolRegistry.execute() 调用 finish(result)
            ↓
finish() 返回 ToolResult(success=True, content="最终答案")
            ↓
Agent.run() 检测到工具名为 finish
            ↓
立即返回 result.content，终止循环
```

关键变化在 `Agent.run()`：它不再只依赖"没有 tool_call"来结束循环，而是主动识别 `finish` 这个特殊工具。

#### 代码亮点

**1. `finish` 是一个纯数据工具**

它不需要沙箱后端，只做一个简单的包装：

```python
def finish(result: str) -> ToolResult:
    return ToolResult(tool_call_id="", content=result, success=True)
```

这体现了工具层的设计原则：**每个工具只负责自己的语义**，复杂的生命周期管理交给主循环。

**2. 主循环通过工具名识别终止信号**

在 `Agent.run()` 的工具执行循环里，我们加了这样一段：

```python
if tc.name == "finish":
    if self.planner and self.planner.current_step:
        self.planner.complete_current()
    return result_content
```

这样做的好处是改动极小，不需要引入新的类型或异常。风险是主循环和工具名耦合，后续可以通过 `ToolResult` 增加 `is_terminal` 字段来解耦。

**3. Planner 步骤自动完成**

如果 Agent 使用了 Planner，调用 `finish` 时把当前步骤标记为完成，保证任务状态一致性。

#### 踩过的坑

**坑 1：是否应该把 `finish` 设计成一个异常？**

另一种方案是让 `finish` 的 handler 抛出一个 `FinishException`，然后在 `Agent.run()` 的外层捕获并返回。这样主循环不需要识别工具名。

但我们没有选这个方案，因为：
- 异常通常表示错误，而 `finish` 是正常流程。
- 异常会跳过工具结果追加到 messages，不利于后续分析对话历史。
- 直接识别工具名更符合"finish 是特殊工具"的语义。

**坑 2：`finish` 与其他工具混用**

如果 LLM 在一轮里同时调用了 `sandbox_exec` 和 `finish`，当前实现会在执行到 `finish` 时立即返回，不再执行后面的工具。这符合 finish 的语义，但测试时要注意不要构造这种混合场景。

#### 核心收获

1. **显式终止信号比隐式终止更可靠**：让 LLM 自己决定什么时候交付，而不是靠"没有 tool_call"兜底。
2. **特殊工具需要主循环配合**：工具层只能返回结果，终止循环的决策权在主循环。
3. **最小改动的设计优先**：通过工具名识别 finish 是当下最轻量的方案，未来再抽象也不迟。
4. **Planner 状态要同步**：任务结束时，步骤状态也应该被正确标记。
5. **工具层保持纯粹**：`finish` 不依赖后端，只负责包装结果。

---

## Phase 4：工具链与集成 {#phase-4}

### 4.4：端到端集成测试——零件能转，整台机器能跑吗？

#### 先理解：这个模块解决什么问题

Phase 4.1~4.3 我们一个接一个地实现了四个 Tool：`sandbox_exec`、`file_read`、`file_list`、`finish`。每个 Tool 都有独立的单元测试，看起来都很健康。但这就够了吗？

不够。

单元测试保证的是"零件合格"，而 Agent 是一个完整系统。真正的问题是：当 LLM 在一个真实的多轮对话中，能否把这些 Tool 串成一条工作流？

具体来说，就是这四个动作能否在一个 `Agent.run()` 里连续发生：

1. **计划**：LLM 决定先做什么。
2. **执行**：调用 `sandbox_exec` 在沙箱里写代码、跑代码。
3. **观察**：调用 `file_list` 看看目录里有什么，再调用 `file_read` 读取具体内容。
4. **交付**：调用 `finish` 把最终结果交给用户，并终止循环。

如果只有单元测试，我们看不到它们之间的协作问题。比如：
- `finish` 工具返回的结果，主循环能不能正确识别并终止？
- `file_read` 拿到的内容，会不会被错误地当成工具失败？
- Planner 的步骤会不会在工具成功后正确推进？
- 消息历史里的 tool result 会不会被 LLM 看到并用于下一轮决策？

端到端集成测试回答的就是这些问题。它是"零件合格"到"系统可用"之间的桥梁。

#### 核心设计

**1. 用 Mock 模拟真实世界**

端到端测试不能依赖真实 Docker，否则环境不可控、运行慢、还可能在 CI 上挂掉。我们用三层 Mock：

- **Mock LLM**：按预定轮次返回 `tool_calls`，模拟 LLM 的决策过程。
- **Mock 沙箱后端**：带内存文件系统，能模拟写文件、列目录、读文件。
- **Mock Planner**：注入 `TaskPlan`，验证步骤推进。

**2. 带状态的 Mock 沙箱后端 `StatefulMockBackend`**

这是 Phase 4.4 最有意思的设计。它不是简单按顺序返回预设结果，而是用 Python 的 `ast` 模块解析 LLM 生成的代码片段：

- 识别 `with open(path, 'w') as f: f.write(...)` → 把内容写入内存文件系统。
- 识别 `os.listdir(path)` → 从内存文件系统返回目录列表。
- `get_file(path)` → 直接读取内存中的文件内容。

这样做的好处是：测试能验证"执行代码后，文件真的出现了"，而不只是验证 execute_code 被调用了几次。

```python
# 示例：StatefulMockBackend 的核心逻辑
tree = ast.parse(code)
for node in ast.walk(tree):
    if isinstance(node, ast.With):
        # 识别 with open(..., 'w') 并记录文件
        ...
    if isinstance(node, ast.Call):
        # 识别 os.listdir(...) 并返回列表
        ...
```

**3. 两个互补的测试场景**

- **无 Planner 场景**：验证 Agent 主循环本身能否正确串联四个 Tool。
- **带 Planner 场景**：验证 Planner 步骤在每次成功工具调用后自动推进，最终全部完成。

#### 代码亮点

**1. AST 解析让 Mock 更真实**

与其硬编码 execute_code 的返回序列，不如让 Mock 后端"理解"代码在做什么。这让测试更贴近真实沙箱行为：

```python
def _find_write_content(self, node: ast.With) -> str:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute) and child.func.attr == "write":
                if child.args:
                    arg = child.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        return arg.value
    return ""
```

**2. 测试断言覆盖端到端关键点**

不仅验证最终返回值，还验证：
- `execute_count` 是否正确（`sandbox_exec` + `file_list` 各调用一次 execute_code）。
- 内存文件系统中是否真的写入了文件。
- Planner 的所有步骤是否都变成了 `COMPLETED`。

**3. 没有修改任何源码**

Phase 4.4 的测试全部通过后，我们发现不需要改任何 `src/agent/` 下的代码。这说明 Phase 4.1~4.3 的设计是协调一致的，工具链和主循环已经能自然支撑端到端工作流。

#### 踩过的坑

**坑 1：TDD 的 RED 阶段没有红**

写完测试一跑，直接绿了。这看起来是好事，但对 TDD 来说有点"不够尽兴"。我们做了两件事来确认测试有效：

1. 临时把断言改成错误值，确认测试会失败。
2. 检查测试覆盖的关键路径是否完整（返回值、调用次数、文件状态、Planner 步骤）。

结论是：测试是有效的，直接通过说明前面 Phase 的实现质量高。

**坑 2：file_list 的 os.listdir 路径在 AST 中是 Name 节点**

`file_list` 工具生成的代码是：

```python
import json, os
path = "/tmp"
print(json.dumps(os.listdir(path)))
```

AST 中 `os.listdir(path)` 的参数是 `Name(id='path')`，不是字符串常量。我们的 `_extract_constant` 只能提取 `Constant`，所以会把 `path` 当成 `.` 处理。

但因为测试中内存文件系统里只有一个文件，所以不影响结果。后续如果要模拟多目录场景，需要扩展 `_extract_constant` 来跟踪赋值语句。

**坑 3：Windows 上的 Unix 路径**

测试运行在 Windows，但沙箱路径是 Unix 风格 `/tmp/result.txt`。`os.path.dirname` 在 Windows Python 中对正斜杠路径仍然返回 `/tmp`，所以 `_list_directory` 工作正常。这个细节如果不验证，可能会留下隐患。

#### 核心收获

1. **集成测试是单元测试的必要补充**：单元测试保证零件，集成测试保证系统能跑通。
2. **Mock 也可以有状态**：带状态的 Mock 后端能验证更丰富的行为，而不仅仅是调用顺序。
3. **AST 是测试动态代码的好工具**：不用 eval/exec，就能安全地分析代码意图。
4. **好的前期设计会让后期测试更容易**：因为 Phase 4.1~4.3 的接口清晰，Phase 4.4 不需要改源码。
5. **端到端测试要覆盖关键断言**：不要只验证最终返回值，调用次数、中间状态、Planner 推进都要检查。

---


### 4.5：错误恢复场景测试——Agent 遇到 bug 会崩溃吗？

#### 先理解：这个模块解决什么问题

Phase 4.4 我们验证了 Agent 能跑通" happy path "：计划 → 执行 → 观察 → 交付，一气呵成。但真实世界不会这么顺利。LLM 生成的代码常常有 bug，沙箱环境可能缺少变量，任务可能太重导致超时，甚至可能触碰权限红线。

所以 Phase 4.5 要回答的问题是：**当事情出错时，Agent 会怎么做？**

一个好的 Agent 不应该一报错就躺平。它应该像有经验的程序员一样：

- 看到 `SyntaxError`："哦，代码写漏了个引号，我改一下再跑。"
- 看到 `NameError`："这个变量没定义，我先看看环境里有什么。"
- 看到 `TimeoutError`："数据量太大，我换个轻量方法。"
- 看到 `PermissionError`："这个我真搞不定，得告诉用户。"

这就是错误恢复能力，也是" Agent "和普通"脚本"的核心区别之一。

#### 核心设计

**1. 错误分类器 `ErrorClassifier`**

在 Phase 2.4 我们就实现了错误分类。它把异常映射为两个维度：

- **严重程度**：`RECOVERABLE`（可恢复）、`DEGRADE`（降级）、`FATAL`（致命）
- **恢复策略**：`REWRITE_CODE`、`CHECK_CONTEXT`、`SIMPLIFY_TASK`、`REPORT`

Phase 4.5 要验证的是：这些分类结果真的能指导 Agent 的行为吗？

**2. 错误信息包装 `_classify_tool_error()`**

`Agent.run()` 在工具失败时，会调用 `_classify_tool_error()`。它从 stderr 中抓取异常名，查 `ErrorClassifier`，然后把结果包装成一段 LLM 能读懂的话：

```text
[工具执行失败]
错误: SyntaxError: invalid syntax
严重程度: RECOVERABLE
建议恢复策略: REWRITE_CODE
提示: 代码有 bug，修改后重试即可
```

这段文字很关键。没有它，LLM 只看到原始报错，不知道"该怎么办"。

**3. 四种错误恢复模式**

Phase 4.5 的测试覆盖了四种典型路径：

| 错误类型 | 严重级别 | 恢复策略 | Agent 行为 |
|---------|---------|---------|-----------|
| `SyntaxError` | RECOVERABLE | REWRITE_CODE | LLM 修正代码，再次执行 |
| `NameError` | RECOVERABLE | CHECK_CONTEXT | LLM 先 `file_read` 查看环境，再执行 |
| `TimeoutError` | DEGRADE | SIMPLIFY_TASK | LLM 简化任务，再次执行 |
| `PermissionError` | FATAL | REPORT | Agent 停止，报告用户 |

#### 代码亮点

**1. 错误注入型 Mock 后端 `ErrorInjectionBackend`**

与 Phase 4.4 的 `StatefulMockBackend` 不同，这个 Mock 不关心代码语义，只按顺序返回预设结果。这样我们可以精确控制：

- 第 1 次调用返回 `SyntaxError`
- 第 2 次调用返回成功
- 第 3 次调用返回 `TimeoutError`

```python
class ErrorInjectionBackend(DockerSandboxBackend):
    async def execute_code(self, code):
        response = self.execute_responses[self.execute_count]
        self.execute_count += 1
        return response
```

这种"注入式 Mock "是测试错误路径的标准做法。

**2. Mock LLM 模拟自我修复**

每个测试场景都有一个对应的 Mock LLM。比如 `SyntaxErrorRecoveryClient`：

- 第 1 轮：提交有语法错误的代码
- 第 2 轮：提交修正后的代码
- 第 3 轮：调用 `finish` 交付结果

这模拟了 LLM 看到错误信息后自我修正的过程。

**3. 断言覆盖错误恢复的关键证据**

不仅验证最终成功，还验证：

- tool result 中确实包含 `[工具执行失败]`、严重级别、恢复策略。
- `sandbox_exec` 被调用了正确的次数（一次失败 + 一次成功）。
- FATAL 错误时，Planner 步骤被标记为 `FAILED`。

```python
assert "[工具执行失败]" in first_error
assert "RECOVERABLE" in first_error
assert "REWRITE_CODE" in first_error
```

#### 踩过的坑

**坑 1：RED 阶段又是直接绿**

和 Phase 4.4 一样，测试写完后直接通过了。因为 `Agent.run()` 和 `ErrorClassifier` 在之前的 Phase 已经实现好了。

这次我没有去"构造一个失败"。原因是：这些测试断言的是非常具体的行为（分类字符串、Planner FAILED 状态），如果实现没做这些事，测试不可能通过。所以它们不是"假绿"。

但这也提醒我们：Phase 4.5 的任务性质是"补测试、补覆盖"，而不是"驱动新实现"。

**坑 2：FATAL 错误后的返回值不是 tool result**

我一开始以为 `test_fatal_error_stops_agent` 的返回值会包含 `PermissionError`。但实际运行后发现，返回值是 LLM 在 FATAL 后最后一轮说的 `"Permission denied, I cannot continue."`。

这说明 `Agent.run()` 的设计是：FATAL 错误后给 LLM 最后一轮机会解释，然后返回 LLM 的解释文本。原始报错在 tool result 里，不在最终返回值里。

所以测试需要同时断言：
- 最终返回值包含"Permission denied" 或"无法继续"。
- tool result 中包含 `FATAL` 分类信息。

**坑 3：RECOVERABLE 错误后 Planner 步骤推进的语义**

当前实现会在"任意成功工具调用"后推进 Planner 步骤。比如在 `NameError` 场景：

1. `sandbox_exec` 失败 → 步骤保持 ACTIVE
2. `file_read` 成功 → 步骤被标记为 COMPLETED
3. `sandbox_exec` 成功 → 没有 current_step，不推进

这意味着步骤在"环境检查"成功后就被标记完成，而不是在"核心任务成功"后完成。语义上有瑕疵，但属于现有实现，不是 Phase 4.5 要修复的范围。

为了验证"错误期间步骤保持 ACTIVE"，我在 Mock LLM 的第二轮 `chat()` 中插入了断言：

```python
if self.turn == 2 and self.planner and self.planner.current_step:
    assert self.planner.current_step.status == StepStatus.ACTIVE
```

这个断言在 `Agent.run()` 调用 LLM 之前执行，能精确捕获"错误已发生、尚未成功修复"时的 Planner 状态。

#### 核心收获

1. **错误恢复是 Agent 的核心能力**：会跑通 happy path 只是及格，会处理错误才是优秀。
2. **错误分类要落地到 tool result**：LLM 需要看到"严重级别 + 恢复策略 + 提示"，才能做出正确决策。
3. **Mock 注入是测试错误路径的利器**：通过预设响应序列，精确控制错误发生时机。
4. **测试要覆盖证据链**：不要只看最终结果，要看错误信息是否被正确分类、传递、消费。
5. **中间状态也要断言**：在 Mock LLM 中检查 Planner 步骤保持 ACTIVE，能验证错误没有导致状态误推进。
6. **FATAL 错误需要终止 + 报告**：不能无限重试，也不能默默失败，要明确告诉用户"我搞不定"。
7. **文档位置也要注意**：Phase 4.4 的内容意外被插入到文件开头，提醒我们要检查 `StrReplaceFile` 的匹配位置。

---

### 4.6：配置驱动的 Tool 加载——让 Agent 的能力可裁剪

#### 先理解：这个模块解决什么问题

Phase 4.1~4.5 我们实现了四个 Tool，并默认全部加载到 Agent 中。这在通用场景下没问题，但会带来几个问题：

1. **能力过剩**：有些任务只需要执行代码，不需要文件操作。加载多余的 Tool 会浪费 LLM 的上下文窗口。
2. **安全风险**：文件读取/列表工具在某些场景下可能是敏感能力，用户希望显式关闭。
3. **测试和调试困难**：默认加载所有工具时，很难单独验证某个 Tool 组合的行为。

所以 Phase 4.6 要解决的问题是：**能不能让用户决定 Agent 加载哪些 Tool？**

答案是：通过配置驱动。

#### 核心设计

**1. 新增 `ToolsConfig` 配置类**

```python
class ToolsConfig(BaseModel):
    enabled: list[str] | None = None
```

- `enabled=None`：启用所有默认工具（向后兼容）。
- `enabled=["sandbox_exec", "finish"]`：只启用这两个工具。
- `enabled=[]`：不启用任何工具。

**2. 把工具定义抽到 `_build_tool_specs()`**

原来 `register_default_tools()` 里直接 inline 注册四个 Tool，现在先把四个 ToolSpec 构建成一个字典：

```python
def _build_tool_specs(backend: DockerSandboxBackend) -> dict[str, ToolSpec]:
    return {
        "sandbox_exec": ToolSpec(...),
        "file_read": ToolSpec(...),
        "file_list": ToolSpec(...),
        "finish": ToolSpec(...),
    }
```

这样 `register_default_tools()` 和 `register_tools_from_config()` 可以复用同一套 ToolSpec 定义。

**3. `register_tools_from_config()` 根据配置注册**

```python
def register_tools_from_config(registry, backend, config):
    all_specs = _build_tool_specs(backend)
    enabled = config.tools.enabled

    if enabled is None:
        for spec in all_specs.values():
            registry.register(spec)
        return

    for name in enabled:
        if name in all_specs:
            registry.register(all_specs[name])
        else:
            logger.warning("配置中启用了未知工具：%s，已忽略", name)
```

**4. `Agent.__init__` 增加 `config` 参数**

```python
if config is not None:
    register_tools_from_config(self.tools, self._sandbox_backend, config)
else:
    register_default_tools(self.tools, self._sandbox_backend)
```

未传 `config` 时保持原有行为，完全向后兼容。

#### 代码亮点

**1. 最小改动实现可配置**

没有引入复杂插件系统，只是在现有注册流程上增加了一个配置入口。四个文件修改：

- `config.py`：新增 `ToolsConfig`
- `tools/__init__.py`：新增 `_build_tool_specs()` 和 `register_tools_from_config()`
- `engine.py`：`Agent.__init__` 支持 `config`
- `test_config.py`：新增测试

**2. 未知工具名优雅忽略**

配置中写了不存在的工具名时，不抛异常，而是记录 warning 并继续。这符合"配置应该宽容"的原则，避免因为一个拼写错误导致整个 Agent 启动失败。

**3. 向后兼容**

所有现有代码不需要修改。`Agent(llm_client=...)` 仍然注册所有默认工具。

#### 踩过的坑

**坑 1：mypy 对 `.get()` 的 narrow 不满意**

一开始写成：

```python
spec = all_specs.get(name)
if spec is None:
    logger.warning(...)
    continue
registry.register(spec)
```

mypy 报错说 `spec` 可能是 `None`。即使逻辑上 `continue` 已经排除了 None，mypy 没推断出来。

修复：改成用 `if name in all_specs:` 直接索引：

```python
if name in all_specs:
    registry.register(all_specs[name])
else:
    logger.warning(...)
```

**坑 2：两个 `register_default_tools`**

重构时忘了删除原来的 `register_default_tools`，导致 mypy 报错 "Name already defined"。

修复：删除原始的 inline 版本，保留基于 `_build_tool_specs` 的新版本。

**坑 3：`Agent.__init__` 中 `config` 的类型**

一开始写成 `config: Any = None`，mypy 不报错但类型信息丢失。后来改成在 `TYPE_CHECKING` 下导入 `AgentConfig`：

```python
if TYPE_CHECKING:
    from agent.config import AgentConfig
```

这样既保留类型安全，又避免运行时循环导入。

#### 核心收获

1. **配置驱动是工程化的标志**：从硬编码到可配置，是项目从 demo 走向产品的必经之路。
2. **先抽象再扩展**：把 ToolSpec 构建逻辑抽到 `_build_tool_specs()`，让两种注册方式复用。
3. **向后兼容不是可选项**：新增 `config` 参数必须可选，不能破坏现有调用方。
4. **mypy 的 narrow 有时候需要迎合**：当 `is None` + `continue` 不被识别时，换 `in` + 索引更稳妥。
5. **配置要宽容**：未知工具名忽略 + warning，比直接崩溃更符合配置文件的语义。

---

## Phase 5：核心机制扩展——为什么 Agent Trace 是其他机制的地基 {#phase-5}

> **状态**：规划中。本节记录 Phase 5 的结构决策，具体实现内容将在 Task 5.1 完成后补充。

---

### 先理解：Phase 5 为什么不是"大杂烩"

Phase 4 完成后，我们面前有五个看似相关的候选方向：

- 上下文压缩
- 长期记忆
- 反思式错误恢复
- 安全策略引擎
- Agent Trace

一开始很容易想："既然都是核心机制，那就放在同一个 Phase 里一起做吧。"

但这是典型的**范围蔓延陷阱**。五个方向虽然都挂在"核心机制"这个名字下，但它们的依赖关系、实现复杂度、验收方式都完全不同。把它们塞进同一个 Phase，会导致：

1. **commit 边界模糊**：一个 commit 里同时改观测、改记忆、改安全，出了问题很难回滚。
2. **测试难以聚焦**：每个方向都需要独立的集成测试，混在一起验收标准会混乱。
3. **技术选型相互绑架**：比如长期记忆需要选持久化方案，这个决策不应该被 Agent Trace 的进度阻塞。

所以正确的做法是：**每一种相对独立的机制，都用一个独立的 Phase 完成。**

---

### Phase 5~10 的最终结构

| Phase | 主题 | 负责回答的问题 |
|-------|------|--------------|
| **Phase 5** | Agent Trace | "Agent 做了什么？" |
| **Phase 6** | 反思式错误恢复 | "Agent 如何从错误中学习？" |
| **Phase 7** | 上下文压缩 | "Agent 怎么看更多上下文？" |
| **Phase 8** | 长期记忆机制 | "Agent 如何记住过去？" |
| **Phase 9** | 安全策略引擎 | "Agent 什么不能做？" |
| **Phase 10** | CLI、演示与文档 | "用户怎么用 Agent？" |

这个结构有几个好处：

1. **每个 Phase 只有一个主题**，边界清晰。
2. **后面的 Phase 可以依赖前面的 Phase，但不会被阻塞。** 比如 Phase 6 的反思可以利用 Phase 5 的 Trace，但也可以先用轻量错误日志实现。
3. **长期记忆独立成 Phase 8**，因为它涉及持久化选型、检索策略、跨会话语义等大问题，不应该和 Trace 混在一起。

---

### 为什么 Phase 5 必须先做 Trace？

Trace 不是"锦上添花"，而是其他机制的**观测地基**。

没有 Trace：
- 反思式错误恢复不知道"同类错误出现过几次"。
- 上下文压缩不知道"哪些轮次重要"。
- 长期记忆不知道"哪些信息值得记住"。
- 安全策略引擎即使记录了违规操作，也缺乏完整的执行上下文。

有了 Trace：
- 每次 LLM 调用、每个 Tool 执行、每次状态变化都被结构化记录。
- 后续所有机制都可以消费 Trace 数据，而不是各自重新实现日志逻辑。

**Trace 的另一个重要作用**：解决现有的技术债——`AgentState` 已实现但未接入 `Agent.run()` 主循环。做 Trace 的过程中，自然要把 `AgentState` 接入主循环，因为 State 变化本身就是 Trace 需要记录的事件。

注意：`ExecutionContext` 虽然也已实现，但它要发挥作用必须改造工具签名/注册机制，让 tools 能读写它。这超出了 Phase 5.1 的范围，会作为独立技术债在后续 Phase 处理。

---

### Trace、Messages、State 的关系

这里要澄清一个容易混淆的点：**Trace 不会替代 Messages，也不会完全基于 Messages。**

```
Agent.run()
  ├──→ messages（给 LLM 看的对话历史）
  │      ├── user 消息
  │      ├── assistant 消息（含 tool_calls）
  │      └── tool 结果消息
  │
  └──→ trace（给 Agent/开发者看的执行记录）
         ├── llm_request 事件
         ├── llm_response 事件
         ├── tool_execution 事件
         ├── state_transition 事件
         ├── error_classification 事件
         └── reflection 事件
```

**Messages 是 LLM 的输入协议；Trace 是 Agent 的自我感知数据。** 两者有重叠，但服务于不同目的。

---

### 核心收获

1. **独立机制要独立成 Phase**：不要为了"省阶段"而强行合并不相关的工作。
2. **Trace 是地基**：没有观测，就没有反思、记忆、压缩、安全策略的可靠输入。
3. **Messages 和 Trace 不能混为一谈**：一个给 LLM 看，一个给 Agent/开发者看。
4. **做 Trace 的同时还技术债**：`AgentState` 接入主循环这个遗留问题，将在 Phase 5.1 中一并解决。
5. **保守规划反而更快**：Phase 5 只做一个机制，能更快交付、更快验证、更快进入下一个机制。

---

### 5.1 Agent Trace：让 Agent 的执行过程可见

> **状态**：已完成。

#### 先理解：为什么 Trace 是"观测地基"

前面 Phase 2~4 构建了一个能循环调用 LLM 和执行工具的 Agent，但它的内部运行过程对开发者来说几乎是个黑盒。当 Agent 行为异常时，我们只能通过 `agent.messages` 间接推断它经历了什么，而 messages 是**给 LLM 看的**，不是**给开发者看的**。

Trace 要解决的核心问题是：**把 Agent 的运行过程记录成结构化、可复盘的事件流。**

这不仅仅是调试需求。没有 Trace：
- 反思式错误恢复不知道"同类错误出现过几次"。
- 上下文压缩不知道"哪些轮次重要"。
- 长期记忆不知道"哪些信息值得记住"。

所以 Trace 是后续所有"智能增强机制"的数据地基。

#### 核心设计

我们采用了 **"Step + Event"** 的两层结构：

```
AgentTrace
├── steps: list[TraceStep]      # 按 Agent 主循环轮次组织
│   ├── step_index: int
│   └── events: list[TraceEvent]
│       ├── event_type: str
│       ├── timestamp: datetime
│       └── payload: dict
```

**为什么按轮次组织？** 因为 Agent 的主循环天然就是按轮次运行的。一轮 = 一次 LLM 调用 + 对应的工具执行。按轮次组织后，复盘时可以说"看第 2 轮发生了什么"，非常直观。

**事件类型包括**：
- `state_transition`：AgentState 的 phase / current_step 变化
- `llm_request`：发给 LLM 的请求元数据
- `llm_response`：LLM 返回的内容或 tool_calls
- `tool_execution`：每个 Tool 的执行结果
- `error_classification`：错误分类结果
- `planner_transition`：Planner 步骤推进

#### 代码亮点

**1. Trace 与 messages 分离**

```python
Agent.run()
  ├──→ messages（给 LLM 看的对话历史）
  └──→ trace（给 Agent/开发者看的执行记录）
```

这种分离让 Trace 可以记录内部状态变化（如 `state_transition`），而这些信息不需要也不应该发给 LLM。

**2. State 接入主循环**

```python
self.state = AgentState()
self.trace = AgentTrace()
```

`Agent` 现在持有 `AgentState`，并在 `run()` 中按阶段更新 `phase`：
- `run()` 开始 → `"running"`
- `finish` 成功 → `"finished"`
- FATAL 错误 / `max_turns` → `"failed"`

**3. 不记录完整 messages**

Trace 只记录 messages 的元数据（数量、tools 数量），避免 Trace 本身变成另一个巨大的上下文对象。如果需要完整对话历史，直接查 `agent.messages`。

**4. `_finalize_run` 统一收尾逻辑**

三个退出路径（纯文本返回、`finish`、FATAL、`max_turns`）都需要做同样的事：设置 phase、记录 end_time、保存 final_state、记录 state_transition。我们把它抽成 `_finalize_run()`，避免重复。

#### 踩过的坑

**坑 1：mypy 对 `self.state.phase` 的 narrow 不满意**

代码中某处需要调用：
```python
self.state.set_phase(self.state.phase, new_step)
```

但 `self.state.phase` 的类型是 `str | None`，而 `set_phase` 要求 `str`。虽然逻辑上此时一定是 `"running"`，但 mypy 不知道。

修复：直接传字面量：
```python
self.state.set_phase("running", new_step)
```

**坑 2：`finish` 工具是默认注册的，测试里重复注册会报错**

测试里写：
```python
agent.tools.register(ToolSpec(name="finish", ...))
```

结果抛 `ValueError: 工具已注册：finish`。因为 `Agent.__init__` 已经通过 `register_default_tools()` 注册了 finish。

修复：测试里不再手动注册 finish，直接用默认的。

**坑 3：Trace 的初始 state_transition 放在哪里？**

一开始想把 `run()` 开始时的 `"running"` 转换记录为一个独立的"step -1"，但负索引很奇怪。后来改为：在第一个 `TraceStep`（step 0）里，先记录 `state_transition`，再记录 `llm_request`。这样语义清晰：step 0 包含本轮的所有事件，包括进入 running 状态的初始转换。

#### 核心收获

1. **Trace 不是日志，是结构化事件流**。字符串日志只能 grep，事件流可以被程序消费。
2. **按轮次组织 Trace 符合 Agent 的心智模型**。一轮 = 一次 LLM 调用周期。
3. **AgentState 接入主循环和 Trace 是天然绑定的**。State 变化本身就是 Trace 要记录的事件。
4. **ExecutionContext 要慎重接入**。它的真正使用者是 tools，接入它需要改造工具签名/注册机制，不应该在 Trace Task 里顺手做。
5. **`_finalize_run()` 这样的小抽离能显著降低重复**。三个退出路径共享同一段收尾逻辑。

---

#### 补充：端到端 Trace 测试

在 Phase 5.1 初版完成后，我们回头补充了 5 个端到端测试，验证 Trace 在真实工作流中的效果：

1. **带 Planner 的端到端工作流**：验证 `planner_transition` 事件和 `State.current_step` 同步。
2. **错误恢复端到端工作流**：验证 `error_classification` 事件在真实恢复路径中被记录。
3. **多 Tool 数据分析工作流**：验证 `file_list` → `file_read` → `finish` 的完整工具链都被记录。
4. **Trace JSON 序列化往返**：验证 `to_json()` 后结构完整。
5. **Artifacts 记录**：验证 `AgentState.add_artifact()` 的产物被记录到 `final_state`。

**修复了一个实现缺口**：`Agent.run()` 开始时没有把 Planner 的当前步骤同步到 `AgentState`。补充测试后发现 `State.current_step` 初始为 `None`，修复后 Planner 的初始活动步骤会被正确同步。

这让 Phase 5.1 的测试从 6 个增加到 **11 个**，总测试数从 184 增加到 **189**。

---

## Phase 6：反思式错误恢复 {#phase-6}

> **状态**：进行中。当前完成 Task 6.1：错误模式账本。

Phase 6 要解决的问题是：**Agent 不能每次遇到错误都从零开始思考。**

前几 Phase 的错误处理是这样的：工具失败后，`ErrorClassifier` 判断严重程度和恢复策略，然后把这个结构化提示塞给 LLM。LLM 看到提示后自己决定下一步。这个机制能工作，但它有一个隐形成本：LLM 是「金鱼记忆」，它不记得自己上一轮因为什么失败过。如果同一个 `NameError` 连续出现三次，LLM 可能三次都给出差不多的修复方案，白白烧钱。

反思式错误恢复的思路是：Agent 自己记住「同类错误出现了几次」，然后在提示 LLM 时追加更有针对性的建议。这是一种**从被动响应到主动干预**的进化。

---

### 6.1 错误模式账本：让 Agent 记住自己犯过什么错

#### 先理解：为什么需要一个账本

人类程序员调试时有一个本能：如果同一个报错连续出现，我们会意识到「这里有个系统性问题」，而不是每次都从头排查。

比如：
- 第 1 次 `NameError: name 'pd' is not defined` → 可能忘了 import；
- 第 2 次同样的错误 → 应该提醒自己在代码开头统一 import pandas；
- 第 3 次 → 可能说明 prompt 或环境配置有问题，需要换策略。

Agent 也需要这种「计数本能」。`ErrorPatternLedger` 就是做这个的：它不是持久化数据库，而是**单次运行内的短期记忆**，用来回答「这个错误已经出现几次了」。

#### 核心设计

```
ErrorPatternLedger
├── _patterns: dict[(tool_name, exc_type), ErrorPattern]
│
ErrorPattern
├── tool_name: str
├── exc_type: str
├── count: int
├── messages: list[str]
└── last_seen_at: datetime
```

**主键 = (tool_name, exc_type)**：为什么不是只看异常类型？因为不同工具的错误语义不同。`sandbox_exec` 的 `NameError` 说明代码里变量没定义；`file_read` 的 `NameError` 几乎不可能出现。分开聚类更合理。

**消息签名提取**：当重复次数达到阈值后，我们会进一步看错误消息里的关键标识。比如 `NameError` 中的变量名、`KeyError` 中的键名、`AttributeError` 中的属性名。这样能把「老是 `pd` 没定义」和「老是 `np` 没定义」区分开。

#### 代码亮点

**1. 与 `ErrorClassifier` 职责分离**

`ErrorClassifier` 回答「这个错误严重吗、应该怎么恢复」。
`ErrorPatternLedger` 回答「这个错误出现过几次、最近的消息长什么样」。

两者互补，但绝不互相替代。这是单一职责原则的体现。

**2. 消息历史做上限裁剪**

```python
if len(pattern.messages) > self.max_history:
    pattern.messages = pattern.messages[-self.max_history :]
```

账本只保留最近 N 条消息，避免在长时间运行中无限制增长。默认值 5 条已经足够用于相似度分析。

**3. `UnknownError` 兜底**

如果错误内容里提取不到 `XxxError` 或 `XxxException`，就用 `UnknownError` 作为主键。这样即使格式不规范的错误也能被记录，而不是被静默丢弃。

#### 踩过的坑

**坑 1：AttributeError 的签名提取很容易抓错对象**

错误消息是：
```
AttributeError: 'DataFrame' has no attribute 'colum'
```

如果简单提取第一个引号内容，会得到 `'DataFrame'`，这是对象类型，不是缺失的属性。我们要的是 `'colum'`。

修复：用更具体的正则：
```python
re.search(r"has no attribute\s+['\"]([^'\"]+)['\"]", error_content)
```

**教训：错误消息的结构化提取要根据异常类型的语义来，不能一刀切。**

#### 核心收获

1. **反思的前提是记忆**：没有错误模式账本，反思层就是无源之水。
2. **主键设计决定聚类质量**：`(tool, exc_type)` 比只看异常类型更精确。
3. **职责边界要清晰**：账本不负责生成提示，只负责记录和查询。
4. **短期记忆就够用了**：Phase 6 不需要持久化数据库，单次运行内的计数已经能显著改善恢复效果。
5. **为后续 Task 留出接口**：`messages` 保留和 `_extract_message_signature` 的存在，为 Task 6.2 的「达到阈值后再看消息相似度」打下了基础。

---

### 6.2 反思策略生成器：把「计数」变成「提示」

#### 先理解：为什么需要 ReflectiveAdvisor

Task 6.1 的 `ErrorPatternLedger` 已经能回答「这个错误出现了几次」。但次数本身对 LLM 没有直接意义——我们需要把它翻译成 LLM 能理解的、能指导下一步行动的提示。

`ReflectiveAdvisor` 就是做这个翻译的。它的输入是一个 `ErrorPattern`，输出是一个结构化的 `ReflectionAdvice`，包含：

- `hint`：追加给 LLM 的反思提示；
- `severity` / `action`：可能升级后的恢复策略；
- `is_escalated`：是否真的升级了；
- `reflection_payload`：供 Trace 记录的结构化数据。

#### 核心设计

**1. 硬编码规则 + 计数阈值**

我们不调用 LLM，而是根据出现次数做确定性决策：

```
count < reflection_threshold      → 不生成提示
reflection_threshold <= count < escalate_threshold → 生成提示，但不升级策略
count >= escalate_threshold       → 生成提示，并按规则升级策略
```

默认 `reflection_threshold=2`，`escalate_threshold=4`。这意味着：
- 第 1 次错误：Agent 保持沉默，让 LLM 自己处理；
- 第 2~3 次：Agent 开始提醒 LLM「这个错误反复出现了」；
- 第 4 次及以上：Agent 认为 LLM 自己搞不定，主动升级策略。

**2. 按异常类型定制升级路径**

不同异常类型的恢复语义不同，不能一刀切。

```text
NameError / KeyError / AttributeError / ImportError / FileNotFoundError
  RECOVERABLE + CHECK_CONTEXT
    → DEGRADE + SIMPLIFY_TASK
      → FATAL + REPORT

SyntaxError / TypeError / ValueError / ZeroDivisionError / IndexError
  RECOVERABLE + REWRITE_CODE
    → DEGRADE + SIMPLIFY_TASK
      → FATAL + REPORT

MemoryError / TimeoutError / RecursionError
  DEGRADE + SIMPLIFY_TASK
    → FATAL + REPORT

PermissionError / UnknownError
  FATAL + REPORT（不升级）
```

这个设计的哲学是：**有些错误值得给 LLM 更多机会，有些错误一开始就是死路。**

**3. 签名收敛分析**

当错误重复出现时，Advisor 会进一步看：这些错误是不是同一个根因？

例如：
- 3 次 `NameError` 都指向 `pd` → 提示「请注意变量 'pd' 未定义，建议先 import pandas」；
- 3 次 `NameError` 分别指向 `pd`、`np`、`df` → 提示「该类错误已多次出现，建议检查代码逻辑或环境状态」。

这个分析是轻量的：复用 6.1 的 `_extract_message_signature()` 提取签名，然后统计频率。

#### 代码亮点

**1. 输出结构化，方便下游消费**

```python
@dataclass
class ReflectionAdvice:
    hint: str
    severity: ErrorSeverity
    action: RecoveryAction
    is_escalated: bool
    reflection_payload: dict[str, Any]
```

`engine.py` 在 6.3 接入时，不需要解析文本，直接拿 `hint` 拼接、`is_escalated` 判断、`reflection_payload` 写 Trace。

**2. 升级路径用表驱动**

```python
_ESCALATION_PATHS: dict[str, list[tuple[ErrorSeverity, RecoveryAction]]] = {
    "NameError": [
        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        (ErrorSeverity.DEGRADE, RecoveryAction.SIMPLIFY_TASK),
        (ErrorSeverity.FATAL, RecoveryAction.REPORT),
    ],
    ...
}
```

表驱动的好处：新增异常类型或调整策略时，只改这张表，不改核心逻辑。

**3. 签名收敛的阈值是「过半数」**

```python
if max_count > len(pattern.messages) / 2:
    return most_common_sig
```

这是经验值。在 `max_history=5` 时，要求至少 3 条消息共享同一个签名才算收敛。如果未来发现太严或太松，可以调整。

#### 踩过的坑

**坑 1：把升级逻辑和提示生成逻辑混在一起**

一开始想在一个大函数里同时算升级和拼提示，结果代码很快变得难读。

修复：拆成三个小函数：
- `_resolve_strategy()`：决定最终 severity/action；
- `_resolve_signature()`：做签名收敛分析；
- `_build_hint()`：根据以上结果生成中文提示。

**教训：策略层的代码更需要清晰的分层，因为规则会不断增加。**

**坑 2：FATAL 类型的错误也会生成反思提示**

最初版本对 `PermissionError` 也会生成「该错误已多次出现」的提示。但 FATAL 错误意味着 Agent 自己搞不定，提示 LLM 也没用，反而浪费 token。

修复：对 `PermissionError` / `UnknownError` 这类 FATAL 路径只有一级的异常，不生成提示、不升级。虽然当前代码中它们仍可能进 `advise()`，但输出保持原策略和空提示。

#### 核心收获

1. **计数只是手段，提示才是目的**：`ErrorPatternLedger` 记录数据，`ReflectiveAdvisor` 把它变成行动建议。
2. **升级规则要按异常类型定制**：不同错误有不同的「容错空间」。
3. **结构化输出降低接入成本**：6.3 接入主循环时，不需要理解 Advisor 内部，只消费 `ReflectionAdvice`。
4. **签名收敛是「轻量分析」**：不调用 LLM，只用正则 + 频率统计，足够解决常见重复错误。
5. **表驱动让规则可维护**：`_ESCALATION_PATHS` 集中管理所有升级路径，新增异常类型时改动最小。

---

### 6.3 接入 Agent 主循环与 Trace：让反思真正产生行为变化

#### 先理解：为什么接入是最后一步，也是最关键的一步

Task 6.1 和 6.2 都是「零件」：
- 6.1 负责记录错误模式；
- 6.2 负责根据模式生成建议；
- 6.3 负责把建议真正送进 Agent 的决策循环。

没有 6.3，ReflectiveAdvisor 写得再好也只是个摆设。LLM 不会主动去看一个独立对象，我们必须把反思提示**塞进 LLM 能看到的消息里**。

#### 核心设计

**1. 接入点选在错误分类之后**

在 `Agent.run()` 的工具执行路径中，原本的流程是：

```text
工具失败 → ErrorClassifier 分类 → 构造错误消息 → 发给 LLM
```

接入反思层后变成：

```text
工具失败
  → ErrorClassifier 分类（保留原始分类，写入 Trace）
  → ErrorPatternLedger.record() 记录模式
  → ReflectiveAdvisor.advise() 生成 effective 策略 + hint
  → 用 effective 策略构造错误消息
  → 追加反思提示
  → 写入 reflection Trace 事件
  → 发给 LLM
```

**2. error_classification 事件保留原始分类**

`ErrorClassifier` 的职责是「这个错误本来应该怎么分类」。反思层是在这个基础上做二次决策。两者不要混淆，所以 `error_classification` TraceEvent 仍然记录原始 `severity/action/hint`，而 `reflection` 事件记录 effective 策略。

**3. effective 策略用于 LLM 消息和 FATAL 判断**

LLM 看到的是 Agent 当前认为最合适的恢复策略。如果 Advisor 把 `NameError` 从 `RECOVERABLE` 升级到 `DEGRADE`，LLM 收到的消息里就是「严重程度: DEGRADE」「建议恢复策略: SIMPLIFY_TASK」。

同时，如果 effective severity 达到 FATAL，Agent 会走现有的 FATAL 退出逻辑：给 LLM 最后一轮解释机会，然后终止循环。

**4. 反思提示独立成段**

错误消息格式变成：

```text
[工具执行失败]
错误: NameError: name 'pd' is not defined
严重程度: RECOVERABLE
建议恢复策略: CHECK_CONTEXT
提示: 先检查环境中是否有需要的变量/模块
反思提示: 注意：NameError 已多次出现，且多与 'pd' 有关，建议先检查相关变量是否已正确声明或导入。
```

这样既有原来的结构化信息，又有新的反思建议，对现有测试的 substring 断言影响最小。

#### 代码亮点

**1. 依赖注入风格一致**

```python
Agent(
    llm_client=...,
    reflective_advisor=ReflectiveAdvisor(reflection_threshold=3),
    persist_error_patterns=True,
)
```

和 `planner`、`error_classifier` 一样，`reflective_advisor` 可以注入自定义实例，便于测试和扩展。

**2. ledger 生命周期可控**

```python
if not self.persist_error_patterns:
    self.error_pattern_ledger.clear()
```

默认每次 `reset()` 清空，保证不同任务之间不互相污染。需要跨任务保留时打开开关即可。

**3. 最小侵入主循环**

整个接入只修改了 `engine.py` 中工具失败处理的几十行代码，没有改变 `Agent.run()` 的整体控制流。

#### 踩过的坑

**坑 1：用原始 severity 还是 effective severity 判断 FATAL？**

一开始犹豫是否只在 `ErrorClassifier` 返回 FATAL 时才终止。但这样_reflective advisor_ 的升级就失去了强制力。

修复：用 effective severity 判断 FATAL。既然 Advisor 决定「这个问题已经没救了」，Agent 就应该尊重这个决策。

**坑 2：reflection 事件记录时机**

一开始想每次错误都记录 reflection 事件，即使 count=1、没有生成提示。这会导致 Trace 里大量空 payload 的 reflection 事件。

修复：只在 `advice.hint != ""` 或 `advice.is_escalated` 时记录。这样 reflection 事件都有实际意义。

#### 核心收获

1. **零件再好，也要接入主循环才能生效**。6.3 是 Phase 6 的「临门一脚」。
2. **原始分类和 effective 策略要分开记录**。一个给复盘看，一个给 LLM 看。
3. **错误消息是 LLM 的输入协议**。反思提示必须变成消息的一部分，而不是独立对象。
4. **FATAL 升级必须有强制力**。effective severity 为 FATAL 时，Agent 必须停止，否则升级规则就是空谈。
5. **接入层要尽量薄**。把决策逻辑留在 Advisor，引擎只负责调用和消费结果。

---

## Phase 6 核心收获

Phase 6 全部完成后，Agent 的错误恢复能力从「被动分类」进化到了「主动反思」：

1. **ErrorPatternLedger**：给 Agent 装上短期错误记忆；
2. **ReflectiveAdvisor**：把记忆转化为结构化建议和策略升级；
3. **Agent.run() 接入**：让建议真正影响 LLM 看到的错误消息和 Agent 的终止决策；
4. **Trace 记录**：让整个反思过程可观测、可复盘。

这个设计的最大优势是**可控、可测试、低成本**：没有调用 LLM 做总结，所有规则都写在代码里，行为确定。未来如果要升级到 LLM-based 反思，只需要替换 `ReflectiveAdvisor` 这一个组件。

---

---

## Phase 6 修复：ReflectiveAdvisor 尊重 ErrorClassifier {#phase-6-fix}

### 问题背景

在 Phase 6.2 实现 `ReflectiveAdvisor` 时，最初的版本把每个异常类型的内置升级路径的**第一阶段**当作默认起点。例如 `NameError` 一律从 `RECOVERABLE + CHECK_CONTEXT` 开始，不管 `ErrorClassifier` 当前把它判成什么。

这在两种场景下会出问题：

1. **用户自定义了更激进的 `ErrorClassifier`**：如果分类器已经把某个 `NameError` 判为 `DEGRADE`，Advisor 却把它拉回 `RECOVERABLE`，等于覆盖了分类器的决策。
2. **分类器直接判为 `FATAL`**：Advisor 仍然可能把它当成 `RECOVERABLE` 处理，导致 Agent 错过终止时机。

### 修复思路

把 `ReflectiveAdvisor` 的职责收窄为：**只升级、不覆盖、不降级**。

具体做法：

- `advise(severity, action)` 接收 `ErrorClassifier` 的当前输出，把它当作升级路径里的"当前阶段"。
- `_resolve_strategy` 在路径中查找当前阶段，向后推进；如果找不到，保守地保持原策略。
- 输入已经是 `FATAL` 时，直接返回，不生成反思提示。
- 次数未达到 `reflection_threshold` 时，也直接透传原策略，避免过度打扰。

### 为什么这是正确的设计

- **单一职责**：`ErrorClassifier` 负责"当前这次错误该怎么看"，`ReflectiveAdvisor` 负责"同类错误反复出现时是否该加码"。
- **可扩展性**：未来加入新的分类器或调整分类规则时，不需要同步修改 Advisor 的路径表。
- **安全性**：`FATAL` 是绝对红线，Advisor 不能为了"给 LLM 一次反思机会"而降低红线。

### 验证

新增了 3 个失败测试，确保：

1. 输入 `FATAL` 时输出仍为 `FATAL`。
2. 输入自定义的 `DEGRADE` 起点时不会被拉回 `RECOVERABLE`。
3. 从自定义起点仍可按路径向上升级。

修复后全量测试 `229 passed`，mypy / ruff 无错误。

---

## Phase 7.1：上下文压缩第一步 —— Token 估算与配置 {#phase-71}

### 为什么要先做 Token 估算？

上下文压缩和所有性能优化一样，必须先有**度量**。
如果连当前消息历史有多少 token 都不知道，就无法决定：
- 是否需要压缩？
- 要保留多少轮？
- 哪部分可以外迁或摘要？

所以 Phase 7 的第一个 Task 不是写压缩器，而是写**估算器**和**预算配置**。

### 设计要点

1. **默认轻量估算**：`CharTokenEstimator` 按 `len(content) // 4` 估算。对英文和代码足够接近，对中文会低估，但优点是不依赖任何外部库。
2. **可选精确估算**：`TiktokenEstimator` 在安装了 tiktoken 时提供更精确的值，但设计为可插拔，不强制引入依赖。
3. **配置默认关闭**：`ContextCompressionConfig.enabled = False`。这是为了避免 Phase 7 半成品期间影响现有 Agent 行为，也是一种解耦手段。
4. **Token 估算要考虑 tool_calls**：assistant 消息里的 `tool_calls` 也会占 token，所以估算时要把工具名和参数也算进去。

### 一个小教训

做基础设施类 Task 时，测试要覆盖“未安装可选依赖”的情况。`TiktokenEstimator` 在未安装 tiktoken 时必须给出清晰的 `ImportError`，而不是神秘的崩溃。这保证了项目在不同环境下的可移植性。

### 当前状态

- `src/agent/core/token_estimator.py`：抽象基类 + 两种实现。
- `src/agent/config.py`：新增 `ContextCompressionConfig`。
- `tests/test_context_compression.py`：11 个测试（10 通过，1 因未安装 tiktoken 跳过）。
- 全量测试：239 passed，1 skipped。

---

## Phase 7.2：工具结果外迁 —— ContextCache 与 ToolResultExternalizer {#phase-72}

### 为什么要把工具结果外迁？

Agent 运行过程中，`sandbox_exec` 的执行输出、`file_read` 读取的文件内容很容易膨胀到几千甚至几万字符。如果全部塞进 `messages`，上下文很快就会爆掉。

直接删除又不行，因为 LLM 可能后续还需要看完整内容。所以最好的方式是：

> **把完整内容搬到本地缓存文件，消息历史里只放一个“索引卡”（URI + 预览）。**

这就是 Claude Code / Kimi Code 管理大上下文的核心思想之一。

### 设计要点

1. **URI 与文件路径解耦**：外部统一使用 `hermes://context/<session_id>/<run_id>/<entry_id>.md`，内部再映射到磁盘路径。未来换对象存储、数据库都不需要改消费端。
2. **Session 级缓存**：同一个 `Agent` 实例的多次 `run()` 共享缓存，进程结束后默认清理。
3. **失败 traceback 默认完整保留（D1）**：调试信息不能省，只有极长时才截断给链接。
4. **成功结果外迁**：`file_read` 保留 500 字符预览，`sandbox_exec` 成功保留 200 字符预览。
5. **不调用 LLM 做摘要**：工具结果摘要用规则预览就够了，LLM 摘要器留给旧对话历史的摘要。

### 解耦意识

- `ToolResultExternalizer` 只处理原始 content，错误分类在调用它之前完成，所以 Phase 6 的 `ReflectiveAdvisor` 完全不受影响。
- `ContextCache` 不依赖 `Agent` 或 `messages`，是一个独立的存储组件，未来 Phase 8 的长期记忆可以复用它的 URI 方案。

### 当前状态

- `src/agent/core/context_cache.py`：`ContextCache` + `CacheEntry`。
- `src/agent/core/tool_result_externalizer.py`：`ToolResultExternalizer`。
- `src/agent/config.py`：新增 `externalize_threshold`、`file_read_preview_chars` 等字段。
- 全量测试：249 passed，1 skipped。

---

## Phase 7.3：小模型摘要器 {#phase-73}

### 为什么摘要要单独抽象？

上下文压缩有两个不同的摘要场景：

1. **工具结果外迁**：只需要“前 N 行/字符”的预览，规则就够了。
2. **旧对话历史压缩**：需要理解多轮对话的语义，提炼出“目前完成了什么、下一步该做什么”。

第二种场景需要模型能力，但又不想让主模型停下来做摘要（费钱、占上下文）。所以引入**独立的小模型摘要器**。

### 设计要点

1. **抽象接口 `Summarizer`**：未来可以换成本地模型、更小的云端模型、甚至规则摘要，调用方无感知。
2. **`StaticSummarizer` 兜底**：默认使用，不调用 LLM，保证在没有配置小模型时也能工作。
3. **`LLMSummarizer` 独立 client**：通过注入的 `llm_client` 调用小模型，和主循环的 `llm_client` 完全分离。
4. **max_length 截断**：即使模型返回很长的摘要，也会被截断到配置的字符上限，防止摘要本身又占满上下文。

### 小模型的使用原则

- 只做“低创意、高确定性”的任务：摘要、格式化、提取关键词。
- 不替代主模型做决策、规划、代码生成。
- 通过 `max_tokens` 限制输出长度，控制成本。

### 当前状态

- `src/agent/core/summarizer.py`：`Summarizer` + `StaticSummarizer` + `LLMSummarizer`。
- 全量测试：255 passed，1 skipped。

---

## Phase 7.4：context_read 工具 —— 让 LLM 读回缓存 {#phase-74}

### 为什么需要一个专门的工具？

Phase 7.2 把长工具结果外迁到了本地缓存文件，消息历史里只留了 URI 和预览。但 LLM 本身不会“自动”去打开文件，它只能通过工具调用来获取内容。所以必须给 LLM 一个 `context_read(uri)` 工具，让它在需要时把完整内容拉回对话。

### 设计要点

1. **URI 方案隔离**：只接受 `hermes://context/...`，拒绝 `file://` 等任意文件路径，防止路径遍历。
2. **自动注册**：只要启用压缩，`Agent` 就会自动注册 `context_read`，不需要用户在 `tools.enabled` 里手动添加。因为它是压缩子系统的内部配套工具。
3. **可关闭**：通过 `register_context_read: false` 可以关闭自动注册，满足特殊场景需求。
4. **默认缓存目录 `.hermes/context_cache`**：可配置 `cache_root`；同时加入 `.gitignore`，避免把缓存提交到版本库。
5. **防止二次外迁**：`ToolResultExternalizer` 对 `context_read` 的结果跳过外迁，避免“读缓存 → 又被外迁 → 再读”的循环。
6. **资源清理**：`Agent.close()` 会根据 `cleanup_on_exit` 清理缓存目录。

### 和沙箱 file_read 的区别

| 工具 | 读取对象 | 典型用途 |
|------|---------|---------|
| `file_read` | 沙箱内部文件 | LLM 想查看沙箱里的代码/数据文件 |
| `context_read` | Agent 内部缓存 | LLM 想查看之前被外迁的 tool result 完整内容 |

两者 URI 方案不同，权限边界也不同，未来 Phase 9 安全策略可以分别管控。

### 当前状态

- `src/agent/tools/context_read.py`：`context_read(uri, cache)`。
- `src/agent/tools/__init__.py`：`register_context_tools()` 闭包注入缓存。
- `src/agent/core/engine.py`：`Agent` 自动创建 `ContextCache`、注册 `context_read`、提供 `close()`。
- 全量测试：268 passed，1 skipped。

---

## Phase 7.5：HybridCompressor 与主循环接入 —— 让压缩真正生效 {#phase-75}

### 为什么这是关键一步？

Phase 7.1~7.4 把“压缩基础设施”都准备好了：token 估算、缓存、外迁器、摘要器、`context_read` 工具。但它们还散落在主循环之外。Phase 7.5 的任务是把它们串进 `Agent.run()`，让 Agent 在对话过程中**自动**完成预算检查、工具结果外迁、历史压缩。

### 设计决策

1. **压缩子系统只在启用时创建**：
   - `config.agent.compression.enabled=false` 时，`_token_estimator`、`_tool_result_externalizer`、`_context_compressor` 全部为 `None`，不会触发任何压缩逻辑。
   - 启用时，`Agent` 自动组装默认实现：
     - `CharTokenEstimator`
     - `ToolResultExternalizer`
     - `StaticSummarizer`（默认兜底）
     - `HybridCompressor`
   - 用户可通过 `token_estimator`、`summarizer`、`context_compressor`、`summarizer_llm_client` 注入自定义实现。

2. **错误分类一定在外迁之前**：
   - 工具执行后，先用原始 `result.content` 做错误分类（Phase 6）。
   - 然后才调用 `ToolResultExternalizer` 替换过长的 content。
   - 这样 `ReflectiveAdvisor` 看到的异常类名不会受外迁后格式影响。

3. **Trace 双事件**：
   - `tool_result_externalized`：单次工具结果外迁时记录，包含 URI、原始长度、摘要。
   - `context_compression`：整轮压缩时记录，包含压缩前后消息数/token 数、策略、摘要。

4. **HybridCompressor 策略**：
   - 保护前 `protect_first_n` 条消息。
   - 从后向前数，保护最近 `protect_last_n_turns` 个 assistant 回合（assistant 消息 + 其后所有 tool 结果）。
   - 中间区域用 Summarizer 生成单条摘要消息。
   - 仍超预算则逐步缩短摘要，最终丢弃中间区域；最后手段对尾部最旧消息做截断，但永远保留最后一条消息完整。

### 踩坑与修复

- **mypy 对 `config is not None` 的推断**：`_setup_compression` 中早期返回条件写得太复杂，mypy 无法推断后续 `config` 非 None。修复：先判断 `config is None or self.context_cache is None` 直接返回，再判断 `enabled`，最后使用 `config.agent.compression`。
- **fallback 截断保护最后一条消息**：最初测试期望两条消息都被截断，但设计原则要求“最近一轮不可动”。测试调整为验证最后一条 assistant 完整保留，第一条 user 被截断。
- **LLM client 返回非法 JSON**：集成测试里手写 `'{"x": "X" * 100}'` 被 LLM 解析器直接原样返回，导致 `json.loads` 失败。修复：用字符串拼接生成真正的 JSON 数组。

### 当前状态

- `src/agent/core/compressor.py`：`HybridCompressor` 实现完成。
- `src/agent/core/engine.py`：外迁 + 压缩接入 `Agent.run()`。
- `src/agent/config.py`：压缩配置字段补齐。
- 全量测试：275 passed，1 skipped；mypy / ruff 全绿。

---

## Phase 7 完结：上下文压缩全链路 {#phase-7-wrapup}

### Phase 7 做了什么？

Phase 7 的目标是让 Agent 在长对话、大工具输出的场景下，仍能把发给 LLM 的上下文控制在预算内，同时不丢失关键信息。整个 Phase 拆成 6 个 Task：

| Task | 内容 | 关键交付 |
|------|------|---------|
| 7.1 | Token 估算与压缩配置 | `TokenEstimator`、`CharTokenEstimator`、`ContextCompressionConfig` |
| 7.2 | ContextCache 与 ToolResultExternalizer | 工具结果外迁到 `.md` 缓存，消息里只留 URI |
| 7.3 | 小模型摘要器 | `Summarizer` 抽象 + `StaticSummarizer` + `LLMSummarizer` |
| 7.4 | context_read 工具 | LLM 可通过 `context_read(uri)` 读回缓存 |
| 7.5 | HybridCompressor 与主循环接入 | `HybridCompressor`、预算检查、Trace 事件 |
| 7.6 | 配置、测试、文档同步 | 全绿门禁 + 文档更新 |

### 为什么这样设计？

1. **消息历史是工作集，Trace/Cache 是档案馆**：可以大胆压缩 `messages`，因为完整事件已经存在 Trace 里，原始工具结果存在缓存里。
2. **外迁优先于摘要，摘要优先于删除**：长工具结果先外迁（成本低、信息不丢），旧对话再摘要，最后才删除。
3. **小模型做摘要**：把“总结旧历史”交给便宜模型，保护主模型上下文和费用；未配置时规则摘要兜底。
4. **默认关闭**：`enabled=false` 保证既有 Agent 行为不变。

### 关键解耦策略

- **错误分类先行**：工具执行后先用原始 `result.content` 做错误分类（Phase 6），再外迁。`ReflectiveAdvisor` 看到的异常类名不受影响。
- **Trace 双事件**：`tool_result_externalized` 记录单次外迁；`context_compression` 记录整轮压缩。
- **`context_read` 结果不外迁**：避免“读缓存 → 又被外迁 → 再读”的循环。
- **不拆分 tool_call/tool 结果**：`HybridCompressor` 头部边界对齐到完整回合，尾部按 assistant 回合保护。

### 质量状态

- `pytest tests/ -q` → 276 passed，1 skipped
- `mypy src/` → 0 errors
- `ruff check src/ tests/` → 0 errors

### 下一步

Phase 8：长期记忆机制。跨任务/跨会话保留关键信息，让 Agent 在多次运行之间也能“记得”用户偏好、已安装依赖、已生成产物等。

---

## Phase 9：安全策略引擎 —— 把安全规则系统化 {#phase-9}

### 先理解：这个模块解决什么问题

前几 Phase 里，Agent 能写代码、读文件、记长期记忆，但缺少一个统一的安全闸口。
如果 LLM 被诱导去读取 `/etc/passwd`、导入 `os` 执行系统命令，或者写入敏感记忆，
我们需要一个地方集中判断"这能不能做"。Phase 9 的目标就是把这类规则抽成可配置的
**策略引擎**，而不是散落在各个 tool handler 里。

### 核心设计

1. **策略引擎 `PolicyEngine`**（`src/agent/core/security.py`）：
   - 按 `resource + operation + subject` 匹配规则。
   - 支持 `allow` / `deny` / `review` 三种动作、优先级覆盖、正则/子串匹配。
   - 默认行为可配置，默认宽松（`ALLOW`），不破坏现有行为。

2. **配置 `SecurityConfig`**（`src/agent/config.py`）：
   - `enabled` 默认 `False`；开启后才加载规则。
   - 未提供自定义规则时，使用包内 `default_security_rules.yaml`。
   - 自定义规则完全覆盖默认规则集。

3. **统一拦截点 `ToolRegistry.execute()`**（`src/agent/core/engine.py`）：
   - 工具执行前先做工具名级检查。
   - 对 `sandbox_exec` / `file_read` / `file_list` / `memory_read` 做参数级检查。
   - 策略拒绝返回 `ToolResult(success=False, content="策略拒绝：...")`，原因返回给 LLM。

4. **文件路径归一化**：
   - `file/path` 类型的 subject 先转字符串、再把 `\\` 换成 `/`、最后转小写。
   - 这样 `C:\\Windows\\System32\\config\\SAM` 和 `/ETC/PASSWD` 都能被默认规则命中。

5. **记忆读写策略**（`src/agent/core/memory.py`）：
   - `MemoryManager` 可选注入 `PolicyEngine`。
   - `record()` 对每条 `MemoryEntry` 检查 `memory/category/write`。
   - `inject()` / `read()` 检查 `memory/category/read`。
   - 新增 `check_read_policy(uri)`，让 `memory_read` 工具能把拒绝原因显式返回给 LLM。
   - 拒绝时跳过/返回 `None` 或返回 `ToolResult(success=False, ...)`，不阻塞主循环。

### 代码亮点

- **非字符串防御**：`PolicyEngine.evaluate()` 先把 `subject` 转 `str()`，避免 LLM 传
  数字/None 导致正则抛 `TypeError` 中断主循环。
- **非法正则退化**：正则编译失败时退回子串匹配，保证单条规则错误不会拖垮引擎。
- **零侵入 tool handler**：所有检查都在 `ToolRegistry` 层完成，不修改 handler 签名。
- **Agent 统一注入 policy**：`Agent.__init__()` 只构建一次 policy，同时给
  `ToolRegistry` 和 `MemoryManager`，避免两套规则不一致；外部传入的 `MemoryManager`
  若已有 policy 则不会被覆盖。

### 踩过的坑

- **Windows 路径绕过**：最初规则只覆盖 Linux 路径，Windows 反斜杠和大小写都能绕过。
  修复：在参数级检查前做路径归一化。
- **记忆读写双路径**：`memory_read` 既走 `ToolRegistry` 的参数级检查，又在
  `MemoryManager.read()` 里做 category 检查；`check_read_policy()` 进一步保证
  拒绝原因能显式返回给 LLM。
- **自定义规则覆盖默认规则集**：`PolicyEngine.from_config()` 在用户传规则时不再加载
  默认规则，避免规则冲突和意外放行。

### 核心收获

- 安全策略应该"默认关闭、默认宽松"，先保证不破坏现有功能。
- 把所有检查收敛到少数拦截点，比在每个 tool 里写 if 更容易维护。
- 拒绝原因必须返回给 LLM，让它能自我修正而不是卡住。
- 路径/URI 这类 subject 一定要先归一化，再匹配规则。
- 集成测试要覆盖主循环：组件级测试只能验证拦截点，主循环测试才能验证
  “策略拒绝不阻塞执行、LLM 能看到原因、安全路径可恢复”。

### 质量状态

- `pytest tests/ -q` → 446 passed，1 skipped
- `mypy src/` → 0 errors
- `ruff check src/ tests/` → 0 errors

### 下一步

Phase 10.1：CLI 入口 —— argparse。把 Agent 包装成用户可直接运行的命令行工具。

---

## Phase 10.1：CLI 入口 —— argparse {#phase-101}

### 先理解：为什么需要 CLI

之前的 Phase 中，运行 Agent 需要写一段 Python 脚本：

```python
from agent import Agent
from agent.llm import OpenAIClient

client = OpenAIClient.from_env()
agent = Agent(llm_client=client)
result = await agent.run("分析 sales.csv")
```

这对开发者没问题，但对最终用户不够友好。Phase 10.1 的目标是给 Agent 穿上一个
**命令行外壳**，让最常见的使用场景变成一行命令：

```bash
agent run "分析 sales.csv"
agent run --echo "hello"        # 无需 API key，快速验证
agent config --config hermes.yaml
```

### 核心设计

1. **argparse 做骨架**：
   - 子命令 `run` 负责执行 Agent。
   - 子命令 `config` 负责显示配置摘要。
   - `--version` 显示版本。
   - 所有参数都有对应的 CLI 覆盖项。

2. **参数优先级**：
   ```
   CLI 参数 > YAML 配置文件 > 代码默认值
   ```
   这让用户可以在不修改 YAML 的情况下临时调整行为，例如调试时加 `--max-turns 5`。

3. **无 API key 保护**：
   - 默认使用 `OpenAIClient.from_env()`，需要 `OPENAI_API_KEY`。
   - 未提供 key 时，`agent run` 会返回非 0 退出码并明确提示，而不是等到调用 API 时才报 401。
   - 提供 `--echo` 模式，使用 `EchoClient` 做无依赖测试。

4. **与现有代码解耦**：
   - 不修改 `Agent`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
   - CLI 只负责解析参数、加载配置、构造对象、调用 `Agent.run()`。

5. **UTF-8 输出处理**：
   - Windows 终端默认编码可能为 GBK，直接输出中文会乱码。
   - 在 `main()` 入口尝试 `sys.stdout.reconfigure(encoding="utf-8")`，
     失败时静默降级。

### 代码亮点

- **`agent_cli.py` 独立成文件**：不与 `memory_cli.py` 混在一个文件里，保持职责清晰。
- **`__main__.py` 支持 `python -m agent.cli`**：方便开发调试，无需安装包。
- **`pyproject.toml` 注册 console script**：安装后直接使用 `agent` 命令。
- **`SystemExit` 透传**：argparse 处理 `--version`/`--help` 时会调用 `parser.exit()`，
  CLI 入口捕获 `SystemExit` 并将退出码返回，避免在测试或调用方抛出异常。
- **API key 脱敏显示**：`agent config` 输出中 `api_key` 不会打印完整密钥。

### 踩过的坑

- **argparse `version` action 会抛 SystemExit**：直接调用 `main(["--version"])`
  会在测试中抛异常，需要捕获并透传退出码。
- **不同子命令参数不一致导致 AttributeError**：`config` 子命令没有 `api_key`、
  `base_url` 等参数，`_load_config()` 里用 `getattr(args, "api_key", None)` 防御。
- **路径 vs 包名冲突**：原计划 `src/agent/cli.py` 与已有 `src/agent/cli/` 包冲突，
  最终保留包结构，新增 `agent_cli.py`。

### 核心收获

1. **CLI 是"最后一公里"**：再强的 Agent，如果用户每次用都要写脚本，门槛就很高。
2. **配置分层很重要**：CLI 参数、YAML、默认值三层优先级让调试和部署都更灵活。
3. **测试要覆盖入口**：`python -m agent.cli --version` 和安装后的 `agent --version`
   都要验证，console script 注册错一行就会导致用户无法启动。
4. **先做加法、不做改造**：Phase 10.1 只新增 CLI 层，不动核心，风险可控。

### 质量状态

- `pytest tests/ -q` → 452 passed，1 skipped（新增 6 个 CLI 测试）
- `mypy src/` → 0 errors（36 source files）
- `ruff check src/ tests/` → 0 errors
- `agent --version` → `agent 0.1.0`
- `agent run --echo "hello"` → `You said: hello`

### 下一步

Phase 10.2：Rich 美化输出。在现有 CLI 骨架上引入 Rich，让配置摘要、运行结果、
错误提示更具可读性。

---

## Phase 10.2：Rich 美化输出 {#phase-102}

### 先理解：为什么 CLI 需要 Rich

Phase 10.1 的 CLI 已经能跑，但输出是「工程师友好、用户不友好」的纯文本：

```text
当前配置摘要：
  provider: openai
  model: gpt-4o
  max_turns: 20
```

对于最终用户，这种输出：
- 没有视觉层级，关键信息不突出
- 长结果（如代码、表格）难以阅读
- 错误信息容易被忽略

Rich 的价值不是"让输出变花"，而是**用视觉层级降低认知负担**。

### 核心设计

1. **渲染层独立为 `render.py`**：
   - `render_config()`：配置摘要 → 表格
   - `render_result()`：Agent 结果 → 面板
   - `render_error()`：错误信息 → 红色边框面板
   - 这样做让 `agent_cli.py` 只关心"调用什么"，不关心"怎么画"。

2. **`--plain` 模式**：
   - 默认开启 Rich。
   - `--plain` 禁用 Rich，输出纯文本。
   - 为什么必须有 `--plain`？
     - 脚本管道化：`| grep`、`| jq` 不需要 ANSI 转义序列。
     - 测试稳定：Rich 输出带边框和颜色，断言脆弱；`--plain` 提供稳定锚点。
     - 兼容旧终端：某些环境不支持 Unicode 边框。

3. **错误也用 Rich**：
   - 普通用户看到红色面板比看到 "Error: ..." 更容易意识到出错了。
   - 错误仍然输出到 `stderr`，不影响 stdout 管道。

4. **不炫技**：
   - 不做 spinner / progress bar：Agent.run 是异步多轮，集成 Live 会显著增加复杂度。
   - 不做自动代码语言检测：误判会适得其反；用 Markdown Panel 已经能正确渲染用户自己写的代码块。

### 代码亮点

- **Console(file=sys.stderr)**：Rich 的 `Console.print(..., stderr=True)` 不存在，需要单独构造输出到 stderr 的 Console。
- **`capsys` 与 Rich 兼容**：Rich 在非 TTY 下会自动 strip 颜色，但表格边框仍保留；测试里用 `--plain` 绕过。
- **参数优先级不变**：`--plain` 是全局参数，所有子命令共享。

### 踩过的坑

- **`Console.print` 没有 `stderr` 参数**：最初写成 `console.print(panel, stderr=True)`，直接 TypeError。正确做法是 `Console(file=sys.stderr)`。
- **Rich 输出断言脆弱**：如果测试去数边框字符，样式一改就挂。解决：Rich 只做 smoke test，断言标题存在即可；具体值用 `--plain` 断言。
- **`--plain` 要作为全局参数**：如果只在 `run` 子命令加，`agent --plain config` 会报错；在顶层 parser 加更自然。

### 核心收获

1. **CLI 的"颜值"是功能的一部分**：清晰的输出能降低用户试错成本。
2. **任何美化都必须提供逃生舱**：`--plain` 不是可有可无，是生产可用性的保障。
3. **测试要分层**： Rich 做 smoke test，纯文本做精确断言，二者互补。
4. **渲染层要独立**：把样式代码从业务逻辑里抽出来，后续换主题、换库都更容易。

### 质量状态

- `pytest tests/ -q` → 459 passed，1 skipped
- `mypy src/` → 0 errors（37 source files）
- `ruff check src/ tests/` → 0 errors
- `agent config` → Rich 表格
- `agent run --echo "hello"` → Rich 面板
- `agent --plain config` → 纯文本，无 ANSI

### 下一步

Phase 10.3：交互模式。让用户可以不退出 CLI 连续多轮对话。

---

## Phase 10.3：交互模式 {#phase-103}

### 先理解：为什么需要交互模式

`agent run "..."` 适合一次性任务，但很多场景需要连续对话：

```bash
You: 分析 sales.csv
Agent: [分析结果]
You: 再画一张按月统计的图
Agent: [图表]
You: 把结果保存到 report.md
Agent: [完成]
```

如果每次都要重新启动进程、重新加载上下文，体验会很差。交互模式让 Agent 在一个进程内持续服务。

### 核心设计

1. **`agent chat` 子命令**：
   - 进入循环，读取用户输入 → 调用 Agent → 渲染回复。
   - 复用同一个 `Agent` 实例，`Agent.messages` 自然累积。

2. **特殊命令以 `/` 开头**：
   - `/quit` / `/exit`：退出
   - `/help`：显示命令列表
   - `/clear`：清屏

3. **工具调用摘要**：
   - 不在 Agent 核心里加实时回调。
   - 在 `Agent.run()` 返回后，扫描 `agent.messages` 中本轮新增的 tool_call，显示简洁摘要。
   - 低耦合、可测试、不影响核心逻辑。

4. **`--plain` 全局可用**：
   - 预处理 `argv`，让 `--plain` 出现在子命令前后都能识别。
   - 这样 `agent --plain chat` 和 `agent chat --plain` 都合法。

5. **Ctrl+C 双层语义**：
   - 第一次：中止当前 `Agent.run()`，回到输入提示。
   - 第二次：退出会话。

### 为什么不做跨会话历史

原始 Phase 10 计划只写了"交互模式"四个字，没有要求会话持久化。把跨会话历史塞进 10.3 会：
- 引入文件/DB 设计，超出当前 Task 范围
- 与 Phase 8 记忆机制边界不清
- 增加测试和维护负担

所以 10.3 只做**单进程内多轮对话**，跨会话历史作为未来独立机制设计。

### 代码亮点

- **`chat.py` 独立模块**：交互循环与命令解析分离，便于后续扩展更多命令。
- **`run_chat_loop(agent, plain)` 接收已构造 Agent**：测试可以注入自定义 Agent（含 Mock LLM / Mock Tool）。
- **`Prompt.ask("You")`**：Rich 内置，无需新增依赖。
- **消息计数提取工具摘要**：通过比较 `Agent.run()` 前后的 `len(agent.messages)`，精确提取本轮 tool call。

### 踩过的坑

- **`--plain` 与子命令位置**：argparse 默认只允许全局参数在子命令前。预处理 `argv` 后同时支持前后两种写法。
- **`Console.print(panel, stderr=True)` 不存在**：错误输出需要构造 `Console(file=sys.stderr)`。
- **交互循环测试**：用 `monkeypatch` 替换 `Prompt.ask` 返回输入序列，避免阻塞在 stdin。

### 核心收获

1. **交互模式的关键是状态保持**：复用 Agent 实例比重建更自然。
2. **不要为展示需求修改核心**：事后扫描公开状态比实时回调更干净。
3. **全局参数要考虑位置习惯**：用户会自然地把 flag 放在子命令后面。
4. **范围控制**：原始计划没写的功能，不要顺手做，留到未来独立设计。

### 质量状态

- `pytest tests/ -q` → 468 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `agent chat --echo --plain` → 可进入并对话
- `agent chat --echo` → Rich 面板输出

### 下一步

Phase 10.4：示例场景脚本。编写几个典型使用场景的示例脚本，展示 Agent 如何解决实际问题。


## Phase 10.4：示例场景脚本 {#phase-104}

### 先理解：为什么示例脚本值得单独一个 Task

很多开源项目的 `examples/` 目录里放的是"能跑"但"没人维护"的脚本：

- 复制粘贴后报错，因为 API 已经变了。
- 依赖真实的外部服务（OpenAI、Docker），新用户第一步就跑不通。
- 没有测试，改了核心代码也不知道示例已经腐烂。

Phase 10.4 的目标是：**让 examples/ 成为项目的一部分，而不是被遗忘的角落。**

### 核心设计

1. **示例必须在无 API key 环境下可运行**：
   - 使用 `EchoClient` 替代 `OpenAIClient`。
   - CLI 示例使用 `--echo` 模式。
   - 注释中说明如何切换到真实 LLM。

2. **覆盖三种典型使用场景**：
   - `simple_agent.py`：最小 `Agent` 类用法 + 自定义 tool。
   - `run_once.py`：模拟 `agent run` 的单次任务。
   - `with_config.py` + `config.yaml`：YAML 配置驱动。

3. **示例也要有测试**：
   - `tests/test_examples.py` 验证每个示例可导入、可运行。
   - 验证示例配置文件可被 `load_config()` 解析。
   - 不严格断言输出内容，避免 EchoClient 行为变化导致测试脆弱。

4. **配置文件避免依赖 Docker**：
   - `examples/config.yaml` 使用 `subprocess` 后端，让用户无需 Docker daemon 也能跑示例。

### 为什么示例要脱离真实 LLM

原始 Phase 10.4 计划要求"展示典型使用场景"，但没有要求示例必须调用真实 LLM。如果强制要求 API key：

- 新用户 clone 项目后第一步就跑不通，体验差。
- CI 环境可能没有 API key，无法验证示例。
- 示例会暴露调用成本（每次跑测试都会消耗 token）。

所以示例先用 `EchoClient` 展示 API 用法，用户在注释指导下自行切换。

### 代码亮点

- **`importlib.util` 动态导入示例脚本**：避免把示例脚本加入 `sys.path`，保持测试隔离。
- **`pytest.mark.parametrize` 覆盖所有示例**：新增示例时只需在列表里加一行。
- **配置与客户端解耦**：`with_config.py` 加载配置后仍显式选择 `EchoClient`，说明"配置决定行为参数，代码决定使用哪个客户端"。

### 踩过的坑

- **`Path(__file__).with_suffix("").with_suffix(".yaml")` 的误用**：本来想按脚本名找同名 YAML，结果生成 `with_config.yaml`，与实际的 `config.yaml` 不一致。改为 `Path(__file__).parent / "config.yaml"` 更直观。
- **示例脚本的模块名冲突**：用 `importlib.util.spec_from_file_location` 导入时，需要手动把模块放入 `sys.modules`，否则相对导入会失败。
- **ruff import 排序**：测试文件里 `import` 和 `from` 顺序不对会被 I001 报错，用 `ruff check --fix` 自动整理。

### 核心收获

1. **示例是文档，也是测试**：好的示例降低用户上手成本，有测试的示例不会腐烂。
2. **无依赖示例更有价值**：新用户第一步能跑通，比"功能完整但跑不通"更重要。
3. **注释里要写明迁移路径**：告诉用户如何从 EchoClient 切换到真实 LLM。
4. **测试不要断言易变内容**：示例测试验证"能跑"即可，不要耦合 EchoClient 的具体输出格式。

### 质量状态

- `pytest tests/ -q` → 475 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `python examples/simple_agent.py` → 正常输出
- `python examples/run_once.py` → 正常输出
- `python examples/with_config.py` → 正常输出

### 下一步

Phase 10.5：Docker 一键启动。为项目提供 Docker Compose 或一键启动脚本，降低环境准备成本。


## Phase 10.5：Docker 一键启动 {#phase-105}

### 先理解：为什么需要一键启动脚本

Hermes Agent 的核心卖点是"让 LLM 在隔离沙箱里写代码并执行"。但这个能力有个强依赖：**Docker daemon 必须可用，且默认镜像要提前拉取**。

新用户常遇到两种挫败：

1. 兴冲冲跑 `agent run "..."`，结果工具调用报 `Docker client unavailable`。
2. 第一次执行代码时，Docker 才开始拉 `python:3.11-slim`，等很久。

Phase 10.5 就是要把"环境准备好了吗？"这件事显性化，让用户在正式用 Agent 前就能快速确认。

### 核心设计

1. **`scripts/setup-docker.py`**：
   - 检查 Docker daemon 是否可达（`docker.from_env().ping()`）。
   - 检查默认镜像 `python:3.11-slim` 是否已存在。
   - 不存在则尝试拉取。
   - 返回退出码：`0` 就绪，`1` 未就绪。
   - 用 Python 写而不是 Shell，是为了跨平台。

2. **`docker-compose.yml`**：
   - 提供一种"不想在宿主机装依赖"时的运行方式。
   - 挂载项目源码、Docker socket、`.hermes` 工作目录。
   - 透传 `OPENAI_API_KEY` 环境变量。

3. **测试使用 Mock**：
   - 不依赖真实 Docker daemon，CI 也能跑。
   - 覆盖 Docker 不可达、镜像已存在、镜像需拉取、拉取失败四种场景。

### 为什么不直接改 Agent 自动拉镜像

直觉上，可以让 `DockerSandboxBackend` 在镜像不存在时自动拉取。但：

- 这会修改核心沙箱层，超出 Phase 10.5 范围。
- 自动拉取可能引入意外延迟和失败，显式检查更符合"失败快速、原因清晰"的工程原则。
- 一键启动脚本可以做得更友好：中文提示、退出码、可选参数。

### 代码亮点

- **`check_docker_available()` 接收可选 client**：测试可以注入 Mock，也方便未来扩展。
- **`ensure_image()` 返回 `(bool, str)` 元组**：调用方既能知道成功失败，也能拿到人类可读的信息。
- **错误输出到 `stderr`**：符合 CLI 惯例，脚本管道使用时不会污染 stdout。

### 踩过的坑

- **`docker.from_env()` 在 Windows 上可能连接成功但拉取失败**：测试环境没有真实的 Docker 网络，所以真实运行时报网络错误；脚本正确返回 1，逻辑是对的。
- **终端编码导致中文输出乱码**：脚本本身输出 UTF-8，但 Windows 终端默认编码非 UTF-8。这是环境问题，已在 CLI 中处理，脚本保持简洁。
- **mypy 对 `docker` 包的类型支持**：`docker.from_env()` 返回类型需要 `DockerClient` 注解，确保 mypy 通过。

### 核心收获

1. **环境准备应该被显式检查**：不要让用户在第一次 tool 调用时才意识到 Docker 没开。
2. **Python 脚本比 Shell 更适合跨平台项目**：尤其是已经依赖 `docker` Python 包时。
3. **Mock 测试让 Docker 相关功能可 CI**：真实 Docker 环境不稳定，测试不应该依赖它。
4. **退出码很重要**：`0`/`1` 让脚本可以被其他工具链调用。

### 质量状态

- `pytest tests/ -q` → 483 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `python scripts/setup-docker.py` → 有 Docker 时返回 0，无 Docker 时返回 1 并提示

### 下一步

Phase 10.6：README 重写。把项目价值、安装步骤、快速开始写清楚，降低新用户上手门槛。


## Phase 10.6：README 重写 {#phase-106}

### 先理解：为什么 README 值得单独一个 Task

README 是项目的"门面"。很多用户不会先看代码，而是先看 README 决定是否值得用。一个差的 README 会：

- 代码示例跑不通，直接劝退。
- 没有讲清楚项目到底解决什么问题。
- 缺少安装和快速开始，用户不知道第一步做什么。

Phase 10.6 的目标不是写一份"看起来完整"的文档，而是写一份**能让新用户 5 分钟内跑起来**的指南。

### 核心设计

1. **从用户视角组织内容**：
   - 先看一句话价值（项目简介）。
   - 再看能解决什么问题（核心特性）。
   - 再看需要什么（前置条件）。
   - 再看怎么装（安装）。
   - 最后看怎么跑（快速开始）。

2. **修正所有错误示例**：
   - `from agent.core import Agent` → `from agent import Agent`。
   - `agent.run(...)` 是异步函数，示例加 `asyncio.run()`。

3. **覆盖两种使用方式**：
   - CLI：`agent run`、`agent chat`。
   - Python 代码：直接构造 `Agent`。

4. **补充 Docker 和配置**：
   - 说明 Docker 是代码沙箱的强依赖。
   - 给出 `scripts/setup-docker.py` 和 `docker compose` 的使用方式。
   - 给出 YAML 配置示例。

5. **用测试防止 README 腐烂**：
   - `tests/test_readme.py` 检查关键章节是否存在。
   - 用 `ast.parse()` 验证所有 Python 代码块语法正确。

### 为什么 README 也需要测试

因为 README 里的代码示例是"看起来不会错，其实很容易错"的重灾区。一个常见的陷阱：

- 你改了核心 API（比如把 `Agent` 从 `agent.core.engine` 移到 `agent`）。
- 代码里所有 import 都更新了。
- 但 README 里的旧示例没人记得改。

`tests/test_readme.py` 就是为了在 CI 阶段抓住这种不一致。

### 代码亮点

- **正则匹配章节标题**：使用 `^##\s+章节名` 确保关键章节存在。
- **提取 Markdown Python 代码块**：用 ````python\n(.*?)\n```` 非贪婪匹配。
- **`ast.parse()` 不做执行**：只检查语法，不触发 API/Docker 调用。

### 踩过的坑

- **README 原有示例路径错误**：`from agent.core import Agent` 实际上导不出 `Agent`，正确是 `from agent import Agent`。
- **异步示例缺少 `asyncio.run()`**：`agent.run()` 是 coroutine，直接调用会返回 coroutine 对象而不是结果。
- **Windows 终端编码问题**：测试中读取文件时显式指定 `encoding="utf-8"`，避免 GBK 解析 UTF-8 文件出错。

### 核心收获

1. **README 是产品的一部分**：不是写完就丢的文档。
2. **示例代码必须可运行**：用户复制粘贴后应该直接成功。
3. **用测试保护文档**：和代码一样，文档也会腐烂。
4. **结构比辞藻重要**：先让用户知道"这是什么、为什么用、怎么用"。

### 质量状态

- `pytest tests/ -q` → 491 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `README.md` 关键章节完整
- Python 代码块语法检查通过

### 下一步

Phase 10.7：架构图（ASCII）。在 `docs/architecture.md` 中用 ASCII 图展示系统组件关系。


## Phase 10.7：架构图（ASCII） {#phase-107}

### 先理解：为什么面试项目需要好的架构图

面试时，面试官通常不会一行行看你的代码。他们更关心：

> **"这个系统有哪些模块？它们怎么协作？数据怎么流？遇到错误怎么处理？"**

一张好的架构图能让你在 30 秒内把设计讲清楚。而 ASCII 图的优势是：

- 直接写在 Markdown 里，不需要外部工具或图片。
- 版本控制友好，diff 可见。
- 不引入新依赖（如 Mermaid.js 需要渲染支持）。

### 核心设计

Phase 10.7 在 `docs/architecture.md` 中画了四张 ASCII 图：

1. **组件架构图**：
   - 横向分层：CLI 层 → Agent Core → 基础设施层（LLM / Sandbox / Memory）。
   - 展示 `Agent`、`ToolRegistry`、`Tools`、`DockerSandboxBackend`、`MemoryManager`、`PolicyEngine` 等核心组件的静态关系。

2. **主循环数据流图**：
   - 展示 `Agent.run()` 的循环：用户输入 → 构造消息 → LLM → 纯文本或 tool_calls → 工具执行 → 结果回传 → 再次调用 LLM。
   - 强调"循环直到无 tool_calls"。

3. **执行序列图**：
   - 用时序方式展示一次典型的自我纠错过程。
   - 包含 `User`、`Agent`、`LLMClient`、`ToolRegistry`、`Sandbox`、`ErrorClassifier` 六个参与者的交互。
   - 清晰展示：生成代码 → 执行失败 → 错误分类 → 修正 → 成功 → 返回结果。

4. **记忆与安全扩展图**：
   - 说明 `MemoryManager.inject()` 和 `MemoryManager.record()` 如何挂在主循环前后。
   - 说明 `PolicyEngine.evaluate()` 在 ToolRegistry 执行前的拦截位置。

### 为什么用 ASCII 而不用 Mermaid

Mermaid 语法更现代、更美观，但有两个问题：

- 不是所有 Markdown 渲染器都支持（比如某些 Git 查看器、静态站点生成器）。
- 需要引入 Mermaid 依赖或依赖外部 CDN。

ASCII 图虽然"丑"一点，但：

- 零依赖。
- 在任何文本环境下都能正常显示。
- 与代码一样受版本控制保护。

对于工程类项目，"可维护、可复现"比"好看"更重要。

### 代码亮点

- **图宽控制在 80 字符以内**：适配终端窄屏和 PDF 导出。
- **中文注释 + 英文组件名**：兼顾可读性与技术准确性。
- **每张图后附文字说明**：避免只看图不理解设计意图。
- **用测试保护文档**：`tests/test_architecture.py` 检查章节存在、至少 3 张 ASCII 图、图中有框线字符。

### 踩过的坑

- **代码块统计正则**：`docs/architecture.md` 中既有普通文本列表，也有 ``` 代码块。测试需要准确识别代码块数量，而不是把列表项也算进去。
- **框线字符检测**：需要确保 ASCII 图确实使用了框线字符（如 `┌`、`│`、`►`），而不是普通文本列表。
- **图的维护成本**：ASCII 图手工调整比较麻烦，未来如果组件关系大改，需要同步更新。但因为它在版本控制中，diff 会提醒维护者。

### 核心收获

1. **架构图是沟通工具**：面向面试官和用户，不是给自己看的。
2. **一张图讲一个维度**：组件关系、数据流、时序三者不要混在一张图里。
3. **ASCII 图适合技术文档**：零依赖、版本可控、随处可显示。
4. **文档也要防腐烂**：用测试确保关键章节和图不丢失。

### 质量状态

- `pytest tests/ -q` → 496 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `docs/architecture.md` 包含 4 张 ASCII 图
- 关键章节测试通过

### 下一步

Phase 10.9：Demo 脚本与录制准备。设计一条无 API Key 可运行的端到端演示流程，并准备截图/录制说明。


## Phase 10.9：Demo 脚本与录制准备 {#phase-109}

### 先理解：为什么 Demo 不等于"录视频"

很多人一听到 Demo 就想到录制视频或做 GIF。但对于面试项目，Demo 的核心价值是：

> **证明这个 Agent 在真实 LLM 驱动下，能完成一个端到端任务。**

视频只是呈现形式，真正的资产是**可一键运行的脚本**。面试官更可能让你现场运行脚本，而不是看你提前录好的视频。

### 核心设计

Phase 10.9 做了三件事：

1. **`examples/demo_real_llm.py`**
   - 默认使用真实 LLM，展示完整 Agent 工作流。
   - 支持 `--prompt` 自定义任务、`--config` 加载配置、`--model` 覆盖模型。
   - 支持 `--echo` 模式，无 API Key 时也能跑通，用于 CI 和预演。
   - 无 Key 时打印友好提示，而不是崩溃。

2. **`tests/test_demo.py`**
   - 测试 `--help` 正常退出。
   - 测试 `--echo` 模式在无 Key 下可运行。
   - 测试无 Key 时打印配置说明。

3. **`docs/demo.md`**
   - 说明如何运行真实 LLM 模式、`--echo` 模式、预期输出和常见问题。

### 为什么默认要真实 LLM

Mock 或 EchoClient 只能证明"代码流程没问题"。但 Agent 的核心能力——工具选择、错误理解、自我纠正——都依赖真实 LLM 的输出质量。面试时如果只展示 EchoClient，面试官无法判断你的 Agent 是否真的能 work。

所以这个 Demo 的设计是：

- **默认真实 LLM**：有 Key 时直接展示真实能力。
- **无 Key 可降级**：今天没有 Key，也能跑 `--echo` 和无 Key 提示路径；明天有了 Key，同一脚本直接升级。

### 踩过的坑

- **`runpy.run_path()` 会抛出 `SystemExit`**：Demo 脚本内部使用 `raise SystemExit(main())`，测试时需要 `pytest.raises(SystemExit)` 捕获。
- **无 Key 时的退出码选择**：返回 0 更友好（Demo 不是错误，只是条件不满足），测试中也断言 0。
- **stdout 编码**：Windows 终端默认 GBK，脚本里强制 UTF-8 避免中文乱码。

### 核心收获

1. **Demo 脚本首先是可运行脚本，其次才是展示材料**。
2. **真实 LLM 是展示核心**，Mock 只能做兜底。
3. **测试要覆盖无 Key 路径**，否则 CI 会挂。
4. **Phase 10 全部完成**：从 CLI、示例、README、架构图、使用文档到 Demo，项目工程面已经闭环。

### 质量状态

- `pytest tests/ -q` → 509 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `python examples/demo_real_llm.py --echo` 可正常运行
- `python examples/demo_real_llm.py` 无 Key 时打印友好提示

### 下一步

Phase 10 全部完成。后续方向由实际面试或用户需求决定：

- 真实 LLM 联调：明天提供 API Key 后运行 Demo，观察 tool call 效果。
- 功能增强：补齐 `subprocess` 后端、镜像源配置、流式输出等。
- 面试整理：准备项目亮点口述、优化 README 首页。


## Phase 10.8：使用文档 {#phase-108}

### 先理解：为什么使用文档值得单独一个 Task

README 解决"5 分钟上手"的问题，但它不可能覆盖所有细节。当用户真正想把 Hermes Agent 用到自己的项目或工作流里时，会遇到更多具体问题：

- `agent run` 和 `agent chat` 各自适合什么场景？
- YAML 配置里每个字段的默认值和覆盖优先级是什么？
- 没有 API Key 时能不能先把流程跑通？
- 自定义 tool 该怎么写参数 schema？
- `--backend subprocess` 为什么不生效？

Phase 10.8 的目标就是回答这些问题，把项目从"能跑"推进到"能用"。

### 核心设计

Phase 10.8 新增两份文档：

1. **`docs/usage.md`：使用指南**
   - CLI 三个子命令的完整用法：`agent run`、`agent chat`、`agent config`。
   - Python API 示例：EchoClient、OpenAIClient、加载 YAML 配置、注册自定义 tool、获取执行轨迹。
   - 常见问题：没有 API Key 怎么测、Docker 失败怎么办、`subprocess` 后端为什么不生效。

2. **`docs/configuration.md`：配置参考**
   - 配置文件整体结构。
   - `llm`、`agent`、`sandbox`、`security`、`tools` 各节点字段详解。
   - 完整 YAML 示例与加载示例。

3. **`tests/test_usage_docs.py`：文档防腐测试**
   - 关键章节存在性检查。
   - 所有 ````python` 代码块通过 `ast.parse()` 语法检查。

### 为什么文档也需要测试

代码会变，文档很容易滞后。一个典型的腐烂场景：

- 你把 `Agent` 的构造参数改了。
- 源码和测试都更新了。
- README 和 usage.md 里的示例还是旧的，用户复制粘贴后直接报错。

`tests/test_usage_docs.py` 用 `ast.parse()` 检查所有 Python 代码块。只要示例语法不正确（比如 import 路径错误、函数签名不匹配导致语法错误），CI 就会失败。虽然它不能检查运行时语义，但已经能拦住大部分的"文档与代码不同步"。

### 代码亮点

- **示例优先使用 EchoClient / `--echo`**：让没有 API Key 的用户也能验证流程。
- **所有示例都是当前实际 API**：`from agent import Agent`、`OpenAIClient.from_env()`、`load_config()`、`ToolSpec`。
- **诚实记录技术债**：在文档和 FAQ 中明确说明 `subprocess` 后端尚未真正实现，避免误导。
- **配置字段表使用 Markdown 表格**：字段、类型、默认值、说明一目了然。

### 踩过的坑

- **Markdown 代码块提取要区分 ```python 和普通 ```**：`ast.parse()` 只应该检查 Python 代码块，不要把 shell 或 YAML 块也丢进去。
- **示例代码必须语法正确**：比如 `OpenAIClient.from_env(api_key=config.llm.api_key or None)` 这种写法在示例中没问题，但要确保整体代码块能 `ast.parse()` 通过。
- **路径与导入要随源码同步**：`from agent import Agent` 是目前正确导出，`from agent.core.engine import Agent` 虽然也能工作但不推荐。文档统一使用前者。

### 核心收获

1. **文档是产品的一部分**：和代码一样需要测试、需要随版本更新。
2. **示例代码必须可运行**：用户复制粘贴后应该直接成功，否则文档就是"反入门"。
3. **诚实面对未实现功能**：明确标注 `subprocess` 未落地，比让用户踩坑后失望更好。
4. **用轻量测试保护文档**：`ast.parse()` 成本低、收益高，是文档类项目的标准做法。

### 质量状态

- `pytest tests/ -q` → 506 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `docs/usage.md` 关键章节完整
- `docs/configuration.md` 关键章节完整
- Python 代码块语法检查通过

### 下一步

Phase 10.9：Demo 脚本与录制准备。设计一条无 API Key 可运行的端到端演示流程，并准备截图/录制说明。


## 评测日志体系 {#evaluation-log}

### 先理解：为什么面试项目需要“评测日志”

面试项目和玩具 demo 最大的区别之一是：**你能不能用数据说话。**

很多候选人在简历上写：

> “实现了具备自我纠错能力的代码沙箱 Agent。”

但面试官追问：

- “你们测试了多少个 case？”
- “真实 LLM 的 tool call 成功率是多少？”
- “优化前后延迟/轮数/token 消耗有什么变化？”
- “你发现了哪些 Bug，怎么修的？”

如果没有记录，这些问题很难回答清楚。评测日志就是为了把“做过的测试、发现的问题、优化的效果”沉淀成可量化的资产。

### 核心设计

新增三份文件：

1. **`docs/evaluation-log.md`**：实际日志。
   - 项目基线：测试数、类型检查、lint、已知限制。
   - 测试环境：OS、Python、模型、Base URL、Docker 状态。
   - 端到端测试结果表：日期、场景、模型、轮数、结果、耗时、关键问题。
   - Bug 与问题清单：ID、描述、严重度、根因、修复、状态。
   - 优化记录：日期、模块、优化前、优化后、提升、STAR 摘要。
   - 简历 STAR 素材：可直接写入简历的 STAR 段落。
   - Action Items：下一步待办。

2. **`.kimi/vibe_specs/evaluation-spec.md`**：规格。
   - 定义记录格式、更新时机、跨会话阅读顺序。

3. **`tests/test_evaluation_log.py`**：结构测试。
   - 确保 `evaluation-log.md` 的关键章节始终存在，防止腐烂。

### 为什么用 Markdown 表格而不是数据库

面试项目的评测数据量不大，用 Markdown 表格有独特优势：

- **版本可控**：每次更新都在 git diff 里清晰可见。
- **低门槛**：不需要部署数据库或额外工具。
- **可直接引用**：写简历时直接复制 STAR 段落。
- **测试可守护**：用正则检查章节标题即可。

### 关键维护规则

- **每次真实 LLM 测试后**：追加一行测试结果。
- **每次 Bug 修复后**：更新 Bug 清单状态。
- **每次优化后**：必须记录可量化的前后指标。
- **新 session 启动必读**：`progress-spec` → `session-context` → `evaluation-log` → `CODEMAP`。

### 已经记录的第一条数据

| 日期 | 场景 | 模型 | 轮数 | 结果 | 耗时 | 关键问题 |
|---|---|---|---|---|---|---|
| 2026-07-15 | 编写并验证 `fibonacci(n)` | deepseek-chat | 5 | 成功 | ~12s | 初始脚本忽略环境变量，已修复 |

这条记录不仅是一个测试结果，也是一个完整的 STAR 故事：

> **S**：需要在无 OpenAI 访问权限的环境下演示 Agent。  
> **T**：让 Demo 脚本支持 DeepSeek 等兼容端点。  
> **A**：调整参数优先级为 CLI > 环境变量 > 配置 > 默认值。  
> **R**：成功在 DeepSeek 上跑通端到端任务，5 轮完成，耗时约 12 秒。

### 踩过的坑

- **章节标题带编号导致测试失败**：最初写成 `## 1. 项目基线`，测试的正则无法匹配。改为 `## 项目基线` 后通过。
- **日志容易写成流水账**：必须强制分章节，特别是“优化记录”要有前后指标，否则失去价值。

### 核心收获

1. **数据是面试的底气**：有记录的优化和测试结果，比口头描述更有说服力。
2. **STAR 段落应该提前写好**：不要等到投简历时才临时编。
3. **文档也要防腐烂**：用测试守护关键章节。
4. **评测日志让项目从“完成”变成“可展示”**。

### 质量状态

- `pytest tests/ -q` → 516 passed，1 skipped
- `mypy src/` → 0 errors（38 source files）
- `ruff check src/ tests/` → 0 errors
- `docs/evaluation-log.md` 关键章节完整

### 下一步

- 解决 Docker 镜像问题，在真实沙箱中重复运行 Demo，记录 tool 执行成功率。
- 设计更复杂的场景（如 CSV 数据分析），验证多工具协作。
- 开始准备简历和口述介绍，把 STAR 素材落地。
