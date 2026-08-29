# Feature Spec — TD-014：代码搜索工具（grep / glob 一等工具）

> **层级**：Feature Spec
> **创建**：2026-08-29（SDD-RIPER-ONE，Research 收口 + Plan）
> **修订**：2026-08-29 v2——影响面分析后修订：拆分为 `grep.py`/`glob.py` 双模块（贴合"模块名=工具名=函数名"约定）；通用化参数（include/ignore_case/max_results/glob 递归）；新增 externalizer 预览分支；评测口径决策落盘
> **技术债登记**：`.kimi/vibe_specs/technical-debt-spec.md` TD-014
> **Codemap**：`mydocs/codemap/2026-08-29_litmus-agent-project.md`
> **当前 phase**：Plan（等待 `Plan Approved`）

---

## 1. 最终目标与当前任务单元

- **最终目标**：提供 `grep`（正则内容搜索）与 `glob`（文件名匹配）两个**通用**一等工具，让代码/文件定位不再依赖 `sandbox_exec` 绕行；两工具全程走统一卡口（策略检查 / Trace / ExecutionContext 注入机制）。
- **通用性定义**：不限于代码场景——任意目录/文件路径、任意正则、fnmatch 包含过滤、大小写开关、递归通配（`**`）、可调结果上限；二进制与符号链接安全处理。
- **当前任务单元**：TD-014 单一单元，边界清晰，可一次 Execute 完成。

## 2. 背景与证据

- 默认工具集（`_build_tool_specs`，`src/agent/tools/__init__.py:50-165`）只有 6 个工具，无内容级搜索能力。
- 评测证据：S2/S4 联调中 LLM 用 `sandbox_exec` 一把梭跳过 `file_*` 工具（`docs/evaluation-log.md:47,49`）；Batch 3 引入 `expected_tools` 路径断言（:68）。搜索工具缺失是工具面窄的结构诱因之一（非已证因果）。

## 3. 影响面分析结论（2026-08-29 实测核查）

| 面 | 结论 | 处置 |
|---|---|---|
| 现有测试 | 无工具数量/穷尽断言（全部存在性检查），**零破坏** | 无需改动 |
| 文档防腐测试 | 只查章节结构不查工具名 | `docs/configuration.md:196-200` 人工同步 |
| CLI/Web 渲染 | `render_tool_summary` 通用渲染，无工具名硬编码 | 零改动 |
| 人工确认 | grep/glob 只读，不进 `HumanApprovalConfig.tools` | 零改动 |
| 安全策略 | `_PARAMETRIC_CHECKS` 不加映射 = 参数零检查（硬约束）；默认 read 规则只 deny 敏感路径，`grep(path="/etc")` 默认放行（与 `file_read` 语义一致，接受） | 必加映射；口径写入 §8 |
| 上下文压缩 | externalizer :75-78 按名特判 `file_read` 500 字符，其余工具一律 200 字符 | **决策：加 grep/glob 500 字符预览分支** |
| 批量评测 | `batch_e2e.py:182` 裸 `AgentConfig()` → 所有臂自动获得新工具，token 上涨 + 工具选择可能漂移，新旧批次不可直接对比 | **决策（用户）：接受漂移，后续重新基线；不 pin 旧批次工具集** |

## 4. In Scope / Out of Scope

**In Scope（Must Have）**

1. 新增 `src/agent/tools/grep.py`：
   ```python
   async def grep(
       pattern: str,
       path: str,
       include: str | None = None,
       ignore_case: bool = False,
       max_results: int = 200,
       *,
       backend: SandboxBackend,
   ) -> ToolResult: ...
   ```
2. 新增 `src/agent/tools/glob.py`：
   ```python
   async def glob(
       pattern: str,
       path: str = "/workspace",
       max_results: int = 200,
       *,
       backend: SandboxBackend,
   ) -> ToolResult: ...
   ```
3. 实现统一走 `SandboxBackend.execute_code` 执行只读搜索脚本（方案 A），**不改 `SandboxBackend` Protocol**，Docker/Subprocess 双后端自动兼容：
   - grep 脚本：`os.walk`（不 followlinks）+ `re`（`re.IGNORECASE` 按开关）+ `fnmatch` 过滤 include；path 既可为目录也可为单文件；逐文件 `open(errors="ignore")` 跳过二进制/不可读文件
   - glob 脚本：标准库 `glob.glob(pattern, root_dir=path, recursive=True)`（沙箱内独立进程，与工具模块同名无冲突），支持 `**` 递归
