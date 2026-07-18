# CLI Rich 美化规格说明 — Task 10.2「Rich 美化输出」

> **适用范围**：`src/agent/cli/` 子包、Rich 渲染模块、相关测试。  
> **目标**：为 Agent CLI 输出增加 Rich 样式，提升可读性与用户体验，同时保留 `--plain` 纯文本模式。  
> **版本**：v1.0（Phase 10.2）

---

## 1. 背景与目标

Phase 10.1 已实现功能完整的 argparse CLI，但输出仍是纯文本：

```text
当前配置摘要：
  provider: openai
  model: gpt-4o
  max_turns: 20
```

Phase 10.2 引入 Rich，把配置摘要、Agent 结果、错误信息包装成更友好的表格/面板，同时：

- 不破坏脚本化使用场景（提供 `--plain` 模式）。
- 不侵入 Agent 核心逻辑。
- 不增加交互复杂度（无 spinner / 无实时日志 / 无 REPL）。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 新建 `src/agent/cli/render.py`，封装所有 Rich 渲染逻辑：
   - `render_config(config, plain=False)`：配置摘要表格
   - `render_result(result, plain=False)`：Agent 结果面板
   - `render_error(message, plain=False)`：错误面板（红色边框）
2. 修改 `src/agent/cli/agent_cli.py`：
   - 新增全局参数 `--plain`，默认关闭 Rich 样式。
   - `config` 子命令调用 `render_config()`。
   - `run` 子命令调用 `render_result()`。
   - 所有错误路径调用 `render_error()`。
3. 更新 `tests/test_cli.py`：
   - 现有断言改用 `--plain` 模式，确保输出稳定可断言。
   - 新增测试验证 Rich 模式下 `config` / `run` / 错误 不崩溃且有输出。
   - 新增测试验证 `--plain` 模式确实不输出 ANSI 转义序列。
4. 中文注释与 docstring、完整类型标注、`mypy strict` 通过、`ruff` 通过。
5. 更新文档：
   - `docs/progress-spec.md`：Task 10.2 标记为 ✅ 完成
   - `CODEMAP.md`：CLI 层增加 `render.py`
   - `docs/session-context.md`：当前任务更新
   - `docs/learning-journal.md`：新增 Phase 10.2 教学内容
6. Commit：`feat: add Rich styling to CLI output`

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
2. **不实现** 交互模式 / REPL（Task 10.3）。
3. **不实现** 进度条 / spinner / Rich Live（超出 Task 10.2 范围，后续可选）。
4. **不替换** argparse 默认 help（超出范围）。
5. **不接入** structlog 的 Rich handler（避免与现有日志系统纠缠）。
6. **不做** 自动代码语言检测与语法高亮（避免误判，留给后续可选增强）。
7. **不改变** CLI 参数语义与退出码。

### 2.3 可选做（Nice to Have，仅当时间充裕）

1. 对 `run` 结果中的 Markdown 代码块做简单渲染（Rich Markdown 原生支持）。
2. `--plain` 模式下也支持 `--no-color` 别名（语义相同）。

---

## 3. 模块结构

```
src/agent/cli/
├── __init__.py          # 不变
├── __main__.py          # 不变
├── agent_cli.py         # 修改：接入 render.py，新增 --plain
├── memory_cli.py        # 不变
└── render.py            # 新增：Rich 渲染封装
```

### 3.1 `render.py` 接口设计

```python
from agent.config import AgentConfig


def render_config(config: AgentConfig, plain: bool = False) -> None:
    """渲染配置摘要。

    Rich 模式：表格形式，api_key 脱敏。
    Plain 模式：与 10.1 的纯文本输出保持一致。
    """


def render_result(result: str, plain: bool = False) -> None:
    """渲染 Agent 最终结果。

    Rich 模式：带标题的面板，内容按 Markdown 渲染。
    Plain 模式：直接打印 result。
    """


def render_error(message: str, plain: bool = False) -> None:
    """渲染错误信息。

    Rich 模式：红色边框面板，标题为"错误"。
    Plain 模式：stderr 输出 "错误：{message}"。
    """
```

### 3.2 `agent_cli.py` 参数变化

在顶层 parser 增加：

```python
parser.add_argument(
    "--plain",
    action="store_true",
    help="禁用 Rich 样式，输出纯文本（适合脚本管道）",
)
```

所有子命令共享此参数。

---

## 4. 输出样式示例

### 4.1 `agent config`（Rich 模式）

```text
┌─────────────────────────────────────────────┐
│ 当前配置摘要                                  │
├────────────────┬────────────────────────────┤
│ provider       │ openai                     │
│ model          │ gpt-4o                     │
│ base_url       │ https://api.openai.com/v1  │
│ temperature    │ 0.7                        │
│ max_tokens     │ 4096                       │
│ max_turns      │ 20                         │
│ backend        │ docker                     │
│ api_key        │ 未设置                      │
└────────────────┴────────────────────────────┘
```

