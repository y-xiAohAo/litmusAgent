# 评测与优化日志规格

## 目标

建立一套可持续维护的评测日志体系，用于：

1. 记录真实 LLM 端到端测试结果。
2. 追踪 Bug 的发现、根因与修复。
3. 量化优化前后的指标，形成可追溯的量化证据。
4. 支持跨会话接力：新 session 打开项目后能快速恢复上下文。

## 文档清单

| 文档 | 路径 | 说明 |
|---|---|---|
| 评测规格（本文件） | `.kimi/vibe_specs/evaluation-spec.md` | 定义记录格式与维护规则 |
| 评测日志 | `docs/evaluation-log.md` | 实际测试结果、Bug、优化记录 |
| 结构测试 | `tests/test_evaluation_log.py` | 防止 `docs/evaluation-log.md` 腐烂 |

## 记录格式

### 1. 端到端测试结果表

每次用真实 LLM 跑 Demo 后追加一行：

```markdown
| 日期 | 场景 | 模型 | 轮数 | 结果 | 耗时 | 关键问题 |
```

必填字段：日期、场景、模型、轮数、结果、耗时、关键问题。

### 2. Bug 与问题清单

每个 Bug 必须包含：

- ID（如 `EVAL-001`）
- 问题描述
- 严重度（高 / 中 / 低）
- 根因
- 修复方案
- 状态（待解决 / 已修复 / 已验证）

### 3. 优化记录

每次优化必须包含可量化指标：

- 日期
- 模块
- 优化前指标
- 优化后指标
- 提升幅度
- 摘要

## 跨会话维护规则

### 新 session 必读顺序

1. `docs/progress-spec.md` — 当前整体进度。
2. `docs/session-context.md` — 上一次的上下文与决策。
3. `docs/evaluation-log.md` — 最新的测试结果与待解决问题。
4. `CODEMAP.md` — 代码地图。

### 更新时机

- **每次真实 LLM 测试后**：在 `docs/evaluation-log.md` 追加测试结果。
- **每次 Bug 修复后**：追加 Bug 记录或更新状态。
- **每次性能/架构优化后**：追加优化记录，必须包含前后指标。
- **每个 Phase 收尾时**：整理量化摘要。

## 验收标准

- `docs/evaluation-log.md` 存在且包含全部约定章节。
- `tests/test_evaluation_log.py` 全部通过。
- 全量质量门禁通过。