4. 输出约定：grep → `相对路径:行号:匹配行`；glob → 每行一个相对路径；统一条数上限（`max_results`，硬顶 1000）+ 8KB 字节截断，截断注明 `... (truncated)`。
5. 注册：两个 ToolSpec 进 `_build_tool_specs`（`partial(fn, backend=backend)`，`additionalProperties: False`），受 `tools.enabled` 白名单控制；`__all__` 同步导出。
6. 策略卡口：`_PARAMETRIC_CHECKS`（`src/agent/core/engine.py:77-83`）追加 `"grep"`/`"glob"` → `("file/path", "read", "path")`。
7. 外迁预览：`src/agent/core/tool_result_externalizer.py` :75-78 追加 `grep`/`glob` 成功结果 500 字符预览分支（与 `file_read` 同级）。
8. 测试：新增 `tests/test_grep_glob.py`，沿用 `MockSandboxBackend` 模式，覆盖：命中（多文件多行）/ 无命中 / include 过滤 / ignore_case / max_results 截断 / 字节截断 / 非法正则 / path 为单文件 / glob `**` 递归 / 默认 path / execute_code 失败透传 / 策略拒绝 / schema 断言。
9. 文档：`docs/configuration.md` 工具列表（:196-200）追加两条。

**Out of Scope（Non-Goals）**

- 不做语义/embedding 检索，不引入向量库或索引持久化。
- 不改 LLM 工具选择引导（system prompt 调优另立项）。
- 不为搜索工具新增网络或宿主文件系统能力（只限沙箱内）。
- 不追求 ripgrep 级性能；不 pin 评测臂工具集（已决策接受漂移）。

## 5. 方案决策（Innovate 摘要）

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. `execute_code` 跑只读搜索脚本 | 零协议改动；双后端自动兼容；与 `file_list.py` 回退模式一致 | 输出格式需自行约定 | ✅ 采用 |
| B. Protocol 增加 grep/glob 方法 | 语义显式 | 破抽象、协议膨胀 | ❌ 拒绝 |
| 单模块 code_search.py | 文件少 | 违反"模块名=工具名=函数名"约定；`glob` 名与 stdlib 易混 | ❌ 拒绝 |
| 双模块 grep.py + glob.py | 贴合现有约定；沙箱脚本内可用 stdlib glob（独立进程无冲突） | 多一个文件 | ✅ 采用 |

## 6. Research Findings（关键代码事实，含行号）

- **ToolSpec**（`core/types.py:39-57`）：dataclass `name/description/parameters(JSON Schema)/handler`。
- **注册中枢**（`tools/__init__.py`）：`_build_tool_specs` :50-165（file_read 模板 :73-88）；`register_tools_from_config` :333-361 为白名单过滤点；`__all__` :30-47。
- **策略卡口**（`core/engine.py`）：`_PARAMETRIC_CHECKS` :77-83；`file/path` 走 `_normalize_file_path_subject` :263-279；拒绝返回 `ToolResult(content="策略拒绝：...", success=False)`。
- **SandboxBackend**（`sandbox/base.py:34-59`）：Protocol 无 grep/glob；工具自走 `execute_code` 为旁路（不经 sandbox_exec 的 `import os` 禁令，`default_security_rules.yaml:24`）。
- **错误约定**（`file_read.py:29-33`）：`tool_call_id=""` 由 registry 补全；错误用 `{ExcName}: ...` 前缀；参数 `json.dumps` 转义防注入（`file_list.py:41-46` 脚本风格）。
- **测试模式**（`tests/test_tools.py:16-57`）：`MockSandboxBackend(execute_responses=[...])` 顺序回放 + `execute_codes` 记录；schema 断言 `required/properties/additionalProperties`。
- **默认安全规则**：read deny 敏感路径（:70-116），无 read catch-all，`default_action="allow"`（`config.py:173`）。
- **Externalizer**（`tool_result_externalizer.py`）：触发阈值 `externalize_threshold`（默认 800，`config.py:68`）；预览分支 :75-78；外迁后 LLM 看到"工具结果已外迁 + 摘要 + context_read 指引"（:88-99）。

