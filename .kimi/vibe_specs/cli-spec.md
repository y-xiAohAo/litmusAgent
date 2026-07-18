# CLI 模块规格说明 — Task 10.1「CLI 入口 — argparse」

> **适用范围**：`src/agent/cli/` 子包、console script、相关测试。  
> **目标**：为 Hermes Agent 提供稳定的命令行入口，使用户无需写 Python 脚本即可运行 Agent。  
> **版本**：v1.0（Phase 10.1）

---

## 1. 背景与目标

目前运行 Agent 必须编写 Python 脚本（如 `examples/simple_agent.py`）。Phase 10.1 要提供一个开箱即用的命令行入口，覆盖最常见的使用场景：

- 单次运行：`agent run "分析 sales.csv"`
- 指定配置：`agent run --config hermes.yaml "..."`
- 快速验证：`agent run --echo "hello"`（无需 API key）
- 查看配置：`agent config --config hermes.yaml`
- 查看版本：`agent --version`

本任务**只**实现 argparse 骨架与核心子命令，不涉及 Rich、交互模式、Docker 一键启动。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 新建 `src/agent/cli/agent_cli.py`，实现 Agent 主 CLI。
2. 新建 `src/agent/cli/__main__.py`，支持 `python -m agent.cli`。
3. 修改 `src/agent/cli/__init__.py`，导出 `main`（来自 `agent_cli.py`），并保留 `memory_main`（来自 `memory_cli.py`）以兼容潜在调用方。
4. 修改 `pyproject.toml`，注册 console script：
   ```toml
   [project.scripts]
   agent = "agent.cli:main"
   ```
5. 子命令与参数：
   - `agent --version`：输出 `agent x.y.z`
   - `agent run PROMPT`：运行 Agent
     - `--config PATH`：YAML 配置文件路径
     - `--model MODEL`：覆盖 LLM 模型名
     - `--api-key KEY`：覆盖 API key
     - `--base-url URL`：覆盖 API base URL
     - `--temperature FLOAT`：覆盖温度
     - `--max-turns INT`：覆盖最大轮数
     - `--backend {docker,subprocess}`：覆盖沙箱后端
     - `--echo`：使用 `EchoClient` 而非真实 LLM，用于测试与演示
   - `agent config`：显示当前生效配置摘要
     - `--config PATH`：YAML 配置文件路径
6. 参数覆盖优先级：**CLI 参数 > YAML 配置 > 代码默认值**。
7. 未提供 API key 且未使用 `--echo` 时，优雅退出并返回非 0 退出码， stderr 提示用户设置 `OPENAI_API_KEY` 或使用 `--echo`。
8. `agent run` 使用 `asyncio.run()` 调用 `Agent.run()`。
9. 在 Windows 终端强制使用 UTF-8 输出（参考 `memory_cli.py` 已做处理）。
10. 中文注释与 docstring、完整类型标注、`mypy strict` 通过、`ruff` 通过。
11. 新增 `tests/test_cli.py`，覆盖：
    - `agent --version` 输出正确版本
    - `agent run --echo "hello"` 返回包含输入的响应
    - `agent run "hello"` 在缺少 API key 时退出码非 0 并提示
    - `agent config` 显示配置摘要（默认配置）
    - `agent config --config <path>` 正确加载并显示 YAML 中的模型名
    - CLI 参数覆盖 YAML 配置（如 `--max-turns` 覆盖 YAML）

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 等核心逻辑。
2. **不实现** Rich 美化输出（Task 10.2）。
3. **不实现** 交互模式 / REPL（Task 10.3）。
4. **不实现** Docker 一键启动（Task 10.5）。
5. **不合并** 记忆 CLI 到主 CLI（Task 10.1 保持独立；后续 Task 再评估）。
6. **不改变** `scripts/hermes-memory.py` 的行为。
7. **不使用**文件备份替代 git 回滚。
8. **不默认启用**任何安全策略或记忆系统。

### 2.3 可选做（Nice to Have，仅当时间充裕）

1. `agent run --dry-run`：仅打印将要执行的配置与 plan，不调用 LLM（留给后续 Task）。
2. 更详细的日志级别参数 `--verbose` / `--quiet`。

---

## 3. 模块结构

```
src/agent/cli/
├── __init__.py          # 导出 main（agent CLI）与 memory_main（记忆 CLI）
├── __main__.py          # python -m agent.cli 入口
├── agent_cli.py         # Task 10.1 新增：Agent 主 CLI
└── memory_cli.py        # Phase 8.4 已有：记忆管理 CLI（不变）
```

### 3.1 `agent_cli.py` 内部函数设计

```python
def build_parser() -> argparse.ArgumentParser:
    """构造 Agent 主 CLI 参数解析器。"""

def _load_config(args: argparse.Namespace) -> AgentConfig:
    """根据 CLI 参数与 YAML 配置文件构造最终 AgentConfig。"""

def _build_llm_client(config: AgentConfig, echo: bool) -> BaseLLMClient:
    """根据配置构造 LLMClient；echo=True 时使用 EchoClient。"""

def _build_agent(config: AgentConfig, llm_client: BaseLLMClient) -> Agent:
    """根据配置与 LLMClient 构造 Agent，注册默认工具。"""

def cmd_run(args: argparse.Namespace) -> int:
    """执行 run 子命令。"""

def cmd_config(args: argparse.Namespace) -> int:
    """执行 config 子命令。"""

def main(argv: list[str] | None = None) -> int:
    """CLI 入口，返回退出码。"""
```

