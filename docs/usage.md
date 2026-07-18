# 使用指南

本文档面向最终用户，介绍如何通过命令行（CLI）和 Python API 使用 Hermes Agent。

- 想 5 分钟快速上手？先看 [README.md](../README.md)。
- 想了解每个配置字段的含义？请阅读 [configuration.md](configuration.md)。
- 想了解内部架构？请阅读 [architecture.md](architecture.md)。

---

## CLI 使用

安装完成后，即可通过 `agent` 命令调用 Hermes Agent：

```bash
# 查看版本
agent --version

# 查看帮助
agent --help
```

> 提示：当前环境没有 API Key 时，请在所有命令后追加 `--echo`，使用 EchoClient 进行测试与演示。

### agent run

一次性运行 Agent，处理给定的提示文本。

```bash
# 最简示例：使用 EchoClient，无需 API Key
agent run "计算 1 + 1" --echo

# 加载 YAML 配置文件
agent run "分析 data.csv" --config examples/config.yaml

# 通过命令行覆盖部分配置
agent run "写一个快速排序" \
  --api-key "$OPENAI_API_KEY" \
  --model gpt-4o \
  --temperature 0.2 \
  --max-turns 30

# 指定沙箱后端（当前推荐 docker）
agent run "执行一段 Python 代码" --backend docker
```

`agent run` 常用参数：

| 参数 | 说明 |
|------|------|
| `prompt` | 必填。发送给 Agent 的提示文本。 |
| `--config` | YAML 配置文件路径。 |
| `--model` | 覆盖 LLM 模型名。 |
| `--api-key` | 覆盖 API Key。 |
| `--base-url` | 覆盖 API Base URL，例如兼容 OpenAI 的本地代理。 |
| `--temperature` | 覆盖生成温度（0–1）。 |
| `--max-turns` | 覆盖最大对话轮数。 |
| `--backend` | 覆盖沙箱后端：`docker` 或 `subprocess`。 |
| `--echo` | 使用 EchoClient 替代真实 LLM，用于测试。 |
| `--approve` | 启用写操作人工确认：`file_write`/`file_edit` 执行前询问 `y/n/a`（y=允许 / n=拒绝 / a=本会话免确认）。 |
| `--plan` | 启用自动规划：执行前先由 LLM 分解任务步骤（多步任务更可靠，每 run 多一次 LLM 调用）。 |
| `--plain` | 禁用 Rich 样式，输出纯文本，适合脚本管道。 |

### agent chat

进入交互式对话模式，可连续多轮输入。

```bash
# 交互模式，使用 EchoClient 测试
agent chat --echo

# 加载配置文件后进入交互模式
agent chat --config examples/config.yaml
```

交互模式下支持的命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/quit` 或 `/exit` | 退出交互模式 |
| `/clear` | 清屏 |

### agent config

显示当前生效的配置摘要，用于检查配置文件是否被正确加载。

```bash
# 显示默认配置
agent config

# 显示指定配置文件合并后的配置
agent config --config examples/config.yaml
```

---

## Python API 使用

CLI 只是 Agent 的一个入口。你也可以在自己的 Python 脚本或应用中直接调用 `Agent` 类。

### 最简示例：使用 EchoClient

EchoClient 会把最后一条用户消息原样返回，适合在没有 API Key 的环境中跑通流程。

```python
import asyncio

from agent import Agent
from agent.llm import EchoClient


async def main() -> None:
    agent = Agent(llm_client=EchoClient())
    result = await agent.run("你好")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

### 连接真实 LLM：OpenAIClient

`OpenAIClient` 兼容任何 OpenAI 风格的 API 端点，例如 OpenAI、DeepSeek 或本地模型。

```python
import asyncio
import os

from agent import Agent
from agent.llm import OpenAIClient


async def main() -> None:
    # 未传 api_key 时，from_env() 会自动读取 OPENAI_API_KEY 环境变量
    client = OpenAIClient.from_env(model="gpt-4o")
    agent = Agent(llm_client=client)
    result = await agent.run("写一个计算斐波那契数列的 Python 函数")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

`from_env()` 会读取以下环境变量：

| 环境变量 | 映射字段 |
|----------|----------|
| `OPENAI_API_KEY` | `api_key` |
| `OPENAI_BASE_URL` | `base_url` |
| `OPENAI_MODEL` | `model` |

### 加载 YAML 配置

```python
import asyncio

from agent import Agent
from agent.config import load_config
from agent.llm import OpenAIClient


async def main() -> None:
    config = load_config("examples/config.yaml")
    client = OpenAIClient.from_env(
        api_key=config.llm.api_key or None,
        model=config.llm.model,
        base_url=config.llm.base_url or None,
    )
    agent = Agent(llm_client=client, config=config)
    result = await agent.run("你好")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

### 注册自定义工具

通过 `ToolSpec` 可以把任意 Python 函数注册成 Agent 可调用的工具。

```python
import asyncio

from agent import Agent
from agent.core.types import ToolSpec
from agent.llm import EchoClient


def add(a: int, b: int) -> int:
    """两数相加。"""
    return a + b


async def main() -> None:
    # 本示例仅演示注册语法。EchoClient 不会真正触发 tool call，
    # 接入真实 LLM 后才能看到 add 工具被调用并返回 5。
    agent = Agent(llm_client=EchoClient())
    agent.tools.register(
        ToolSpec(
            name="add",
            description="计算两个整数之和",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "被加数"},
                    "b": {"type": "integer", "description": "加数"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
            handler=add,
        )
    )
    result = await agent.run("请使用 add 工具计算 2 + 3")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

### 获取执行轨迹

每次 `agent.run()` 都会自动记录 `AgentTrace`，可用于调试或审计。

```python
import asyncio

from agent import Agent
from agent.llm import EchoClient


async def main() -> None:
    agent = Agent(llm_client=EchoClient())
    await agent.run("你好")
    trace = agent.get_trace()
    print(trace)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 常见问题

### 1. 没有 API Key 怎么测试？

所有 CLI 命令和 Python 示例都可以使用 EchoClient 跑通：

```bash
agent run "任意提示" --echo
agent chat --echo
```

### 2. Docker 沙箱启动失败怎么办？

请确保 Docker Engine 已运行，并已准备所需镜像：

```bash
python scripts/setup-docker.py
```

如果无法连接 Docker Hub，请配置镜像源或使用本地已导入的镜像。

### 3. Docker 不可用时如何运行？

将配置中的 `sandbox.backend` 设为 `subprocess`（TD-002/TD-003 已生效）：

```yaml
sandbox:
  backend: subprocess
```

Agent 会改用本地子进程后端：每个实例使用独立临时目录作为 workspace，`/workspace/...`、`/tmp/...` 等沙箱内路径会映射到该目录下，写 → 读 → 改 → 运行闭环可用。注意它不提供 Docker 级安全隔离，仅适合可信代码与演示场景。

### 4. 配置文件加载失败如何排查？

使用 `agent config` 查看合并后的配置：

```bash
agent config --config your-config.yaml
```

常见错误包括：字段类型不对、YAML 缩进错误、文件路径不存在。
