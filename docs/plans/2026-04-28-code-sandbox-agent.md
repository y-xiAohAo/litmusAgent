# Code Sandbox Agent — 完整实施计划

> **For Hermes:** 使用 TDD 方法论，每个 task 严格遵循 RED-GREEN-REFACTOR 循环。
>
> **Goal:** 构建一个具备自我纠错能力的代码执行 Agent——Agent 写代码→执行→观察结果→修正→交付产物。
>
> **Architecture:** Agent 核心引擎（Plan-Execute-Observe-Reflect 循环）→ 工具路由器（sandbox_exec / file_ops / finish）→ 沙箱层（Docker隔离执行，子进程fallback）。
>
> **Tech Stack:** Python 3.10+, Pydantic v2, httpx, Rich, pytest, Docker SDK, structlog
>
> **Prerequisites:** Docker Desktop（Phase 3 之前安装，Phase 1-2 不依赖）

---

## 环境现状

| 项目 | 状态 |
|------|------|
| Python 3.14.3 | ✅ |
| httpx, pydantic | ✅ 已安装 |
| pytest, mypy, ruff | ❌ 需 `pip install -e ".[dev]"` |
| Docker Engine | ❌ 需安装 Docker Desktop |
| docker-py (Python SDK) | ❌ 需 `pip install docker` |
| Git repo | ✅ 1 commit，branch: master |

---

## Phase 1: 修地基 — 让项目能跑、能测、能 lint

> **学习目标:** 理解 Python 工程规范——src-layout, pyproject.toml 配置, type hints, TDD 节奏

### Task 1.1: 安装 dev 依赖并验证工具链

**Objective:** 确保 pytest / mypy / ruff 可用

**Files:** 无新增

**Step 1:** 安装
```bash
cd /d/djh/hermes/project1
pip install -e ".[dev]"
```

**Step 2:** 验证
```bash
pytest --version        # should show 8.x
mypy --version          # should show 1.x
ruff --version           # should show 0.x
```

**Step 3:** 运行现有测试确认基线
```bash
pytest tests/ -v        # 预期：2-3 个 pass（EchoClient 的测试）
```

**Step 4:** Commit
```bash
# 如果 pyproject.toml 或 requirements.txt 有改动就 commit
```

---

### Task 1.2: 修复 types.py — 拆分 core/__init__.py

**Objective:** 修复 `engine.py: from agent.core.types import ...` 会失败的问题

**原因:** types 定义在 `core/__init__.py` 里，但 engine.py 期望独立 `core/types.py`

**Files:**
- Create: `src/agent/core/types.py`
- Modify: `src/agent/core/__init__.py`
- Validate: `src/agent/core/engine.py`, `src/agent/tools/__init__.py`

**Step 1: 写测试（验证 import 不报错）**

```python
# tests/test_imports.py (新文件)
"""Test that all key modules import cleanly."""

def test_import_agent():
    from agent import Agent, Message, ToolCall, ToolResult
    assert Agent is not None

def test_import_core_types():
    from agent.core.types import Message, ToolCall, ToolResult, ToolSpec
    assert Message is not None

def test_import_engine():
    from agent.core.engine import Agent, ToolRegistry
    assert Agent is not None

def test_import_llm():
    from agent.llm import BaseLLMClient, EchoClient, OpenAIClient
    assert BaseLLMClient is not None
```

**Step 2:** 跑测试 → 预期 FAIL（`No module named 'agent.core.types'`）

**Step 3:** 实施：
- 把 `core/__init__.py` 里的 Message/ToolCall/ToolResult/ToolSpec 定义移到 `core/types.py`
- `core/__init__.py` 改为 `from agent.core.types import ...`
- 确保 `engine.py` 和 `tools/__init__.py` 的 import 不受影响

**Step 4:** 跑测试 → 预期 PASS

**Step 5:** Commit: `fix: extract types to core/types.py, fix import path`

---

### Task 1.3: 添加 structlog + pyyaml 到依赖

**Objective:** 引入结构化日志和配置管理基础库

**Files:** Modify `pyproject.toml`, `requirements.txt`

**Step 1:** 在 pyproject.toml 的 dependencies 中添加：
```toml
"structlog>=24.0.0",
"pyyaml>=6.0",
"docker>=7.0.0",
```

**Step 2:** 同步到 requirements.txt

**Step 3:** `pip install -e ".[dev]"` 安装新依赖

