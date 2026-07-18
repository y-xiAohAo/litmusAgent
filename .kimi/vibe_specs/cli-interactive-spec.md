# CLI 交互模式规格说明 — Task 10.3「交互模式」

> **适用范围**：`src/agent/cli/` 子包、`Agent` 实例复用、相关测试。  
> **目标**：提供 `agent chat` 命令，让用户可以在不退出 CLI 的情况下与 Agent 进行多轮对话。  
> **版本**：v1.0（Phase 10.3）

---

## 1. 背景与目标

Phase 10.1 提供了单次运行的 `agent run`，Phase 10.2 提供了 Rich 样式。Phase 10.3 要提供**交互模式**，让用户可以持续对话：

```bash
$ agent chat
You: 分析 sales.csv
Agent: [回复]
You: 再画一张按月统计的图
Agent: [回复]
You: /quit
```

本任务聚焦**单进程内的多轮对话**，不涉及跨会话持久化、实时工具流、Stream Manager 等更复杂的未来机制。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 新增子命令 `agent chat`，进入交互式对话循环。
2. 使用 `rich.prompt.Prompt.ask("You")` 获取用户输入（Rich 已是项目依赖）。
3. 复用同一个 `Agent` 实例，让 `Agent.messages` 在多轮间自然累积。
4. 每轮调用 `Agent.run(user_input)`，用 `render_result()` 渲染回复。
5. 显示本轮工具调用摘要：
   - 在 `Agent.run()` 返回后，扫描 `agent.messages` 中本轮新增的 tool_call/tool 消息。
   - 输出简洁摘要（如「本次运行调用了 sandbox_exec、file_read」）。
   - 摘要使用 `render.py` 中的渲染函数，支持 `--plain` 回退。
6. 支持特殊命令：
   - `/help`：显示可用命令
   - `/quit` 或 `/exit`：退出交互模式
   - `/clear`：清屏
7. 优雅处理 `Ctrl+C`：
   - 第一次：中止当前 `Agent.run()`，回到输入提示。
   - 快速第二次：退出整个 `agent chat`。
8. 支持 `--config`、 `--model`、 `--api-key`、 `--echo` 等已有参数进入 chat。
9. 新增 `tests/test_cli_chat.py`，覆盖：
   - `/quit` 立即退出
   - 一轮 `--echo` 对话正常返回
   - `/help` 显示帮助
   - `--plain` 模式下输出无 ANSI
   - 工具调用摘要正确显示
10. 中文注释与 docstring、完整类型标注、`mypy strict` 通过、`ruff` 通过。
11. 更新文档：
    - `docs/progress-spec.md`：Task 10.3 标记为 ✅ 完成
    - `CODEMAP.md`：CLI 层增加 chat 说明
    - `docs/session-context.md`：当前任务更新
    - `docs/learning-journal.md`：新增 Phase 10.3 教学内容
12. Commit：`feat: add interactive chat mode to CLI`

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 等核心逻辑。
2. **不实现** 实时工具调用流显示（未来通过 Stream Manager 实现）。
3. **不实现** 跨会话历史持久化（未来独立设计，不采用 crude DB 方案）。
4. **不引入** `prompt-toolkit` 等新增依赖。
5. **不实现** Web UI / GUI / 全屏 TUI。
6. **不改动** 现有 `run` / `config` 子命令行为。

### 2.3 可选做（Nice to Have，仅当时间充裕）

1. `/config` 特殊命令：显示当前配置。
2. 输入为空时的提示与循环继续。

---

## 3. 模块结构

```
src/agent/cli/
├── __init__.py          # 不变
├── __main__.py          # 不变
├── agent_cli.py         # 修改：新增 chat 子命令与 cmd_chat
├── chat.py              # 新增：交互循环实现
├── render.py            # 修改：新增 render_tool_summary
├── memory_cli.py        # 不变
```

### 3.1 `chat.py` 接口设计

```python
def run_chat_loop(agent: Agent, plain: bool = False) -> int:
    """运行交互式对话循环，直到用户退出。

    Args:
        agent: 已构造好的 Agent 实例。
        plain: 是否禁用 Rich 样式。

    Returns:
        退出码：0 正常退出。
    """


def _read_user_input(plain: bool = False) -> str | None:
    """读取用户输入；返回 None 表示退出请求。"""


def _handle_command(command: str, plain: bool = False) -> bool:
    """处理特殊命令；返回 True 表示应继续循环，False 表示退出。"""


def _extract_tool_summary(agent: Agent, before_count: int) -> list[str]:
    """从 agent.messages 中提取本轮新增的工具调用名称列表。"""
```

### 3.2 `agent_cli.py` 参数变化

新增 `chat` 子命令，支持已有全局/覆盖参数：

