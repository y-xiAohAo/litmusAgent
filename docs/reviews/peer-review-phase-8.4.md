# Phase 8.4 同行评审报告

> 评审对象：Phase 8.4「记忆审计与用户反馈」实现
> 评审日期：2026-07-04 → 2026-07-10（复评）
> 评审人：Kimi Code CLI
> 基线：331 passed / 1 skipped → 最终：373 passed / 1 skipped
> 质量门禁：pytest ✅ / mypy ✅ / ruff ✅

---

## 1. 变更摘要

| 文件 | 变更性质 | 说明 |
|------|----------|------|
| `src/agent/core/memory.py` | 扩展 | `MemoryEntry` 新增反馈/审计字段；`MemoryManager` 新增 `record_feedback`、`audit`、`_rank_entries`、冲突链接；新增 `MemoryConflict` / `MemoryConflictDetector` |
| `src/agent/config.py` | 扩展 | `MemoryConfig` 新增 `stale_threshold_days=30`、`environment_stale_days=7` |
| `src/agent/cli/__init__.py` | 新增 | CLI 子包标记，导出 `main` |
| `src/agent/cli/memory_cli.py` | 新增 | 纯 argparse CLI：list/show/delete/feedback/audit/export |
| `scripts/hermes-memory.py` | 新增 | CLI 入口包装，处理 `sys.path` 与 UTF-8 输出 |
| `tests/test_memory_feedback.py` | 新增 | 6 条反馈 API 测试 |
| `tests/test_memory_conflict.py` | 新增 | 8 条冲突检测与审计测试 |
| `tests/test_memory_cli.py` | 新增 | 20 条 CLI 测试 |
| `tests/test_memory_manager.py` | 扩展 | 排序增强测试（feedback、confidence、environment 衰减） |
| `tests/test_memory_store.py` | 扩展 | 新增字段序列化/反序列化测试 |
| `docs/progress-spec.md` | 更新 | Phase 8.4 完成状态、测试基线 |
| `docs/session-context.md` | 更新 | Phase 8.4 完成摘要与下一步 |
| `docs/plans/phase-8.4-plan.md` | 新增 | Phase 8.4 计划 |
| `docs/reviews/peer-review-phase-8.4.md` | 新增 | 本评审报告 |
| `CODEMAP.md` | 更新 | Phase 8 完成、CLI 模块、测试数量 |

---

## 2. 质量门禁

```bash
python -m pytest tests/ -q        # 373 passed, 1 skipped
python -m mypy src/               # Success: no issues found in 33 source files
python -m ruff check src/ tests/  # All checks passed!
```

所有门禁通过，基线未破坏。

---

## 3. 已解决的阻塞项

### R1. 范围缺失：CLI 工具与 Markdown 导出未实现 ✅ 已解决

- 已实现 `src/agent/cli/memory_cli.py` + `scripts/hermes-memory.py`。
- 支持全部 6 个命令：`list / show / delete / feedback / audit / export`。
- `show` 默认过滤敏感信息，`--raw` 可输出原始 JSON。
- `export` 按 category 导出 Markdown 到 `.hermes/memory-bank/`，并过滤敏感信息。
- 已新增 `tests/test_memory_cli.py`（20 条测试）覆盖参数解析与命令执行。

### R2. `CODEMAP.md` 严重滞后 ✅ 已解决

- 已更新 Phase 状态表：Phase 7 / Phase 8 改为完成，Phase 9 为下一任务。
- 已新增 `src/agent/cli/` 与 `src/agent/core/memory.py` 模块说明。
- 已更新测试数量与测试文件清单。

---

## 4. 保留的改进建议（非阻塞）

| 编号 | 位置 | 内容 | 风险 |
|------|------|------|------|
| R3 | `MemoryConflictDetector._detect_environment_conflicts` | 环境冲突收集逻辑可进一步简化 | 低 |
| R4 | `MemoryConfig.retrieval_top_k` docstring | 说明实际召回为 `top_k * 2` | 低 |
| R5 | `MemoryManager._rank_entries` | feedback / stale 权重为经验值，建议标注待调优 | 低 |
| R6 | `MemoryManager._apply_conflict_links` | `linked_entry_ids` 当前仅作审计线索，建议文档化 | 低 |
| R7 | `tests/test_memory_conflict.py` | `_write_legacy_entry` 可考虑复用 | 低 |
| R8 | `MemoryManager.audit` | 若未来保存冲突摘要，必须加入脱敏 | 低 |

---

## 5. 设计冲突与风险评估

| 相关 Phase | 评估 | 结论 |
|------------|------|------|
| Phase 10 完整 CLI | 使用 `src/agent/cli/memory_cli.py` 而非 `src/agent/cli.py`，脚本名为 `hermes-memory` 而非 `hermes` | ✅ 无命名冲突，未来可复用 |
| Phase 8.5 Agent 记忆工具 | CLI 与 8.5 工具操作同一 store；`feedback/audit` 走 `MemoryManager` 同一 API | ✅ 无冲突 |
| Phase 9 安全策略引擎 | CLI 为人类特权入口，暂时不接入 Agent 策略；已在文档中说明 | ✅ 可控 |
| Phase 7/8.1-8.3 既有实现 | 未修改 `engine.py`、Tool 签名、JSONL 格式 | ✅ 无冲突 |

新增风险：
- **Windows 终端中文编码**：已在 `scripts/hermes-memory.py` 中强制 `stdout/stderr` 为 UTF-8，实测帮助信息中文正常显示。
- **CLI feedback/audit 绕过 `enabled=False`**：用户显式调用 CLI 时自动将 config 临时设为 `enabled=True`，符合人类管理入口的定位，已在代码注释中说明。

---

## 6. 评审结论

| 维度 | 结论 |
|------|------|
| 质量门禁 | ✅ 通过 |
| 代码质量 | ✅ 良好 |
| 测试覆盖 | ✅ 充分 |
| 范围完整性 | ✅ CLI 与 Markdown 导出已补齐 |
| 文档一致性 | ✅ `CODEMAP.md` / `progress-spec.md` / `session-context.md` 已同步 |
| 跨 Phase 冲突 | ✅ 无冲突 |
| 合入建议 | **通过** — 可进入 Phase 9 |

---

## 7. 下一步建议

1. 进入 **Phase 9：安全策略引擎**。
2. 可选：在 Phase 9 设计文档中预留 CLI 审计日志接入点。
3. 可选：后续迭代处理 R3-R8 中的低优先级改进项。