**Step 4:** 写测试确认可 import
```python
def test_can_import_structlog():
    import structlog
    assert structlog is not None

def test_can_import_yaml():
    import yaml
    assert yaml is not None
```

**Step 5:** Commit: `chore: add structlog, pyyaml, docker to dependencies`

---

### Task 1.4: 创建 config.py — Agent 配置加载

**Objective:** 提供 YAML 配置文件加载，支持 LLM API key、模型选择、沙箱配置

**Files:**
- Create: `src/agent/config.py`
- Create: `tests/test_config.py`

**Step 1: 写失败测试**

```python
# tests/test_config.py
import tempfile
import os
from agent.config import AgentConfig, load_config

SAMPLE_YAML = """
llm:
  provider: openai
  model: gpt-4o
  api_key: sk-test123
  base_url: https://api.openai.com/v1
  temperature: 0.3
  max_tokens: 4096

agent:
  max_turns: 15
  system_prompt: "You are a data analyst."

sandbox:
  backend: docker
  image: python:3.11-slim
  timeout: 30
  memory_limit_mb: 256
"""

def test_load_config_from_yaml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(SAMPLE_YAML)
        path = f.name
    try:
        config = load_config(path)
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"
        assert config.agent.max_turns == 15
        assert config.sandbox.timeout == 30
    finally:
        os.unlink(path)

def test_config_defaults():
    config = AgentConfig()
    assert config.agent.max_turns == 20
    assert config.sandbox.backend == "docker"
```

**Step 2:** 跑测试 → FAIL

**Step 3:** 实现 `src/agent/config.py`（Pydantic 模型 + YAML 加载）

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: add AgentConfig with YAML loading`

---

### Task 1.5: 配置 structlog 日志

**Objective:** 统一日志输出，支持结构化 + 彩色终端输出

**Files:**
- Create: `src/agent/logging.py`
- Modify: `src/agent/__init__.py`

**Step 1:** 写测试
```python
def test_logger_outputs_message(capsys):
    from agent.logging import get_logger
    logger = get_logger("test")
    logger.info("hello", user="alice")
    captured = capsys.readouterr()
    assert "hello" in captured.err
```

**Step 2:** 实现 structlog 配置（开发模式彩色输出，生产 JSON）

**Step 3:** 跑测试 → PASS

**Step 4:** Commit: `feat: structured logging with structlog`

---

## Phase 2: Agent 核心引擎

> **学习目标:** 理解 Agent 主循环、状态管理、tool routing、错误恢复——Agent 架构的核心

### Task 2.1: Agent 主循环 — 单轮无工具对话

**Objective:** Agent 收到用户消息 → 调 LLM → 返回纯文本（无 tool call）

**Files:**
- Modify: `src/agent/core/engine.py`（重写 Agent.run()）
- Create: `tests/test_agent_loop.py`

**KEY INSIGHT:** Agent 的本质是一个循环——调 LLM → 看 response → 有 tool call？执行 → 把结果喂回去 → 再调 LLM → 直到没有 tool call

**Step 1: 写失败测试**

```python
# tests/test_agent_loop.py
import pytest
from agent.core.engine import Agent
from agent.llm import EchoClient

@pytest.mark.asyncio
async def test_agent_simple_response_no_tools():
    """Agent should return LLM response when no tools are called."""
    agent = Agent(
        llm_client=EchoClient(),
        system_prompt="You are helpful."
    )
    response = await agent.run("hello")
    assert response == "You said: hello"

@pytest.mark.asyncio
async def test_agent_builds_message_history():
    """Agent should track conversation history."""
    agent = Agent(llm_client=EchoClient())
    await agent.run("msg1")
    assert len(agent.messages) == 2  # user + assistant
    await agent.run("msg2")
    assert len(agent.messages) == 4  # accumulated
```

**Step 2:** 跑测试 → FAIL（Agent.run() 当前逻辑基于旧的 tool loop）

**Step 3:** 重写 Agent.run()：

```
run(user_input):
  messages.append(Message(user, user_input))
  loop:
    response = llm.chat(messages, tools)
    messages.append(Message(assistant, response.content, response.tool_calls))
    if not response.tool_calls:
      return response.content
    for each tool_call:
      result = tools.execute(tool_call)
      messages.append(Message(tool, result.content, tool_call_id=...))
```

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: agent single-turn dialogue without tools`

---