```python
chat_parser = subparsers.add_parser("chat", help="进入交互式对话模式")
chat_parser.add_argument("--config", dest="config_path", help="YAML 配置文件路径")
chat_parser.add_argument("--model", help="覆盖 LLM 模型名")
chat_parser.add_argument("--api-key", help="覆盖 API key")
chat_parser.add_argument("--base-url", help="覆盖 API base URL")
chat_parser.add_argument("--temperature", type=float, help="覆盖生成温度")
chat_parser.add_argument("--max-turns", type=int, help="覆盖最大对话轮数")
chat_parser.add_argument("--backend", choices=["docker", "subprocess"], help="覆盖沙箱后端")
chat_parser.add_argument("--echo", action="store_true", help="使用 EchoClient")
```

---

## 4. 数据流

```
用户输入：agent chat --echo
    ↓
argparse 解析 args
    ↓
_load_config(args) → AgentConfig
    ↓
_build_llm_client(config, echo=args.echo) → EchoClient
    ↓
_build_agent(config, llm_client) → Agent
    ↓
run_chat_loop(agent, plain=args.plain)
    循环：
      Prompt.ask("You") → user_input
      若 /quit → 退出
      记录 messages 长度 before_count
      asyncio.run(agent.run(user_input)) → result
      _extract_tool_summary(agent, before_count) → tool_names
      render_tool_summary(tool_names, plain=args.plain)
      render_result(result, plain=args.plain)
```

---

## 5. 关键设计决策

1. **复用同一 Agent 实例**：`Agent.messages` 自然累积，无需额外状态管理。
2. **工具摘要事后扫描**：通过比较 `Agent.run()` 前后的 `agent.messages` 长度，提取新增 tool_call，避免修改核心逻辑。
3. **Rich Prompt 读取输入**：与现有 Rich 渲染风格一致，无需新增依赖。
4. **Ctrl+C 双层语义**：第一次中止当前 turn，第二次退出会话，符合常见 CLI 习惯。
5. **交互模式不持久化**：跨会话历史是未来独立机制，不在 10.3 实现。
6. **特殊命令以 `/` 开头**：与常见 chat CLI（如 ChatGPT CLI）保持一致。

---

## 6. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 单元测试 | `pytest tests/test_cli_chat.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 461 passed, 1 skipped 以上 |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| chat 入口 | `agent chat --echo` 可进入并对话 |
| 多轮对话 | 同一 chat 内第二轮能引用前文 |
| 特殊命令 | `/quit` `/help` `/clear` 工作正常 |
| 工具摘要 | 触发 tool call 后显示工具名称摘要 |
| plain 模式 | `agent --plain chat --echo` 无 ANSI 输出 |
| 核心 untouched | `Agent.run()` 等核心文件无修改 |

---

## 7. 测试策略

采用 TDD：

1. 先写 `tests/test_cli_chat.py`，预期失败（chat 子命令不存在）。
2. 实现 `chat.py` 与 `agent_cli.py` 中的 chat 子命令。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁。

测试要点：

- 使用 `monkeypatch` 模拟 `rich.prompt.Prompt.ask` 的输入序列。
- 使用 `--echo` 模式避免真实 API 调用。
- 工具摘要测试通过构造会触发 tool call 的 Agent 场景（可使用 Mock LLM）。

---

## 8. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| `Prompt.ask` 与 capsys 不兼容 | 中 | 中 | 测试中用 monkeypatch 替换 `Prompt.ask` |
| Ctrl+C 信号处理在 Windows 异常 | 中 | 低 | 使用 try/except KeyboardInterrupt，不注册自定义信号处理器 |
| 工具摘要误判 | 低 | 低 | 通过 before/after message 计数精确提取本轮 tool call |
| 长对话导致 messages 过长 | 低 | 中 | 由 `Agent.max_turns` 与 Phase 7 压缩机制控制 |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD~1 -- src/agent/cli/` 回退 CLI 改动。

---

## 9. 未来方向（不在本 Task）

1. **实时工具调用显示**：未来通过 Stream Manager 机制，在 `Agent.run()` 执行工具时实时流式输出。
2. **跨会话历史**：未来独立设计会话持久化机制，**不采用 crude DB 存上下文**的方式；可能结合 Phase 8 记忆机制与会话摘要，实现轻量、可解释的会话恢复。

---

## 10. 文档更新清单

Task 10.3 完成后需同步：

- [ ] `docs/progress-spec.md`：Task 10.3 状态改为 ✅ 完成
- [ ] `CODEMAP.md`：CLI 层增加 `chat.py` 说明
- [ ] `docs/session-context.md`：当前任务更新
- [ ] `docs/learning-journal.md`：新增 Phase 10.3 教学内容

---

## 11. 相关文件

- `src/agent/cli/chat.py`（新建）
- `src/agent/cli/agent_cli.py`（修改：新增 chat 子命令）
- `src/agent/cli/render.py`（修改：新增 render_tool_summary）
- `tests/test_cli_chat.py`（新建）
- `src/agent/core/engine.py`（只读，复用 Agent 实例）