### 3.2 参数覆盖规则

`_load_config(args)` 的逻辑：

1. 以 `AgentConfig()` 为默认值。
2. 若 `args.config` 存在，调用 `load_config(args.config)` 覆盖默认值。
3. 若 CLI 参数非 None，逐项覆盖对应字段：
   - `model` → `config.llm.model`
   - `api_key` → `config.llm.api_key`
   - `base_url` → `config.llm.base_url`
   - `temperature` → `config.llm.temperature`
   - `max_turns` → `config.agent.max_turns`
   - `backend` → `config.sandbox.backend`

---

## 4. 数据流

```
用户输入：agent run --config hermes.yaml --max-turns 10 "分析 sales.csv"
    ↓
argparse 解析 args
    ↓
_load_config(args):
  1. AgentConfig() 默认值
  2. load_config("hermes.yaml") 覆盖
  3. args.max_turns=10 覆盖
    ↓
_build_llm_client(config, echo=False) → OpenAIClient.from_env() 或显式 api_key
    ↓（若 api_key 为空且非 echo）
stderr 提示并返回退出码 1
    ↓
_build_agent(config, llm_client):
  创建 Agent，调用 register_default_tools(registry, config)
    ↓
asyncio.run(agent.run("分析 sales.csv"))
    ↓
stdout 输出最终结果
```

---

## 5. 关键设计决策

1. **独立文件 `agent_cli.py`**：避免与 `memory_cli.py` 耦合，也避免破坏现有 `agent.cli` 包的导入语义。
2. **`agent` 作为 console script**：与包名一致，降低用户记忆成本。
3. **`--echo` 而非 `--dry-run`**：`--echo` 明确使用测试桩 LLM；`--dry-run` 语义更复杂，留给后续。
4. **`subprocess` 后端默认可用于 `--echo` 测试**：`EchoClient` 不调用任何 tool，因此无需 Docker 也能跑通 `agent run --echo`。
5. **配置摘要显示敏感信息过滤**：`agent config` 输出中 `api_key` 显示为 `***` 或长度提示，避免泄露。

---

## 6. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 单元测试 | `pytest tests/test_cli.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 仍保持 446 passed, 1 skipped |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| 版本命令 | `python -m agent.cli --version` 输出 `agent 0.1.0` |
| Echo 运行 | `python -m agent.cli run --echo "hello"` 输出包含 `You said: hello` |
| 缺少 API key | `python -m agent.cli run "hello"` 返回非 0 并提示设置环境变量 |
| 安装后命令 | `pip install -e .` 后，`agent --version` 可用 |
| 配置加载 | `agent config --config <yaml>` 正确显示 YAML 中模型名 |
| 参数覆盖 | `agent run --config <yaml> --max-turns 5` 实际使用 5 轮 |

---

## 7. 测试策略

采用 TDD：

1. 先写 `tests/test_cli.py`，预期全部失败。
2. 实现 `agent_cli.py`、更新 `__init__.py` 与 `__main__.py`、注册 console script。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁：`pytest tests/`、`mypy src/`、`ruff check src/ tests/`。

测试要点：

- 使用 `capsys` 捕获 stdout/stderr。
- 对于需要命令行参数解析的测试，直接调用 `main(["--version"])` 等方式，不依赖子进程。
- 对于需要环境变量的测试，使用 `monkeypatch` 设置/清除 `OPENAI_API_KEY`。
- 配置文件测试使用 `tmp_path` 创建临时 YAML。

---

## 8. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| `src/agent/cli/__init__.py` 导出错误导致 `agent` 命令无法启动 | 低 | 高 | 新增 `test_cli.py` 覆盖 `python -m agent.cli --version`；console script 安装后手动验证 |
| 修改 `pyproject.toml` 破坏包安装 | 低 | 高 | 仅在 `[project.scripts]` 新增一行；安装后验证 `agent --version` |
| CLI 参数未正确覆盖 YAML 默认值 | 中 | 中 | 专门测试 `--max-turns` / `--model` 覆盖场景 |
| 缺少 API key 时未优雅退出 | 低 | 中 | 测试缺失 API key 时的退出码与提示 |
| Windows 中文输出乱码 | 中 | 低 | 参考 `memory_cli.py` 在 `main()` 顶部做 `sys.stdout.reconfigure(encoding="utf-8")` |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout -- src/agent/cli/ pyproject.toml tests/test_cli.py` 回退到干净状态。

---

## 9. 文档更新清单

Task 10.1 完成后需同步：

- [ ] `docs/progress-spec.md`：更新 Phase 10.1 状态为 ✅ 完成，产出文件改为实际路径。
- [ ] `CODEMAP.md`：CLI 层增加 `agent_cli.py` 说明，Phase 10 状态改为进行中/完成。
- [ ] `docs/session-context.md`：更新当前任务为 Phase 10.1，Git 状态为干净。
- [ ] `docs/learning-journal.md`：按模板补充 CLI 设计教学内容。

---

## 10. 相关文件

- `src/agent/cli/agent_cli.py`（新建）
- `src/agent/cli/__main__.py`（新建）
- `src/agent/cli/__init__.py`（修改）
- `src/agent/cli/memory_cli.py`（不修改，仅作为参考）
- `pyproject.toml`（修改：新增 console script）
- `tests/test_cli.py`（新建）
- `src/agent/config.py`（只读，不修改）
- `src/agent/core/engine.py`（只读，不修改）
- `src/agent/llm/client.py`（只读，不修改）
- `src/agent/tools/__init__.py`（只读，用于注册默认工具）