### Task 2.2: Agent 主循环 — Tool Call 执行

**Objective:** LLM 返回 tool call → Agent 执行 tool → 结果返回 LLM → 继续

**Files:** Modify `src/agent/core/engine.py`

**Step 1: 写测试**

```python
from agent.llm import BaseLLMClient

class ToolCallingMockClient(BaseLLMClient):
    """Mock that requests a tool then gives final answer."""
    def __init__(self):
        self.call_count = 0

    async def chat(self, messages, tools=None, **kwargs):
        self.call_count += 1
        if self.call_count == 1:
            # First call: request the tool
            return {
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'}
                }]
            }
        else:
            # Second call: tool result received, give final answer
            return {"content": "The result is 5.", "tool_calls": None}

@pytest.mark.asyncio
async def test_agent_executes_tool_call():
    agent = Agent(llm_client=ToolCallingMockClient())
    agent.tools.register(ToolSpec(
        name="add",
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
        handler=lambda a, b: a + b,
    ))
    response = await agent.run("add 2 and 3")
    assert response == "The result is 5."
    assert len(agent.messages) == 4  # user, assistant+toolcall, tool, assistant
```

**Step 2:** 跑测试 → FAIL（当前 `_build_openai_messages` 不处理 tool role 消息）

**Step 3:** 修复 `_build_openai_messages()` 支持 `role=tool` 的消息

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: agent tool call execution loop`

---

### Task 2.3: State — 执行状态管理

**Objective:** Agent 需要追踪"当前在执行哪个子任务"、"已安装了什么包"等上下文

**Files:**
- Create: `src/agent/core/state.py`
- Create: `tests/test_state.py`

**KEY INSIGHT:** Agent 不是无状态的。执行数据分析任务时，需要记住"CSV 已经加载了"、"pandas 已经 import 了"。这超越了简单的 message history。

**Step 1: 写测试**

```python
from agent.core.state import AgentState, ExecutionContext

def test_state_tracks_execution_phases():
    state = AgentState()
    state.set_phase("planning")
    assert state.phase == "planning"
    state.set_phase("executing", step="load_data")
    assert state.phase == "executing"
    assert state.current_step == "load_data"

def test_state_stores_artifacts():
    state = AgentState()
    state.add_artifact("chart.png", {"type": "image", "path": "/tmp/chart.png"})
    assert "chart.png" in state.artifacts
    assert state.artifacts["chart.png"]["type"] == "image"

def test_execution_context_isolation():
    ctx = ExecutionContext()
    ctx.set("packages_installed", ["pandas", "numpy"])
    assert ctx.get("packages_installed") == ["pandas", "numpy"]
    # Missing keys return None
    assert ctx.get("nonexistent") is None
```

**Step 2:** 跑测试 → FAIL

**Step 3:** 实现 `AgentState` 和 `ExecutionContext`（轻量 dataclass）

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: agent execution state tracking`

---

### Task 2.4: Error Handler — 错误分级与恢复

**Objective:** Agent 执行出错时，不直接崩溃，而是分析错误类型决定策略

**Files:**
- Create: `src/agent/core/error_handler.py`
- Create: `tests/test_error_handler.py`

**KEY INSIGHT:** 这是 Agent 和普通脚本的本质区别——Agent 需要像人类程序员一样读报错、判断严重程度、决定怎么修。

**Step 1: 写测试**

```python
from agent.core.error_handler import ErrorClassifier, ErrorSeverity, RecoveryAction

def test_classify_syntax_error():
    error = SyntaxError("invalid syntax", ("<sandbox>", 1, 10, "x = "))
    severity, action = ErrorClassifier.classify(error)
    assert severity == ErrorSeverity.RECOVERABLE
    assert action == RecoveryAction.REWRITE_CODE

def test_classify_name_error():
    error = NameError("name 'df' is not defined")
    severity, action = ErrorClassifier.classify(error)
    assert severity == ErrorSeverity.RECOVERABLE
    assert action == RecoveryAction.CHECK_CONTEXT

def test_classify_timeout():
    error = TimeoutError("execution exceeded 30s")
    severity, action = ErrorClassifier.classify(error)
    assert severity == ErrorSeverity.DEGRADE
    assert action == RecoveryAction.SIMPLIFY_TASK

def test_classify_unknown_error():
    error = Exception("something weird happened")
    severity, action = ErrorClassifier.classify(error)
    assert severity == ErrorSeverity.FATAL
```

