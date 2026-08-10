# Feature Spec — TD-002+TD-003：Subprocess 沙箱后端与 backend 配置生效

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-17 20:55 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"`
> **上游依据**：`.kimi/vibe_specs/technical-debt-spec.md` TD-002 / TD-003 详规（本 Spec 为其执行化）
> **关联 Spec**：`mydocs/specs/2026-07-17_20-38_project-rebaseline.md`（已 CLOSED）

---

## 0. 任务复述（Restate First）

- **最终目标**：让 Hermes Agent 在无 Docker 环境下也能跑通「写代码 → 改代码 → 运行验证」最小闭环。
- **当前任务单元**：
  - TD-002：新增 `SubprocessSandboxBackend` 轻量后端（临时目录 workspace、async 接口与 Docker 后端对齐）。
  - TD-003：新增后端工厂，`config.sandbox.backend` 真正决定默认后端；`Agent.__init__` 未注入后端时走工厂。
- **In Scope**：sandbox 层新后端、工厂函数、engine 接线、tools 类型标注抽象、对应测试与文档同步。
- **Out of Scope**：cgroup/seccomp/网络隔离等 Docker 级安全（明确放弃，轻量 fallback）；容器预热池；`SandboxConfig` schema 变更；已注入 `sandbox_backend` 的行为变更；TD-004/005/006。
- **Done Contract（验证方式）**：
  1. `pytest tests/test_subprocess_backend.py -v` 全过（真实子进程执行，不依赖 Docker）。
  2. 工厂测试：`backend: subprocess/docker/非法值` 三种配置行为正确，非法值警告回退不抛异常。
  3. 工具层在 subprocess 后端上的集成测试通过（`sandbox_exec` + `file_*` 写→读→列→编辑闭环）。
  4. 全量门禁：`pytest tests/ -q`（≥541+新增）、`mypy src/` 零错误、`ruff check src/ tests/` 全绿。

---

## 1. Research Findings（关键事实）

1. **接口面**：`DockerSandboxBackend` public 方法均为 async（`ping/ensure_image/create_container/remove_container/warmup/execute_code/put_file/get_file`），`close()` 为同步；`ExecutionResult` 是 dataclass（`exit_code/stdout/stderr/success`），定义在 `docker_backend.py`。
2. **耦合点**：5 个工具（`sandbox_exec/file_read/file_write/file_list/file_edit`）与 `tools/__init__.py`、`engine.py` 都把 `DockerSandboxBackend` 硬编码为类型标注；`engine.py:285` `self._sandbox_backend = sandbox_backend or DockerSandboxBackend()` 忽略 config（TD-003 根因）。
3. **配置面**：`SandboxConfig.backend: str = "docker"`（docstring 已声明 docker/subprocess 两种），`timeout: int = 30` 可复用。
4. **路径语义**：Docker 后端约定 `/workspace` 持久、`/tmp` 临时；工具与安全策略按 POSIX 风格路径传参。Windows 开发机上 subprocess 后端必须做路径映射。
5. **测试现状**：`tests/test_sandbox.py` 全部 mock Docker SDK，不依赖真实 daemon——新增 subprocess 测试也应保持「无外部依赖」。
6. **既有详规**：TD-002/TD-003 在 `technical-debt-spec.md` 中已有 Must Have / Non-Goals / 验收标准，本 Plan 与其一致并细化为签名级。

## 2. Innovate（方案对比与决策）

| 方案 | 描述 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. Protocol 结构化抽象 | 新增 `sandbox/base.py`：`SandboxBackend(Protocol)` + 迁入 `ExecutionResult`；tools/engine 改注 Protocol | 符合 mypy strict；无需改 docker 类；新增后端零成本 | 多一个文件 | ✅ **选定** |
| B. ABC 抽象基类 | docker/subprocess 继承同一 ABC | 显式继承关系 | 需改动 `DockerSandboxBackend` 类定义，侵入既有稳定代码 | ❌ |
| C. Union 类型 | `DockerSandboxBackend \| SubprocessSandboxBackend` 标注 | 改动最少 | 每加一个后端改所有标注；扩展性差 | ❌ |