### 4.2 `agent run`（Rich 模式）

```text
┌─────────────────────────────────────────────┐
│ Agent 结果                                   │
│                                             │
│ You said: hello                             │
└─────────────────────────────────────────────┘
```

### 4.3 错误（Rich 模式）

```text
┌─────────────────────────────────────────────┐
│ 错误                                        │
│                                             │
│ 未提供 OPENAI_API_KEY。请设置环境变量...      │
└─────────────────────────────────────────────┘
```

### 4.4 `--plain` 模式

与 Phase 10.1 输出完全一致，确保脚本兼容与测试稳定。

---

## 5. 数据流

```
用户输入：agent config --config hermes.yaml
    ↓
argparse 解析 args，args.plain = False
    ↓
_load_config(args) → AgentConfig
    ↓
render_config(config, plain=args.plain)
    ├─ plain=True  → print 纯文本
    └─ plain=False → Rich Console.print(Table)
```

---

## 6. 关键设计决策

1. **`--plain` 是全局参数**：所有子命令共享，方便统一控制。
2. **渲染逻辑独立到 `render.py`**：避免 `agent_cli.py` 里混入选项解析与样式代码，后续换主题/换库更方便。
3. **Rich 输出到 stdout，错误到 stderr**：与 Phase 10.1 保持一致。
4. **测试以 `--plain` 为主**：Rich 输出包含 ANSI 与边框，断言脆弱；`--plain` 提供稳定的测试锚点。
5. **不自动检测代码语言**：避免把普通文本误判为代码；统一用 Markdown Panel 能正确处理用户自己写的 ``` 代码块。
6. **api_key 脱敏保留**：Rich 表格中仍显示「未设置」或 `****...****`。

---

## 7. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 单元测试 | `pytest tests/test_cli.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 455 passed, 1 skipped |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| Rich config | `agent config` 输出表格 |
| Rich run | `agent run --echo "hello"` 输出面板 |
| Rich error | `agent run "hello"`（缺 API key）输出红色错误面板 |
| Plain 模式 | `agent --plain config` 输出纯文本且无 ANSI 转义序列 |
| 模块入口 | `python -m agent.cli --plain config` 可用 |
| 安装后 | `pip install -e .` 后 `agent config` 仍有 Rich 样式 |

---

## 8. 测试策略

采用 TDD：

1. 先更新 `tests/test_cli.py`，把现有断言改为 `--plain` 模式（预期失败，因为 `--plain` 还未实现）。
2. 实现 `--plain` 与 `render.py`。
3. 新增 Rich 模式 smoke test。
4. 跑完整质量门禁。

测试要点：

- `--plain` 输出验证：使用 `capsys` 捕获，断言不包含 `\x1b[`（ANSI 转义起始字符）。
- Rich 输出验证：仅断言 `Agent 结果` / `当前配置摘要` / `错误` 等标题存在，不强断言边框。
- 错误渲染验证：调用 `render_error` 或 `main(["run", "hello"])` 缺 API key 时，stderr 有内容。

---

## 9. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| Rich 输出导致测试断言失败 | 中 | 中 | 测试统一用 `--plain` 模式；Rich 只做 smoke test |
| Windows 终端不支持 Unicode 边框 | 低 | 低 | Rich 自动降级；已在 agent_cli.py 设置 UTF-8 |
| render.py 与 agent_cli.py 循环依赖 | 低 | 高 | render.py 只依赖 `agent.config.AgentConfig` |
| `--plain` 未正确禁用 Rich | 低 | 中 | 专门测试 ANSI 转义序列不存在 |
| 破坏现有 `agent --version` | 低 | 中 | 保持 `--version` 使用 argparse 原生输出，不经过 Rich |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD~1 -- src/agent/cli/` 回退 CLI 改动。

---

## 10. 文档更新清单

Task 10.2 完成后需同步：

- [ ] `docs/progress-spec.md`：Task 10.2 状态改为 ✅ 完成
- [ ] `CODEMAP.md`：CLI 层增加 `render.py` 说明
- [ ] `docs/session-context.md`：当前任务更新为 Phase 10.3 或总结 10.2
- [ ] `docs/learning-journal.md`：新增 Phase 10.2 教学内容

---

## 11. 相关文件

- `src/agent/cli/render.py`（新建）
- `src/agent/cli/agent_cli.py`（修改：接入 render、新增 --plain）
- `tests/test_cli.py`（修改：--plain 断言、新增 Rich smoke test）
- `src/agent/cli/__init__.py`（不修改）
- `src/agent/cli/__main__.py`（不修改）
- `src/agent/cli/memory_cli.py`（不修改）
- `pyproject.toml`（不修改，Rich 已是依赖）
