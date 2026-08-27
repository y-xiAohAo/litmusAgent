# 使用指南

本文档面向最终用户，介绍如何通过命令行（CLI）和 Python API 使用 Litmus Agent。

- 想 5 分钟快速上手？先看 [README.md](../README.md)。
- 想了解每个配置字段的含义？请阅读 [configuration.md](configuration.md)。
- 想了解内部架构？请阅读 [architecture.md](architecture.md)。

---

## CLI 使用

安装完成后，即可通过 `agent` 命令调用 Litmus Agent：

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

## 接入 MCP 工具（TD-016）

Agent 可接入 MCP server 提供的工具（`pip install agent[mcp]`）。在配置文件中
声明 server 后，首次 `run()` 前自动连接并发现工具，以 `mcp__<server>__<tool>`
全名注册，照常走策略 / 人工确认 / Trace 卡口：

```yaml
mcp:
  tool_timeout: 30
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

```bash
agent run "用 filesystem 工具列出 /tmp 内容" --config config.yaml
```

要点：非 `trust: true` 的 server 工具默认全部需要人工确认；单 server 连接
失败跳过不阻塞；`agent.close()` 回收子进程。**注意 MCP server 是宿主进程，
配置即信任**——详见 [configuration.md](configuration.md) 的 mcp 章节。

---

## 维护本地项目（bind 工作区模式，TD-015）

默认模式下 Agent 的沙箱工作区是 Docker 卷，宿主机上看不到产物。若想让 Agent
**直接维护宿主机上的真实项目目录**（读写你的代码仓库），配置 `sandbox.host_dir`：

```yaml
# config.yaml
sandbox:
  backend: docker        # 推荐；显式 subprocess 为自担风险的弱隔离 opt-in
  host_dir: D:/myproject # 宿主机真实项目目录，容器内挂载为 /workspace
```

```bash
agent run "修复 src/ 下的类型错误并补测试" --config config.yaml
```

> **⚠️ 高风险模式**：Agent 的写操作直接落在宿主机目录，误写误删没有沙箱兜底。
> 完整风险说明见 [configuration.md](configuration.md) 的 bind 警示框。

四道保险默认生效：

1. **git 强制快照**：`host_dir` 必须是 git 仓库（否则拒绝启动）。启动时若工作区
   有未提交改动，自动在当前分支提交快照（`litmus: pre-agent snapshot`，署名
   `litmus-agent`，不改你的 git 配置），并在启动横幅中打印快照 sha。
2. **写确认默认开启**：`file_write`/`file_edit` 执行前询问 `y/n/a`
   （`a` 后本会话免确认）；管道等非交互场景默认拒写。
3. **敏感文件 read deny**：`.env*`、`.ssh/`、`*.pem`/`*.key`、`id_rsa*`、`.git/`
   默认禁止读取。
4. **启动横幅**：打印挂载路径、快照 sha、写确认状态与回滚命令。

回滚与审计：

```bash
git -C D:/myproject status                  # 查看 Agent 改了什么
git -C D:/myproject diff                    # 看具体差异
git -C D:/myproject reset --hard <快照sha>  # 回到启动前快照
```

注意：Docker 不可用时 bind 模式直接报错，不会降级到 subprocess；也不要让两个
Agent 同时挂载同一个目录。

> **边界口径**：敏感文件 read deny 约束的是**工具层**访问（`file_read`/`grep`/
> `glob` 等工具调用，含脚本内的兜底过滤）。容器内 `sandbox_exec` 执行的代码
> **不受该策略约束**（策略引擎只能看到工具参数，无法审计任意代码）——bind
> 模式的真实安全边界是**挂载点 + git 快照 + 写确认**三件套，read deny 只是
> 降低 LLM 顺手读取密钥概率的辅助手段，不能替代仓库本身的密钥卫生
> （不要把真实生产密钥留在工作区）。

---

## 沙箱网络策略（TD-010）

默认所有沙箱容器以 `network_mode: none` 禁网运行，加固面不变。需要网络时有两种
受控开口（仅 `docker` 后端）：

```yaml
sandbox:
  network_mode: bridge        # ① 整体放开：容器池全部按 bridge 创建
  allow_setup_network: true   # ② 仅安装阶段放行：pip install 意图的执行
                              #    改用有网临时容器（用完即销毁不入池）
```

- 两个字段默认 `none` + `false`，与旧版行为完全一致。
- `allow_setup_network` 是便利开关而非安全边界：`pip install` 意图由静态
  启发式（字符串/正则级匹配）识别，可能被 prompt injection 诱导，也可能被
  代码里的字面量误触发——例如 `x = "pip install curl"` 这样的字符串同样会
  放网；有网容器仍维持 non-root、read_only 根文件系统与同一 workspace 挂载。
- `bridge`/有网临时容器可经 docker0 网关访问宿主机内网（含云厂商 metadata
  服务 169.254.169.254），在公网或内网敏感环境慎用。
- bind（`host_dir`）模式下开启 `allow_setup_network` 会打 warning
  （有网 + 直写宿主目录 = 攻击面叠加），慎用。
- `subprocess` 后端不做网络隔离，`allow_network` 参数被接受并忽略。

---

## 批量评测（Batch E2E）

项目内置批量评测体系，用于在真实 LLM 上量化 Agent 机制效果（规划/反思对照实验）：

```bash
# 冒烟测试：合成结果，零成本验证结构
python examples/batch_e2e.py --echo

# 全批真实运行（默认 b3 任务集：20 开放任务 × 3 机制臂，串行）
python examples/batch_e2e.py

# 子集试点：指定任务与机制臂
python examples/batch_e2e.py --only T41,T47 --arms full

# 切换任务集（b1 基线 / b2 高难显式分步 / b3 开放）
python examples/batch_e2e.py --set b2
```

- **任务集**：`examples/batch_tasks*.py`，覆盖算法/文件处理/数据分析/多步工程/file_edit 专项/开放报告，难度 L1-L4 递进；
- **机制臂**：`full`（规划+反思全开）/ `no-planner` / `no-reflect`，两两对照；
- **判分**：沙箱断言 + LLM-judge 混合；部分任务带工具路径断言（产物正确但未用指定工具也判 FAIL）；
- **产出**：聚合报告（成功率/轮数/token/失败分类）写入 `mydocs/reports/`，token 成本逐 run 统计；历史报告见 `docs/batch-e2e-batch*-report.md`。

真实运行需要 `OPENAI_API_KEY` 与可用的 Docker daemon。

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
