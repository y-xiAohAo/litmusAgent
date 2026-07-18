# Demo 指南

本文件说明如何运行 Hermes Agent 的端到端演示脚本。

## 脚本位置

```bash
examples/demo_real_llm.py
```

## 运行方式

### 1. 使用真实 LLM（推荐，能展示完整能力）

```bash
# 设置 API Key（OpenAI 兼容端点均可）
export OPENAI_API_KEY=sk-...

# 使用默认任务（编程并验证斐波那契函数）
python examples/demo_real_llm.py

# 使用自定义任务
python examples/demo_real_llm.py --prompt "读取 /tmp/data.txt 并统计行数"

# 覆盖模型
python examples/demo_real_llm.py --model gpt-4o-mini

# 覆盖 API Key / Base URL（适合 DeepSeek 等兼容端点）
python examples/demo_real_llm.py \
  --api-key "sk-..." \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat"

# 加载自定义配置
python examples/demo_real_llm.py --config examples/config.yaml
```

### 2. 无 API Key 时体验循环结构

```bash
python examples/demo_real_llm.py --echo
```

`--echo` 模式使用 `EchoClient`，不会调用真实 LLM，也不会触发沙箱工具。它用于验证脚本能正常跑通，适合 CI 和无 Key 环境。

## 预期输出

真实 LLM 模式下，Agent 通常会经历以下循环：

1. LLM 决定调用 `sandbox_exec` 编写 `fibonacci` 函数。
2. 再次调用 `sandbox_exec` 验证 `fibonacci(10) == 55`。
3. 调用 `finish` 返回函数源码。

具体输出取决于模型能力、system prompt 和任务描述。

## 常见问题

### 未检测到 API Key

如果看到以下提示，说明环境变量或配置文件中没有提供 Key：

```text
未检测到 API Key
本 Demo 需要真实 LLM 才能展示完整能力。
```

解决方式：

1. 设置环境变量：`export OPENAI_API_KEY=sk-...`
2. 或在 YAML 配置中填写 `llm.api_key`
3. 或使用 `--api-key` 参数
4. 或先用 `--echo` 模式测试

### Docker 沙箱不可用

如果沙箱后端连接失败，Agent 会把错误信息返回给 LLM，由 LLM 决定下一步。 Demo 脚本本身不需要 Docker 才能运行 `--echo` 模式。

### 费用

一个典型 Demo 任务通常只消耗几百到几千 token。建议使用 `gpt-4o-mini` 或 DeepSeek 等成本较低的模型。

## E2E 场景套件（examples/e2e_suite.py）

批量执行预定义联调场景，自动提取轮数、工具序列、耗时与证据断言，输出 Markdown 报告：

```bash
# 全量场景（需 OPENAI_API_KEY）
python examples/e2e_suite.py

# 指定场景（对照场景 ID：S1-sub、S3b）
python examples/e2e_suite.py --only S1,S3

# 冒烟测试（无需 Key）
python examples/e2e_suite.py --echo --only S1
```

场景一览：S1 基础编码验证 / S2 文件工作流 / S3 缺库自愈（禁网）/ S4 多工具链+file_edit / S5 策略拦截；对照：S1-sub（subprocess 后端）、S3b（预置镜像 `hermes-sandbox:latest`，构建见 `examples/docker/Dockerfile.sandbox`）。

2026-07-18 首次联调结果见 `docs/evaluation-log.md` 端到端测试结果（5/7 PASS）。
