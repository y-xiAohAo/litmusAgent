# Phase 10.9 Demo 脚本与录制准备

## 目标

为 Hermes Agent 准备一套可一键运行的端到端演示脚本，用于面试展示或教学录制。

## 范围

- `examples/demo_real_llm.py`：真实 LLM 驱动的端到端 Demo。
  - 支持 `--prompt` 自定义任务。
  - 支持 `--config` 加载 YAML 配置。
  - 支持 `--model` 覆盖模型。
  - 支持 `--echo` 模式，无 API Key 时也能跑通。
  - 无 Key 时打印配置说明，而不是崩溃。
- `tests/test_demo.py`：验证 Demo 脚本的 `--help`、`--echo` 和无 Key 提示。
- `docs/demo.md`：Demo 运行指南。

## 非目标

- 不录制视频或 GIF。
- 不引入新的依赖。
- 不修改 Agent 核心引擎。

## API Key 记录

> 以下 Key 仅用于本项目 Demo 调试，已按用户要求记录在规格文件中。

- Provider: DeepSeek
- API Key: `sk-0e19c8f1ac41452e90fb77dfdc63cd02`
- Base URL: `https://api.deepseek.com/v1`
- 默认模型: `deepseek-chat`

运行真实 LLM Demo：

```bash
export OPENAI_API_KEY=sk-0e19c8f1ac41452e90fb77dfdc63cd02
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat
python examples/demo_real_llm.py
```

## 验收标准

- `python examples/demo_real_llm.py --echo` 在无 Key 环境下正常运行。
- `python examples/demo_real_llm.py` 在无 Key 时打印友好提示并退出。
- `pytest tests/test_demo.py` 全部通过。
- 全量质量门禁通过。