**Step 2:** 跑测试 → FAIL

**Step 3:** 实现 ErrorClassifier（错误类型 → 严重级别 → 恢复策略的映射表）

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: error classification and recovery strategy`

---

### Task 2.5: Planner — 任务分解

**Objective:** 用户说"分析 sales.csv"，Agent 先分解成步骤再逐步执行

**Files:**
- Create: `src/agent/core/planner.py`
- Create: `tests/test_planner.py`

**KEY INSIGHT:** Planner 不是必需的（LLM 可以隐式规划），但显式规划让 Agent 行为可预测、可调试、可中断。

**Step 1: 写测试**

```python
from agent.core.planner import TaskPlan, PlanStep

def test_plan_has_steps():
    plan = TaskPlan(goal="Analyze sales data")
    plan.add_step("load", "Read sales.csv into dataframe")
    plan.add_step("clean", "Remove null values")
    plan.add_step("analyze", "Group by month and sum revenue")
    assert len(plan.steps) == 3
    assert plan.current_step is None

def test_plan_progression():
    plan = TaskPlan("Test")
    plan.add_step("step1", "First")
    plan.add_step("step2", "Second")
    plan.start_next()  # → step1
    assert plan.current_step.name == "step1"
    plan.complete_current()
    plan.start_next()  # → step2
    assert plan.current_step.name == "step2"
    plan.complete_current()
    assert plan.is_complete()

def test_plan_to_prompt():
    plan = TaskPlan("Do X")
    plan.add_step("a", "Thing A")
    plan.add_step("b", "Thing B")
    prompt = plan.to_progress_prompt()
    assert "Step 1/2" in prompt
    assert "Thing A" in prompt
```

**Step 2:** 跑测试 → FAIL

**Step 3:** 实现 TaskPlan 和 PlanStep（dataclass，状态机）

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: task planning and step progression`

---

### Task 2.6: Tool Router — 智能工具选择

**Objective:** Agent 有多个 tool 时，需要在 system prompt 中引导 LLM 正确选择

**Files:**
- Create: `src/agent/core/tool_router.py`
- Create: `tests/test_tool_router.py`

**Step 1: 写测试**

```python
from agent.core.tool_router import ToolRouter
from agent.core.types import ToolSpec

def test_router_generates_system_guidance():
    tools = {
        "sandbox_exec": ToolSpec(
            name="sandbox_exec",
            description="Execute Python code in sandbox",
            parameters={},
            handler=lambda: None,
        ),
        "finish": ToolSpec(
            name="finish",
            description="Mark task as complete and deliver result",
            parameters={},
            handler=lambda: None,
        ),
    }
    router = ToolRouter(tools)
    guidance = router.build_routing_prompt()
    assert "sandbox_exec" in guidance
    assert "finish" in guidance
    assert "when to use" in guidance.lower()

def test_router_identifies_required_tool():
    # Given a plan step, router suggests which tool category fits
    router = ToolRouter({})
    step = type("Step", (), {"description": "load CSV file and clean data"})()
    suggestion = router.suggest_tool(step)
    assert suggestion == "sandbox_exec"
```

**Step 2:** 跑测试 → FAIL