**关键设计决策**：
1. **路径映射**：subprocess 后端将沙箱内 POSIX 路径映射到实例临时目录——`/` 映射为 workspace 根（如 `/workspace/main.py` → `<root>/workspace/main.py`，`/tmp/a.txt` → `<root>/tmp/a.txt`），统一语义且天然隔离；所有文件操作 resolve 后强制校验在 root 内（防 `../` 逃逸）。
2. **async 对齐**：subprocess 后端用 `asyncio.create_subprocess_exec` 实现真正 async，签名与 Docker 后端一致，tools 层零感知。
3. **执行环境**：`cwd=workspace 根`，`sys.executable` 调起当前解释器；超时用 `asyncio.wait_for` + kill；stdout/stderr 按 UTF-8（errors=replace）解码。
4. **工厂回退策略**：`docker` → `DockerSandboxBackend()`；`subprocess` → `SubprocessSandboxBackend(timeout=config.timeout)`；未知值 → `logger.warning` + 回退 `subprocess`（无 Docker 环境也能跑，符合 TD-003 详规）。
5. **兼容性**：`ExecutionResult` 迁入 `base.py` 后在 `docker_backend.py` re-export，既有 import 不断裂。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 新增 | `src/agent/sandbox/base.py` | `ExecutionResult`（从 docker_backend 迁入）+ `SandboxBackend(Protocol)` |
| 修改 | `src/agent/sandbox/docker_backend.py` | 改为从 `base` 导入并 re-export `ExecutionResult`；类实现不变 |
| 新增 | `src/agent/sandbox/subprocess_backend.py` | `SubprocessSandboxBackend` 完整实现 |
| 修改 | `src/agent/sandbox/__init__.py` | 导出新符号 + `create_sandbox_backend()` 工厂 |
| 修改 | `src/agent/core/engine.py` | `sandbox_backend: SandboxBackend \| None`；默认 `create_sandbox_backend(config.sandbox if config else None)` |
| 修改 | `src/agent/tools/sandbox_exec.py`、`file_read.py`、`file_write.py`、`file_list.py`、`file_edit.py` | 类型标注 `DockerSandboxBackend` → `SandboxBackend`（仅 import 与标注，逻辑零改动） |
| 修改 | `src/agent/tools/__init__.py` | `TYPE_CHECKING` import 与 `backend` 参数标注同步为 `SandboxBackend` |
| 新增 | `tests/test_subprocess_backend.py` | 后端单元测试（真实子进程，无 Docker 依赖） |
| 新增 | `tests/test_sandbox_factory.py` | 工厂与 engine 接线测试 |
| 修改 | `docs/usage.md`、`docs/configuration.md` | 补充 subprocess fallback 行为说明 |
| 修改 | `CODEMAP.md`、`docs/progress-spec.md`、`docs/session-context.md` | Reverse Sync 文档 |

### 3.2 Signatures（契約级，Execute 不得偏离）

