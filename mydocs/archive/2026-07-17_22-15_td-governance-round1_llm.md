# 归档（LLM 视角）— 技术债治理第一轮：TD-002 / TD-003 / TD-006

> 生成：2026-07-17 | 模式：thematic | 受众：llm（后续会话续接用）
> Source Index：
> - `mydocs/specs/2026-07-17_20-55_td-002-003-subprocess-backend.md`（Research/Plan/Execute/Validation/Review）
> - `mydocs/specs/2026-07-17_21-45_td-006-workspace-write-boundary.md`（同上）
> - `mydocs/codemap/2026-07-17_20-38_hermes-agent-project.md`（项目总图）
> 冲突标记：无（各来源结论一致）

---

## 1. 约束（Constraints）

- 质量门禁：每次提交前 `pytest tests/ -q` + `mypy src/`（strict）+ `ruff check src/ tests/` 全绿；当前基线 **575 passed, 1 skipped**。
- `SecurityConfig.enabled=False` 时行为必须零变化；`build_policy_engine()` 返回 None。
- 自定义 `security.rules` 非空时完全接管，不注入任何默认边界规则。
- 注释/文档中文；public API 类型标注 + 中文 docstring；commit 格式 `type: description`，feat 与 docs 分开提交。
- `mydocs/` 默认不入 git（隐私边界，见 `AGENTS.md`）。

## 2. 接口与契约（Interfaces / Contracts）

```python
# src/agent/sandbox/base.py
@dataclass
class ExecutionResult: exit_code: int; stdout: str; stderr: str; success: bool

class SandboxBackend(Protocol):          # 工具层唯一依赖的沙箱抽象
    async def ping(self) -> bool
    async def execute_code(self, code: str, timeout: int | None = None) -> ExecutionResult
    async def put_file(self, container_path: str, content: bytes) -> bool
    async def get_file(self, container_path: str) -> bytes | None
    def close(self) -> None

# src/agent/sandbox/__init__.py
def create_sandbox_backend(config: SandboxConfig | None = None) -> SandboxBackend
# docker -> DockerSandboxBackend；subprocess -> SubprocessSandboxBackend(timeout=config.timeout)
# 未知值 -> logger.warning + 回退 subprocess

# src/agent/sandbox/subprocess_backend.py（可选能力，非 Protocol 成员）
async def list_dir(self, container_path: str) -> list[str] | None

# src/agent/config.py — SecurityConfig
workspace_path: str = "/workspace"      # 仅默认规则集下生效
def build_policy_engine(self) -> PolicyEngine | None   # 非默认 workspace 时追加 allow-60/deny-55 覆盖
```

〔Trace: 两 Spec §3.2 Signatures；代码：`src/agent/sandbox/`、`src/agent/config.py`〕

## 3. 代码触点（Code Touchpoints）

| 主题 | 位置 |
|---|---|
| 后端选择接线 | `src/agent/core/engine.py` `Agent.__init__`：`sandbox_backend or create_sandbox_backend(config.sandbox if config else None)` |
| 工具类型标注 | `src/agent/tools/*.py`：全部标注 `SandboxBackend`（Protocol） |
| 路径映射核心 | `SubprocessSandboxBackend._resolve()`：POSIX→workspace，resolve 后强制在 root 内 |
| file_list 可选能力优先 | `src/agent/tools/file_list.py`：`getattr(backend, "list_dir", None)` 优先，缺失回退 execute_code |
| 写边界三件套 | `src/agent/core/default_security_rules.yaml`：deny `\.\.` @95 / allow `^/workspace(/|$)` @50 / deny `.*` @1 |
| 边界覆盖注入 | `SecurityConfig._apply_workspace_override()` |

## 4. 已接受模式（Accepted Patterns）

1. **Protocol 结构化抽象优先于 ABC/Union**：新增后端/能力不改既有类。〔Trace: TD-002/003 Spec §2 方案 A〕
2. **执行期冲突先改 Spec 后改码**（Reverse Sync）：`list_dir` 增补为范例流程。
3. **策略即数据**：能用规则优先级表达的边界，不改引擎代码。
4. **错误不外抛**：沙箱/工具层失败返回结果对象（`ExecutionResult(success=False)` / `ToolResult(success=False)`），让 LLM 自我修正。
5. **TDD + 原子 checklist + 双 commit（feat/docs）**。

## 5. 反模式（Anti-patterns，勿再犯）

1. ❌ 在工具层硬编码具体后端类型（本次已清除 5 处 `DockerSandboxBackend` 标注）。
2. ❌ 经 `execute_code` 执行绝对路径文件操作来绕过路径映射（`file_list` 旧实现的教训）。
3. ❌ 向 `evaluation-log.md` 表格插行时依赖通用分隔行做锚点（列数不一致导致两次误插入）；应锚定表头文本。
4. ❌ 工具 handler 抛异常而不是返回失败结果。

## 6. 下一步钩子（Next-step Hooks）

1. **TD-004**：`ToolRegistry.execute()` 检查 handler 签名注入 `execution_context`（详规见 technical-debt-spec §TD-004）；注意 `list_dir` 鸭子类型探测是过渡设计，可在 TD-004 后正式化。
2. **TD-005**：统一"运行时上下文"对象封装 `ContextCache`/`MemoryManager`，解耦 `Agent.__init__`；与 TD-004 共享设计，建议捆绑。
3. **TD-008**：approval callback 注入点可复用 TD-004 成果。
4. **TD-009**：核实 Phase 8.4 交付状态后关闭。
5. **小任务**：`tests/test_evaluation_log.py` 增加表格列数一致性校验。
6. 当前 git HEAD：`00e9479`（本地 master，无远程）。
