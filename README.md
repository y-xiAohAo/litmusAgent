# Litmus Agent

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/y-xiAohAo/litmusAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/y-xiAohAo/litmusAgent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> A self-correcting code-sandbox agent: let an LLM write code, run it in an isolated sandbox, observe the result, fix it, and deliver.

Litmus Agent is an LLM agent framework for code generation and execution. It wraps the "plan → write code → run → observe → fix" loop into a configurable, observable, and safe system — so the LLM doesn't just generate code, it actually runs it, sees the output, and fixes its own bugs.

## Features

- **Sandboxed code execution**: run LLM-generated Python safely in Docker containers via the `sandbox_exec` tool; failures are fed back to the LLM for self-correction.
- **Full tool set**: the default layer ships `sandbox_exec` / `grep` / `glob` / `file_read` / `file_write` / `file_edit` / `file_list` / `finish` — a closed loop of execution, search, and file I/O.
- **Self-correction loop**: the agent main loop keeps calling the LLM until the code runs successfully or the turn budget is exhausted.
- **Interactive CLI**: `agent run` for one-shot tasks and `agent chat` for multi-turn sessions, with Rich-powered output.
- **Configuration-driven**: manage LLM model, sandbox parameters, tool sets, security policies, and long-term memory through a YAML config file.
- **Persistent workspaces**: three workspace modes — ephemeral random volumes (cleaned up after use), named volumes (`litmus-ws-<name>`, preserved across sessions), and `host_dir` bind mounts of a host project directory (mandatory git snapshot + write confirmation on by default + read-deny for sensitive files), with in-session `/diff` review and `/undo` rollback for bind-mode chats.
- **Sandbox network policy**: configurable `network_mode` (`none` by default); `allow_setup_network` grants a temporary networked container only for pip-install execution intents.
- **MCP tool integration**: declaratively attach any MCP server (stdio / SSE / HTTP transports); discovered tools are registered as `mcp__<server>__<tool>` behind the unified gatekeeper (policy / human approval / trace). CLI/Web scenarios require per-call human approval by default, with `trust` as an opt-out (optional dependency: `pip install "agent[mcp]"`).
- **Streaming & observable rendering**: `--stream` enables token-level streaming of the final answer, dimmed rendering of the model's reasoning (`reasoning_content`, e.g. DeepSeek V4 thinking mode), and live tool-call progress lines — with no change to the agent loop semantics (default off).
- **Long-term memory**: retain environment state, user preferences, and failure patterns across tasks (off by default; no behavior change when disabled).
- **Security policy engine**: configurable interception of high-risk code, file-path operations, and memory reads/writes.
- **Batch evaluation suite**: 125 tasks across 6 batches (b1–b4: 20 each, b5: 22, b6: 23, progressive difficulty) with triple scoring (assertions / LLM-judge / tool-path), mechanism ablation arms, repeated sampling, and token-cost accounting (`examples/batch_e2e.py` + `examples/batch_tasks*.py`); query-expansion regression 44/46 (96%, baseline 92%).

## Prerequisites

- Python >= 3.10 (3.11 recommended)
- Docker Desktop or Docker Engine (for the code sandbox; use `--echo` mode to explore examples without real execution)
- OpenAI API key (optional; `--echo` examples need no key)

## Installation

```bash
git clone https://github.com/y-xiAohAo/litmusAgent.git
cd litmusAgent
pip install -e ".[dev]"
```

The `agent` command is then available:

```bash
agent --version
```

## Quick Start

### CLI

Try the CLI with the `EchoClient` — no API key required:

```bash
# One-shot run
agent run "write a quicksort algorithm for me" --echo

# Interactive mode
agent chat --echo
```

Connect a real LLM (requires `OPENAI_API_KEY`):

```bash
export OPENAI_API_KEY="sk-..."
agent run "write a quicksort algorithm for me"
```

### Python API

```python
import asyncio

from agent import Agent
from agent.llm import EchoClient


async def main() -> None:
    agent = Agent(llm_client=EchoClient())
    response = await agent.run("write a quicksort algorithm for me")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
```

More examples in [`examples/`](examples/).

## Docker Quickstart

To run Litmus Agent inside a container, use the provided Docker Compose setup:

```bash
# Check the Docker environment and pull the default sandbox image
python scripts/setup-docker.py

# Start the container (project dependencies are installed automatically)
docker compose up -d

# Run an example inside the container
docker compose exec hermes agent run "write a quicksort algorithm for me" --echo
```

> On Windows, you may need to adjust the Docker socket mount path in `docker-compose.yml` depending on your Docker Desktop backend.

## Project Structure

```
litmusAgent/
├── src/agent/              # Core source code
│   ├── cli/                # CLI implementation (agent run / agent chat / agent config)
│   ├── config.py           # YAML configuration system
│   ├── core/               # Agent engine, state, trace, error handling, security policy
│   ├── llm/                # LLM clients (OpenAI-compatible + EchoClient)
│   ├── sandbox/            # Docker sandbox backend
│   └── tools/              # Tool implementations (sandbox_exec / grep / glob / file_read / file_write / file_edit / file_list / finish)
├── examples/               # Runnable examples (incl. batch_e2e.py evaluation suite)
├── scripts/                # Utility scripts (setup.sh / setup-docker.py / hermes-memory.py)
├── docker-compose.yml      # Docker Compose configuration
├── tests/                  # Test suite
├── docs/                   # Documentation
├── Makefile                # Common command shortcuts
├── pyproject.toml          # Package config and toolchain
└── README.md               # This file
```

## Development

```bash
# Run tests
make test

# Type check
make check

# Lint
make lint

# Format
make format

# Run all three CI gates
make ci
```

Quality gates:

```bash
pytest tests/ -q        # Tests
mypy src/               # Type checking
ruff check src/ tests/  # Lint
```

## Configuration

Customize agent behavior with a YAML config file:

```yaml
llm:
  model: gpt-4o
  temperature: 0.2

agent:
  max_turns: 10
  system_prompt: "You are a patient Python teaching assistant."

sandbox:
  backend: docker
  timeout: 30

tools:
  enabled:
    - sandbox_exec
    - finish

# Optional: attach tools from MCP servers (requires pip install "agent[mcp]")
mcp:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
      trust: false   # false = human approval before every call
```

Run with a config file:

```bash
agent run "write a sorting algorithm" --config examples/config.yaml --echo
```

## License

MIT