**Step 3:** 实现 ToolRouter（tool 分类 + prompt 生成 + 简单规则匹配）

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: tool router with intelligent selection guidance`

---

### Task 2.7: 集成 — Agent + Planner + ErrorHandler

**Objective:** 把 Phase 2 的组件串起来，形成一个完整的 Agent 引擎

**Files:** Modify `src/agent/core/engine.py`

**Step 1: 写集成测试**

```python
@pytest.mark.asyncio
async def test_full_agent_with_planner_and_error_recovery():
    """Simulate a full run: plan → execute → error → recover → complete."""
    # Use a mock LLM that simulates a realistic flow
    class RealisticMockClient(BaseLLMClient):
        def __init__(self):
            self.step = 0
        async def chat(self, messages, tools=None, **kwargs):
            self.step += 1
            responses = [
                # Turn 1: plan the task
                {"content": "I'll read the CSV first.", "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "sandbox_exec",
                                 "arguments": '{"code": "import pandas as pd; df = pd.read_csv(\'data.csv\'); print(df.head())"}'}
                }]},
                # Turn 2: code error, LLM sees tool result with error
                {"content": None, "tool_calls": [{
                    "id": "c2", "type": "function",
                    "function": {"name": "sandbox_exec",
                                 "arguments": '{"code": "import pandas as pd; print(pd.read_csv(\'data.csv\').columns.tolist())"}'}
                }]},
                # Turn 3: got columns, now finish
                {"content": "The CSV has columns: name, date, revenue. Analysis complete.", "tool_calls": None},
            ]
            # Safety: if we run out of predefined responses, return finished
            if self.step > len(responses):
                return {"content": "Done.", "tool_calls": None}
            return responses[self.step - 1]

    agent = Agent(llm_client=RealisticMockClient())

    errors_caught = []
    async def sandbox(code):
        if "df.head()" in code:
            raise NameError("name 'pd' is not defined")
        if "columns.tolist" in code:
            return "['name', 'date', 'revenue']"
        return "ok"

    agent.tools.register(ToolSpec(
        name="sandbox_exec",
        description="Execute Python code",
        parameters={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        handler=sandbox,
    ))

    response = await agent.run("Analyze data.csv")
    assert "columns" in response.lower()
    # Should have recovered from the NameError
```

**Step 2:** 跑测试 → FAIL

**Step 3:** 在 Agent.run() 中集成 planner 初始化和 error_handler 调用

**Step 4:** 跑测试 → PASS

**Step 5:** Commit: `feat: integrate planner and error handler into agent loop`

---

### Task 2.8: LLM Client 增强 — 重试、超时、流式

**Objective:** 生产可用的 LLM 客户端，不只是基础功能

**Files:** Modify `src/agent/llm/client.py`, Create `tests/test_llm_client.py`

**Step 1:** 为重试逻辑写测试
```python
@pytest.mark.asyncio
async def test_client_retries_on_5xx():
    # 用 httpx mock 或实际测试 endpoint
    pass

def test_client_config_from_env():
    import os
    os.environ["OPENAI_API_KEY"] = "test-key"
    client = OpenAIClient.from_env()
    assert client.api_key == "test-key"
```

**Step 2-5:** 实现、测试、commit

---

## Phase 3: 沙箱层

> **学习目标:** Docker 容器管理、安全隔离、资源限制——系统编程基础
> **前置条件:** Docker Desktop 已安装并运行

### Task 3.1: Docker 连接与健康检查

**Files:** Create `src/agent/sandbox/__init__.py`, `src/agent/sandbox/docker_backend.py`

**Step 1:** 写测试
```python
async def test_docker_client_connects():
    backend = DockerSandboxBackend()
    assert await backend.ping() is True

async def test_pull_image_if_missing():
    backend = DockerSandboxBackend(image="python:3.11-slim")
    assert await backend.ensure_image() is True
```

### Task 3.2: 容器创建与销毁

### Task 3.3: 代码执行与结果捕获

### Task 3.4: 安全限制（cgroup, seccomp, 超时）

### Task 3.5: 文件注入与提取

### Task 3.6: 容器预热池（可选，性能优化）

---

## Phase 4: 工具链与集成

> **学习目标:** Tool 设计模式、Agent 与工具的解耦

### Task 4.1: sandbox_exec Tool

### Task 4.2: file_read / file_list Tools

### Task 4.3: finish Tool（交付产物）

### Task 4.4: 端到端集成测试

### Task 4.5: 错误恢复场景测试

### Task 4.6: 配置驱动的 Tool 加载

---

## Phase 5: 核心机制扩展 — Agent Trace

> **学习目标:** 观测基础设施、执行轨迹记录、状态管理接入主循环
>
> 说明：原完整计划中的 Phase 5/6（CLI 与演示 / 打磨与文档）已整体后移至 Phase 10。

### Task 5.1: Agent Trace

**Objective:** 实现 Agent Trace，记录 Agent 运行的完整事件流，并把 `AgentState` 接入 `Agent.run()` 主循环。`ExecutionContext` 已实现但暂不接入，待未来改造工具签名/注册机制后使用。

**Files:**
- Create: `src/agent/core/trace.py`
- Modify: `src/agent/core/engine.py`
- Create: `tests/test_trace.py`

**必须做:**
1. 定义 `AgentTrace`、`TraceStep`、`TraceEvent` 等数据模型。
2. 在 `Agent` 中持有 `AgentState`，并在主循环中更新 `phase` / `current_step`。
3. 在 LLM 请求、LLM 响应、Tool 执行、错误分类、Planner 状态变化等节点记录 Trace 事件。
4. 提供 `AgentTrace.to_dict()` / `to_json()` 导出能力，以及 `Agent.get_trace()` 方法。
5. 新增 `tests/test_trace.py`，覆盖多轮循环、Tool 结果、错误分类、State 更新等场景。

**严禁做:**
- 不实现上下文压缩、长期记忆、反思式错误恢复、安全策略引擎（后续独立 Phase）。
- 不改变 `Agent.run()` 核心语义。
- 不引入外部持久化层。

---

## Phase 6: 反思式错误恢复

> **学习目标:** 让 Agent 从反复失败中主动学习并调整恢复策略

### Task 6.1: 反思式错误恢复

**Objective:** 在 `ErrorHandler` 基础上增加主动反思层，当同类错误反复出现时触发结构化恢复策略。

**Files:** 待定

**说明:** 本 Phase 依赖 Phase 5 的 Trace 或轻量错误日志，但可独立实现。具体 Task 在 Phase 5 完成后拆分。

---

## Phase 7: 上下文压缩

> **学习目标:** 在 LLM 上下文窗口受限时，对对话历史做摘要 / 裁剪 / 优先级筛选

### Task 7.1: 上下文压缩

**Objective:** 当消息历史接近 token 上限时，保留关键信息并压缩旧消息。

**Files:** 待定

**说明:** 本 Phase 与 Trace 是正交关系，基础版压缩不依赖 Trace。具体 Task 在 Phase 6 完成后拆分。

---

## Phase 8: 长期记忆机制

> **学习目标:** 跨任务 / 跨会话保留关键信息

### Task 8.1: 长期记忆机制

**Objective:** 持久化存储并检索用户偏好、环境状态、已生成产物等关键信息。

**Files:** 待定

**说明:** 本 Phase 涉及持久化层选型与检索策略，作为独立 Phase 实现。具体 Task 在 Phase 7 完成后拆分。

---

## Phase 9: 安全策略引擎

> **学习目标:** 系统化的代码执行与操作安全规则

### Task 9.1: 安全策略引擎

**Objective:** 把代码执行、文件操作、网络访问等安全规则系统化，形成可配置的策略引擎。

**Files:** 待定

**说明:** 本 Phase 在现有 Docker 安全限制基础上增加策略层。具体 Task 在 Phase 8 完成后拆分。

---

## Phase 10: CLI 与演示

> **学习目标:** CLI 设计、Rich 美化、用户体验、项目文档
>
> 说明：本 Phase 由原完整计划中的 Phase 5（CLI 与演示）和 Phase 6（打磨与文档）合并并后移而来。

### Task 10.1: CLI 入口 — argparse

### Task 10.2: Rich 美化输出

### Task 10.3: 交互模式

### Task 10.4: 示例场景脚本

### Task 10.5: Docker 一键启动

### Task 10.6: README 重写

### Task 10.7: 架构图（ASCII）

### Task 10.8: 使用文档

### Task 10.9: Demo 脚本与录制准备

---

## 编码规范

每个 task 必须满足：

1. **Type hints**: 所有函数签名有完整类型标注
2. **Docstrings**: 每个 public 函数/docstring
3. **TDD**: 测试先于实现，见 RED 才写代码
4. **Commit**: 一个 task 一个 commit，格式 `type: description`
5. **No lint errors**: `ruff check src/ tests/` 零报错
6. **Type check pass**: `mypy src/` 零新增错误

## 当前进度

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: 修地基 | 1.1 - 1.5 | ✅ 完成 |
| Phase 2: 核心引擎 | 2.1 - 2.8 | ✅ 完成 |
| Phase 3: 沙箱层 | 3.1 - 3.6 | ✅ 完成 |
| Phase 4: 工具链 | 4.1 - 4.6 | ✅ 完成 |
| Phase 5: 核心机制扩展 — Agent Trace | 5.1 | ⏳ 进行中 |
| Phase 6: 反思式错误恢复 | 6.1 | ⬜ 待开始 |
| Phase 7: 上下文压缩 | 7.1 | ⬜ 待开始 |
| Phase 8: 长期记忆机制 | 8.1 | ⬜ 待开始 |
| Phase 9: 安全策略引擎 | 9.1 | ⬜ 待开始 |
| Phase 10: CLI 与演示 | 10.1 - 10.9 | ⬜ 待开始 |

---

*Generated: 2026-04-28 | Plan version: 1.0*
