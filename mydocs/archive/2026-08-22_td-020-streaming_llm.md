# 归档：TD-020 流式输出与可观测渲染 — LLM 视角

> 用途：后续会话维护/扩展流式与渲染。只记约束、契约、触点与坑。

## 核心约束（未来任务必须遵守）

1. **主循环只认完整消息**：任何流式改动不得把 partial delta 传进引擎主循环；聚合在客户端层完成（`client.py:_do_chat_stream_request`）。
2. **回调必须兜底**：所有 StreamEvents 回调调用点都要 try/except（客户端 `_safe_stream_callback`、引擎 `_emit_stream_event`）——渲染层异常永远不能中断请求。
3. **默认关闭**：`llm.stream` / `llm.thinking` 默认 False，零行为回归；EchoClient 的流式也是 `--stream` 显式开启。
4. **重试只在产出前**：`progress.produced` 置位后断连禁止重试（用户已看到的 token 不可收回）。
5. **usage 取最后非 null 帧**：DeepSeek v4-flash 中间帧带 `usage: null`（2026-08-22 实测）；不支持 `include_usage` 的端点 400 时降级重试一次，降级不计 usage。

## 触点

| 触点 | 位置 | 说明 |
|---|---|---|
| 流式接口 | `llm/base.py` `BaseLLMClient.chat_stream()` | 默认实现回退 chat()；勿改抽象方法 chat() |
| 回调容器 | `llm/base.py` `StreamEvents` | on_token / on_reasoning / on_tool_start / on_tool_end |
| SSE 解析+聚合 | `llm/client.py` `_do_chat_stream_request` | tool_calls 按 index 聚合；usage 最后非 null |
| 引擎接入点 | `engine.py` `_chat_llm()` | 主循环与 FATAL 解释轮共用；其后逻辑零改动 |
| 工具进度 | `engine.py`（on_tool_start/end 发送点） | 受 `_config_stream` 门控；args 摘要截断 100 字符在调用点 |
| 参数自愈 | `engine.py` tool_calls 解析处 | json.loads 失败 → 失败 ToolResult 回喂 LLM，不穿透 |
| 断连标注 | `engine.py` run() except 分支 | trace_step 记 `stream_partial` 事件 |
| CLI 渲染 | `cli/chat.py` `CliStreamRenderer` | rich=Live 增量 / plain=直出；工具结束标记 plain 用 [OK]/[FAIL]（GBK） |
| 配置 | `config.py` `LLMConfig.stream/thinking` | thinking → 请求体 `thinking: {"type":"enabled"}` |

## 已验证事实（真实端点，DeepSeek v4-flash，2026-08-22）

- thinking+stream：reasoning_content 与 content 分片正常分流
- 多轮对话回传/不回传 reasoning_content 均不 400 → 当前实现不回传（不进 Message 历史，仅渲染）
- 中间帧 usage=null、末帧完整 usage

## Anti-patterns（不要这么做）

- ❌ 把 `chat_stream` 改成抽象方法（57 处 mock 爆炸）
- ❌ 在回调里抛异常给客户端（一个 emoji 崩整轮，CR 实证）
- ❌ 流式断连后重试（重复渲染）
- ❌ 用 url 后缀启发式判别 SSE/HTTP 时不允许显式覆盖（config 有 `transport` 字段，见 TD-016）

## 下一步钩子

- TD-022：Web SSE 端点把 StreamEvents 桥到前端（engine 的 events 已就绪，只差端点+前端）
- 多 Agent 立项时，子 agent 的流式事件如何汇聚到顶层渲染，需要重新设计事件命名空间
