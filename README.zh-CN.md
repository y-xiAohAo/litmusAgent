# Litmus Agent

[English](README.md) | [中文](README.zh-CN.md)

> 具备自我纠错能力的代码沙箱 Agent：让 LLM 写代码、在隔离沙箱中执行、观察结果、修正并交付产物。

Litmus Agent 是一个面向代码生成与执行的 LLM Agent 框架。它把"计划 → 写代码 → 运行 → 观察 → 修正"的循环封装成可配置、可观测、可安全的系统，让 LLM 不仅能生成代码，还能真正跑起来、看到结果、自己修 bug。

## 核心特性

- **代码沙箱执行**：通过 `sandbox_exec` tool 在 Docker 容器中安全运行 LLM 生成的 Python 代码，失败时把错误返回给 LLM 自我修正。
- **完整工具集**：默认层含 `sandbox_exec` / `grep` / `glob` / `file_read` / `file_write` / `file_edit` / `file_list` / `finish`，覆盖执行、搜索与文件读写闭环。
- **自我纠错循环**：Agent 主循环持续调用 LLM，直到代码成功运行或达到最大轮数。
- **交互式 CLI**：支持 `agent run` 单次运行与 `agent chat` 多轮对话，内置 Rich 美化输出。
- **配置驱动**：通过 YAML 配置文件管理 LLM 模型、沙箱参数、工具集、安全策略与长期记忆。
- **持久工作区**：三种工作区模式——默认随机卷（用完清理）、`volume_name` 命名卷（`litmus-ws-<name>` 跨会话保留）、`host_dir` bind 挂载宿主项目目录（git 强制快照 + 写确认默认开 + 敏感文件 read deny）。
- **沙箱网络策略**：`network_mode` 配置化（默认 `none` 禁网），`allow_setup_network` 仅对 pip 安装意图的执行放行有网临时容器。
- **MCP 工具接入**：声明式接入任意 MCP server（stdio / SSE / HTTP 三种传输），发现的工具以 `mcp__<server>__<tool>` 注册进统一卡口（策略 / 人工确认 / Trace），CLI/Web 场景默认逐次人工确认、`trust` 可豁免（可选依赖 `pip install "agent[mcp]"`）。
- **长期记忆**：跨任务保留环境状态、用户偏好与失败模式（默认关闭，不破坏原有行为）。
- **安全策略引擎**：可配置地拦截高危代码、文件路径操作与记忆读写。
- **批量评测体系**：125 任务 6 批次（b1-b4 各 20 + b5 22 + b6 23，难度递进）+ 断言/LLM-judge/工具路径三重判分 + 三机制臂对照 + 重复采样 + token 成本可核算（`examples/batch_e2e.py` + `examples/batch_tasks*.py`）；QE 全量回归 44/46（96%，基线 92%）。

## 前置条件

- Python >= 3.10（推荐 3.11）
- Docker Desktop 或 Docker Engine（用于代码沙箱；如果仅看示例，可用 `--echo` 模式跳过真实执行）
- OpenAI API key（可选，示例使用 `--echo` 模式无需 key）

## 安装

```bash
git clone <repo-url>
cd litmusAgent
pip install -e ".[dev]"
```

安装完成后，`agent` 命令即可使用：

```bash
agent --version
```

## 快速开始

### CLI 方式

无需 API key，使用 `EchoClient` 体验 CLI：

```bash
# 单次运行
agent run "帮我写一个快速排序算法" --echo

# 交互模式
agent chat --echo
```

接入真实 LLM（需设置 `OPENAI_API_KEY`）：

```bash
export OPENAI_API_KEY="sk-..."
agent run "帮我写一个快速排序算法"
```

### Python 代码方式

```python
import asyncio

from agent import Agent
from agent.llm import EchoClient


async def main() -> None:
    agent = Agent(llm_client=EchoClient())
    response = await agent.run("帮我写一个快速排序算法")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
```

更多示例见 [`examples/`](examples/)。

## Docker 一键启动

如果你希望在容器内运行 Litmus Agent，可以使用项目提供的 Docker Compose 配置：

```bash
# 检查 Docker 环境并拉取默认沙箱镜像
python scripts/setup-docker.py

# 启动容器（会自动安装项目依赖）
docker compose up -d

# 在容器内运行示例
docker compose exec hermes agent run "帮我写一个快速排序算法" --echo
```

> Windows 用户可能需要根据 Docker Desktop 后端调整 `docker-compose.yml` 中的 Docker socket 挂载路径。

## 项目结构

```
litmusAgent/
├── src/agent/              # 核心源码
│   ├── cli/                # CLI 实现（agent run / agent chat / agent config）
│   ├── config.py           # YAML 配置系统
│   ├── core/               # Agent 引擎、状态、Trace、错误处理、安全策略
│   ├── llm/                # LLM 客户端（OpenAI 兼容 + EchoClient）
│   ├── sandbox/            # Docker 沙箱后端
│   └── tools/              # Tool 实现（sandbox_exec / grep / glob / file_read / file_write / file_edit / file_list / finish）
├── examples/               # 可运行示例（含 batch_e2e.py 批量评测体系）
├── scripts/                # 工具脚本（setup.sh / setup-docker.py / hermes-memory.py）
├── docker-compose.yml      # Docker Compose 运行配置
├── tests/                  # 测试集
├── docs/                   # 文档
├── Makefile                # 常用命令封装
├── pyproject.toml          # 包配置与工具链
└── README.md               # 本文件
```

## 开发

```bash
# 运行测试
make test

# 类型检查
make check

# 代码检查
make lint

# 格式化
make format

# 一键跑 CI 三门禁
make ci
```

质量门禁：

```bash
pytest tests/ -q        # 测试
mypy src/               # 类型检查
ruff check src/ tests/  # Lint
```

## 配置示例

通过 YAML 配置文件自定义 Agent 行为：

```yaml
llm:
  model: gpt-4o
  temperature: 0.2

agent:
  max_turns: 10
  system_prompt: "你是一名耐心的 Python 助教。"

sandbox:
  backend: docker
  timeout: 30

tools:
  enabled:
    - sandbox_exec
    - finish

# 可选：接入 MCP server 的工具（需 pip install "agent[mcp]"）
mcp:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
      trust: false   # false=每次调用前人工确认
```

使用配置运行：

```bash
agent run "帮我写一个排序算法" --config examples/config.yaml --echo
```

## 许可证

MIT
