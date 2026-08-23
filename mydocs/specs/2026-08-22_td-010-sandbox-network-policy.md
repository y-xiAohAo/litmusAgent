# Feature Spec — TD-010：沙箱网络策略增强（两阶段网络 + 配置化）

> **层级**：Feature Spec
> **创建**：2026-08-22（SDD-RIPER-ONE）
> **技术债登记**：`.kimi/vibe_specs/technical-debt-spec.md` TD-010
> **当前 phase**：Execute 完成（2026-08-22，当日 `Plan Approved`），Review 中

---

## 1. 目标与单元

- **最终目标**：打破 `network=none` 一刀切——默认禁网不变，但允许两种受控开口：①配置化整体网络模式；②"安装阶段"自动放行网络（pip install 意图的执行用有网容器，其余执行维持禁网），支撑缺库自愈场景（S3 类）。
- **单元规模**：单一单元，预估 0.5-1 天。

## 2. 背景证据

- S3 场景（`examples/e2e_suite.py:93-98`）：禁网下 pip 必败，Agent 降级手写实现，比预置镜像对照慢 63%（`docs/evaluation-log.md:48,52`）。
- 现状链路缺口（已核实）：`SandboxConfig` 无网络字段 → 工厂不透传 → 后端构造无网络参数 → 预热池/自动创建写死 `network_mode="none"`（`docker_backend.py:305-333`，`_do_create_container` 无参调用）。
- 现成的切换信号：`sandbox_exec._extract_pip_packages` 已能静态识别 pip install 意图（`sandbox_exec.py:12-78`），且 sandbox_exec 已是 ExecutionContext 感知工具——**引擎主循环和 Planner 无需任何改动**。
- 池模型约束：网络模式在容器 create 时固化，运行中不可改；容器用完即销毁重建。

## 3. 方案决策

| 方案 | 做法 | 结论 |
|---|---|---|
| A. 每次执行按意图选容器 | sandbox_exec 检测到 pip 意图 → 走有网临时容器；否则禁网池 | ✅ 采用（信号现成、粒度精确到单次执行） |
| B. 双池（有网池 + 禁网池） | 预热两种池 | ❌ 池计数测试硬断言多、预热成本翻倍 |
| C. 时间阶段切换 | 先安装阶段后执行阶段 | ❌ 主循环无"阶段"语义，需改引擎，过度设计 |

## 4. 设计

### 4.1 配置（`SandboxConfig` 平铺两字段，贴现有风格）

```python
network_mode: str = "none"           # 容器池网络模式，原样透传（none/bridge/...）
allow_setup_network: bool = False    # 安装阶段自动放行：pip 意图的执行改用有网临时容器
```

- 默认全保持现状（none + False）——零行为回归。
- `allow_setup_network=True` 时有网容器的模式固定为 `"bridge"`（最小暴露面；更细的网络白名单属 Non-Goal）。

### 4.2 后端（`docker_backend.py`）

- `__init__` 新增 `network_mode: str = "none"`；池创建路径（warmup/_acquire_container）透传该值，替代写死的 `"none"`。
- `execute_code(code, timeout=None, *, allow_network: bool = False)`：
  - `False`：现状（池容器）。
  - `True`：现场创建一个**有网临时容器**（network_mode="bridge"，同一 workspace 卷/挂载，其余加固不变），执行完立即销毁，**不入池**——池语义与计数测试不受影响。
- `subprocess_backend.execute_code` 接受并忽略 `allow_network`（本就无网络隔离，docstring 注明）。
- `sandbox/base.py` Protocol 的 `execute_code` 签名追加可选 kwarg（向后兼容）。

### 4.3 工具层（`sandbox_exec.py`）

- 执行前调用现有 `_extract_pip_packages(code)`；检测到包且后端支持 `allow_network`（`inspect.signature` 探测，同 `list_dir` 先例）时传 `allow_network=True`。
- 仅当配置 `allow_setup_network=True` 才启用该行为；配置关闭时完全不走此路径。

### 4.4 工厂（`sandbox/__init__.py`）

透传 `network_mode` / `allow_setup_network`（后者存到后端实例属性供工具层查询，如 `backend.setup_network_enabled`）。

### 4.5 bind 模式交互

bind（host_dir）模式下 `allow_setup_network` 默认仍 False；用户显式开启时打 warning（bind + 有网 = 攻击面叠加，文档警示）。

## 5. In / Out

**In**：§4.1-4.5；测试；文档（configuration.md、usage.md 网络段落）。

**Out**：网络白名单/代理细粒度控制；subprocess 后端的网络隔离；双池；Planner 阶段语义；memory_limit_mb 透传（发现的既有遗漏，另行处理）。

## 6. 涉及文件

| 文件 | 改动 |
|---|---|
| `src/agent/config.py` | +2 字段 |
| `src/agent/sandbox/docker_backend.py` | network_mode 参数 + execute_code allow_network 临时容器路径 |
| `src/agent/sandbox/base.py` | Protocol 签名 |
| `src/agent/sandbox/subprocess_backend.py` | 接受忽略 allow_network |
| `src/agent/sandbox/__init__.py` | 工厂透传 |
| `src/agent/tools/sandbox_exec.py` | pip 意图 → allow_network |
| `tests/test_sandbox.py` / `test_sandbox_factory.py` / 新增 `tests/test_setup_network.py` | 见 §7 |
| `docs/configuration.md` / `docs/usage.md` | 网络配置与口径 |

## 7. 验收

- 配置默认：`network_mode="none"` 池断言不受影响（现有 test_sandbox 网络断言全绿）。
- `network_mode: bridge` 配置后池容器按 bridge 创建。
- `allow_setup_network=True` 且代码含 pip install → 有网临时容器执行且销毁、不入池（计数断言）。
- 无 pip 意图的代码仍走禁网池。
- 配置关闭时 pip 代码也走禁网（现状）。
- subprocess 后端接受 allow_network 不报错。
- 全量门禁：`pytest tests/ -q`（基线 881）+ mypy + ruff 绿。

## 8. 风险

- **有网容器的攻击面**：临时容器仅 bridge 出站，仍 non-root/read_only/同一卷；pip 意图可被诱导（LLM 被 prompt injection 写出 pip install curl exfil）——文档声明口径：allow_setup_network 是便利开关，bind 模式慎用。
- **真实 pip 验证依赖网络/镜像源**：自动测试只做参数层断言；真实 Docker 手工验证作为补验项（同 TD-015 先例）。

## 9. Open Questions

- 无阻塞项。

## Resume / Handoff

- **Execute（2026-08-22）**：改动 `config.py`（+network_mode/allow_setup_network）、`docker_backend.py`（network_mode 贯穿池创建；execute_code allow_network 有网临时容器，用完即毁不入池）、`base.py`/`subprocess_backend.py`（Protocol kwarg）、工厂透传 + bind 开启 warning、`sandbox_exec.py`（pip 意图 + 能力探测 → allow_network）、`tests/test_setup_network.py`（16 例）、configuration/usage 文档。
- **Validation（实测复核）**：897 passed, 1 skipped（+16）；mypy 51 文件零错误；ruff 全绿。
- **实现说明**：allow_network=False 时工具层不传 kwarg（兼容第三方后端）；bind warning 落工厂层。
- **真实 Docker 联网验证（2026-08-22，Docker Desktop 29.7.2 + WSL2）**：禁网池容器内 `pip install six` 失败（pip exit 1），`allow_network=True` 有网临时容器内同一命令成功（exit 0）——两阶段网络行为符合预期。**TD-010 闭环。**