## 7. Plan（File Changes + 原子 Checklist）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `src/agent/tools/grep.py` | 🆕 grep handler + 内嵌搜索脚本 |
| 2 | `src/agent/tools/glob.py` | 🆕 glob handler（stdlib glob recursive） |
| 3 | `src/agent/tools/__init__.py` | `_build_tool_specs` 注册两条 + `__all__` |
| 4 | `src/agent/core/engine.py` | `_PARAMETRIC_CHECKS` 追加两条 |
| 5 | `src/agent/core/tool_result_externalizer.py` | grep/glob 500 字符预览分支 |
| 6 | `tests/test_grep_glob.py` | 🆕 §4.8 全部用例 |
| 7 | `docs/configuration.md` | 工具列表追加两行 |

原子 Checklist：

1. [ ] `grep.py` + `glob.py`（含截断、JSON 防注入、错误前缀约定）
2. [ ] `tools/__init__.py` 注册 + `__all__`
3. [ ] `engine.py` `_PARAMETRIC_CHECKS` 追加
4. [ ] `tool_result_externalizer.py` 预览分支
5. [ ] `tests/test_grep_glob.py`
6. [ ] `docs/configuration.md`
7. [ ] 门禁：`pytest tests/ -q` 全绿（基线 786 + 新增）、`mypy src/`、`ruff check src/ tests/`
8. [ ] Reverse Sync：技术债总表 TD-014 → ✅；codemap §4.4/§5/§8 更新；评测口径变化记入 `docs/evaluation-log.md`（接受漂移、待重新基线）

## 8. 风险与口径

- **搜索输出过大** → max_results（硬顶 1000）+ 8KB 双截断；超 800 字符且压缩启用时走外迁，预览 500 字符。
- **LLM 仍偏好 sandbox_exec** → 不硬扭 prompt；后续可选评测项观察（b3 风格 `expected_tools`）。
- **评测基线口径变化（已决策）** → 新旧批次不可直接对比，需重新基线；记入 evaluation-log。
- **read 放行口径** → `grep(path="/etc")` 默认放行（与 file_read 一致），仅敏感路径 deny；如未来需要 read workspace 边界，另立项。
- **Windows 路径** → 搜索脚本在沙箱内运行（POSIX 语义）；策略 subject 归一化已处理反斜杠。
- **符号链接环/二进制** → os.walk 默认不 followlinks；逐文件 errors="ignore" 跳过。

## 9. Open Questions

- 无阻塞项。

---

## Change Log / Validation / Review

- 2026-08-29 v2：影响面分析 + 通用性设计修订；用户决策×2 落盘（评测口径接受漂移、externalizer 加预览分支）。
- 2026-08-29 Execute 完成（当日 `Plan Approved`）。实际改动：`tools/grep.py` + `tools/glob.py`（新增）、`tools/__init__.py`（注册 + `__all__`）、`core/engine.py`（`_PARAMETRIC_CHECKS` 追加两条）、`core/tool_result_externalizer.py`（grep/glob 并入 500 字符预览分支）、`tests/test_grep_glob.py`（21 用例）、`docs/configuration.md`（工具列表 +2 行）。
- **Validation（实测）**：`pytest tests/test_grep_glob.py -v` = 21 passed；`pytest tests/ -q` = **807 passed, 1 skipped**（基线 786 + 21，无新增失败）；`mypy src/` = 50 文件零错误；`ruff check src/ tests/` 全绿。另以真实 SubprocessSandboxBackend 对 handler 做端到端抽查（include/ignore_case/截断/单文件/非法正则/`**` 递归等）全部符合预期。
- **Execute 中发现的偏差与修复**：内嵌脚本注入 bool/None 参数初版用 `json.dumps` 生成 JSON 字面量（`false`/`null`），在 Python 脚本里非法 → 改用 `repr()`，两条测试断言同步更新。无功能性偏差。
- **Review 三轴**：① Spec↔代码一致（§4 签名/输出约定全部落地，范围零增减）；② 方案 A 零协议改动成立，双后端兼容经真实子进程后端验证；③ 已知口径：二进制文件按 `errors="ignore"` 机制跳过探测（Spec 字面语义）；评测新旧批次不可直接对比（已决策接受漂移）。

## Resume / Handoff

- **状态**：✅ 已完成（2026-08-29），Review 通过
- **Reverse Sync**：技术债总表 TD-014 → ✅（含修复记录）；codemap §4.4/§5/§8 更新；`docs/evaluation-log.md` 优化记录 +1（含评测口径漂移警示）
- **遗留（后续单元）**：评测重新基线；可选评测项观察 grep/glob 使用率（b3 风格 `expected_tools`）