```python
# src/agent/sandbox/base.py
@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    success: bool

class SandboxBackend(Protocol):
    async def ping(self) -> bool: ...
    async def execute_code(self, code: str, timeout: int | None = None) -> ExecutionResult: ...
    async def put_file(self, container_path: str, content: bytes) -> bool: ...
    async def get_file(self, container_path: str) -> bytes | None: ...
    def close(self) -> None: ...

# src/agent/sandbox/subprocess_backend.py
class SubprocessSandboxBackend:
    def __init__(self, timeout: int = 30, workspace_root: str | None = None) -> None: ...
    @property
    def workspace(self) -> str: ...           # 实例临时目录绝对路径
    async def ping(self) -> bool: ...         # 恒 True
    async def ensure_image(self) -> bool: ...  # no-op，恒 True（接口对齐）
    async def create_container(self) -> str | None: ...   # no-op，返回 workspace 路径
    async def remove_container(self) -> bool: ...         # no-op，恒 True
    async def warmup(self, count: int = 2) -> bool: ...   # no-op，恒 True
    async def execute_code(self, code: str, timeout: int | None = None) -> ExecutionResult: ...
    async def put_file(self, container_path: str, content: bytes) -> bool: ...
    async def get_file(self, container_path: str) -> bytes | None: ...
    def close(self) -> None: ...              # 清理临时目录（幂等）
    async def list_dir(self, container_path: str) -> list[str] | None: ...
    # ^ Execute 期发现的必要补充（见 Change Log 2026-07-17 21:20）：
    # file_list 工具通过 execute_code 执行 os.listdir(绝对路径)，
    # 在 subprocess 后端（Windows 宿主机）会绕过路径映射读到错误位置。
    # 因此为 subprocess 后端增加可选能力 list_dir（不进 Protocol，结构化可选），
    # file_list 工具优先使用该能力，缺失时回退原有 execute_code 路径。

# src/agent/sandbox/__init__.py
def create_sandbox_backend(config: SandboxConfig | None = None) -> SandboxBackend: ...
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：写 `tests/test_subprocess_backend.py`——ping / execute_code 成功（stdout）/ 失败（stderr+exit_code）/ 超时 / put_file→get_file 闭环 / 路径逃逸（`../`）拒绝 / close 清理临时目录 / 实例间 workspace 隔离
- [ ] 2. **GREEN**：新增 `base.py`（ExecutionResult 迁入 + Protocol）→ 改 `docker_backend.py` 导入 re-export → 新增 `subprocess_backend.py` → `sandbox/__init__.py` 导出；跑通步骤 1
- [ ] 3. **RED**：写 `tests/test_sandbox_factory.py`——`subprocess`/`docker`/非法值三分支 + `Agent(config=...)` 默认后端类型断言
- [ ] 4. **GREEN**：`create_sandbox_backend()` + `engine.py` 接线；跑通步骤 3
- [ ] 5. tools 5 文件 + `tools/__init__.py` 类型标注替换为 `SandboxBackend`；`mypy src/` 复核零错误
- [ ] 6. 新增 subprocess 后端工具集成测试（并入 `test_subprocess_backend.py`）：`sandbox_exec` + `file_write`→`file_read`→`file_list`→`file_edit` 闭环
- [ ] 7. 文档同步：`docs/usage.md`、`docs/configuration.md`（fallback 说明）、`CODEMAP.md`、`docs/progress-spec.md`、`docs/session-context.md`、本 Spec Reverse Sync
- [ ] 8. 全量质量门禁 + **两个 commit**：`feat: add subprocess sandbox backend and honor sandbox.backend config (TD-002, TD-003)`（代码+测试）→ `docs: sync docs for subprocess backend (TD-002, TD-003)`（文档同步）〔2026-07-17 用户决策：拆成 feat + docs〕

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| ~~Windows 上 `asyncio` 子进程事件循环策略差异~~ | ✅ **2026-07-17 已实测排除**：`WindowsProactorEventLoopPolicy` + `create_subprocess_exec` 在本机运行正常，风险关闭 |
| 路径映射破坏既有 `/workspace` 约定 | 映射规则在 docstring 与文档中显式声明；测试覆盖 `/workspace` 与 `/tmp` 两类路径 |
| `docker_backend.py` import 调整破坏既有引用 | re-export 保持 `from agent.sandbox.docker_backend import ExecutionResult` 可用；全量测试兜底 |
| 回滚 | `git checkout HEAD -- src/agent/sandbox src/agent/tools src/agent/core/engine.py` + 删除新增文件 |

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 RED | `tests/test_subprocess_backend.py`（14 例） | 收集错误，失败成立 |
| 2 GREEN | `sandbox/base.py` + `subprocess_backend.py` + `__init__.py` + `docker_backend.py` re-export | 14 passed |
| 3 RED | `tests/test_sandbox_factory.py`（7 例） | 接线测试 1 失败（engine 硬编码 Docker），RED 成立 |
| 4 GREEN | `engine.py` 工厂接线 + 标注 `SandboxBackend` | 21 passed |
| 5 | tools 5 文件 + `tools/__init__.py` 标注抽象 | mypy 44 文件零错误 |
| 冲突 | file_list 经 execute_code 走绝对路径绕过映射 → 新增可选能力 `list_dir`（先改 Spec 再改码） | 已解决 |
| 6 | 工具集成测试 4 例（写→读→列→改→运行闭环） | 47 passed |
| 7 | 文档同步（configuration/usage/CODEMAP/progress-spec/session-context/technical-debt-spec） | 已落盘 |
| 8 | 门禁 + 双 commit：`811babb`（feat）、`e8b4c6e`（docs） | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. `test_subprocess_backend.py` 全过（无 Docker 依赖） | 18 passed（14 单元 + 4 工具集成），真实子进程执行 | ✅ |
| 2. 工厂三分支正确、非法值警告回退不抛异常 | `test_sandbox_factory.py` 7 passed（docker/subprocess/gVisor 回退 + Agent 接线三场景） | ✅ |
| 3. 工具层 subprocess 闭环 | 集成测试覆盖 sandbox_exec + file_write/read/list/edit + 跨工具 workspace 一致 | ✅ |
| 4. 全量门禁 | `pytest tests/` **566 passed, 1 skipped**（基线 541+25）；`mypy src/` 44 文件零错误；`ruff check src/ tests/` 全绿 | ✅ |

## 6. Review Verdict

**评审时间**：2026-07-17 22:10 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 行为级抽查脚本实测）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 是否清晰且可验证 | **PASS** | Spec §0 Done Contract 4 条均有实测证据（见 §5 Validation）；In/Out 边界明确（不做 cgroup/网络隔离/预热池，与 TD-002 详规一致） |
| Axis-1 需求达成 | TD-002 验收（后端同名 public 方法、临时目录隔离、超时） | **PASS** | `test_subprocess_backend.py` 18 例覆盖；行为抽查：子进程执行成功/失败/超时均符合预期 |
| Axis-1 需求达成 | TD-003 验收（配置驱动、非法值回退、注入优先） | **PASS** | `test_sandbox_factory.py` 7 例；行为抽查 1a/1b：`subprocess` config → SubprocessSandboxBackend，无 config → DockerSandboxBackend |
| Axis-2 Spec-代码一致性 | File Changes 与 Plan §3.1 对照 | **PASS** | 11 项文件变更全部落实，无计划外文件（`mydocs/` Spec 产物除外） |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS（含 1 项已记录增补）** | `list_dir` 为 Plan 外新增，但属执行期冲突的 Spec 先行修订（Change Log 21:20），流程合规 |
| Axis-2 行为一致性 | 工具层在 subprocess 后端的闭环 | **PASS** | 行为抽查 2a-2c：write→exec→edit→read→list 全部符合预期 |
| Axis-3 代码质量 | 正确性/健壮性 | **PASS** | 路径逃逸 resolve 校验、超时 kill、close 幂等、异常不抛（与 Docker 后端语义一致）；Windows 实测通过 |
| Axis-3 代码质量 | 可维护性/测试充分性 | **PASS** | 中文 docstring 完整；25 个新测试含边界与隔离用例；既有 541 例零回归 |
| Axis-3 风险 | 安全/回归 | **PASS（附观察项）** | subprocess 后端不提供 OS 级隔离——已在 docstring 与文档中显式声明为轻量 fallback，符合 TD-002 Non-Goals；非阻塞 |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞，供后续参考）
1. `file_list` 的 `getattr(backend, "list_dir", None)` 鸭子类型探测是过渡设计；TD-004（ExecutionContext/工具签名机制）落地时可考虑把可选能力纳入正式协议。
2. subprocess 后端执行的代码若硬编码绝对 POSIX 路径（如 `open('/workspace/x')`）在 Windows 宿主机上不可见——已通过 `file_list`/`list_dir` 与 cwd 设计缓解工具路径，纯 LLM 代码场景为已知限制，文档已声明。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| `list_dir` 可选能力 | 未包含 | 新增于 subprocess_backend + file_list 优先调用 | ✅ 执行期冲突修订，先改 Spec 后改码，合规 |
| commit 粒度 | 单一 commit | feat + docs 双 commit | ✅ 用户显式决策（Change Log 21:05） |
| 其余 File Changes / Signatures / Checklist | — | 全部一致 | — |

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-17 20:55 | sdd_bootstrap TD-002+003：Research 完成（耦合点/接口面/配置面核实），Innovate 选定方案 A（Protocol 抽象），Plan 落盘，等待 `Plan Approved` |
| 2026-07-17 21:05 | 开发前环境核查（Reverse Sync）：pytest 541 passed 实测复核；Windows asyncio 子进程实测可用（风险表第一项关闭）；git 无远程（用户决策：暂不配置，commit 仅本地）；commit 粒度（用户决策：拆成 feat + docs 两个 commit）。任务已完全澄清，无遗留 Open Questions |
| 2026-07-17 21:10 | `Plan Approved` 收到，进入 EXECUTE。步骤 1-2 完成：base.py / subprocess_backend.py / __init__.py / test_subprocess_backend.py 落盘，14 passed |
| 2026-07-17 21:15 | 步骤 3-4 完成：test_sandbox_factory.py（7 例）RED→GREEN，engine.py 工厂接线，21 passed |
| 2026-07-17 21:18 | 步骤 5 完成：tools 5 文件 + tools/__init__.py 标注替换为 SandboxBackend，mypy 44 文件零错误 |
| 2026-07-17 21:20 | Execute 期逻辑冲突（Reverse Sync 先改 Spec 再改码）：file_list 经 execute_code 执行绝对路径 os.listdir，在 subprocess 后端绕过路径映射。决策：subprocess 后端增加可选能力 `list_dir`，file_list 优先使用、缺失时回退原路径；Docker 后端零改动 |
| 2026-07-17 21:30 | Execute 完成：8 步 checklist 全部落实，566 passed / mypy / ruff 全绿；双 commit `811babb`（feat）+ `e8b4c6e`（docs）；Validation 4 项验收全部达成，待 `REVIEW EXECUTE` |
| 2026-07-17 22:10 | REVIEW EXECUTE 完成：三轴全 PASS（含行为级抽查脚本实测），Overall Verdict = PASS（可关闭），Blocking Issues = 无，Plan-Execution Diff 含 1 项合规修订（list_dir） |

## 9. Archive Record

| 时间 | 归档产物 | 模式 |
|---|---|---|
| 2026-07-17 22:15 | `mydocs/archive/2026-07-17_22-15_td-governance-round1_human.md` + `..._llm.md` | thematic（与 TD-006 合并主题"技术债治理第一轮"） |

- 归档为知识衍生品，不影响本 Spec 的真相源地位；原始文件未删除/未移动。
