# 归档：TD-020 流式输出与可观测渲染 — 人类视角

> 完成：2026-08-29 | Spec：`mydocs/specs/2026-08-29_td-020-streaming.md` | Commit：`4edf822` + `d569d87`

## 做了什么

LLM 回复从"整轮结束一次性返回"变为三层可观测：正文逐字流式、思考链（reasoning_content）弱化渲染、工具调用实时进度行。CLI 加 `--stream` 开关；DeepSeek 退役模型名迁移到 v4 口径并支持 `thinking` 参数。

## 关键决策（为什么这么做）

1. **方案 A（旁路渲染）而非流进内循环**：`chat_stream()` 聚合完才交主循环，token 经 StreamEvents 回调旁路给渲染层。内循环零改动，策略/Trace/错误分类全部白拿。Pi 式"流进循环"被否——会把 partial 状态传染给整个框架。
2. **默认实现回退**：`chat_stream` 是基类普通方法（默认调 `chat()` 一次性回调），不是抽象方法——57 处现有 mock 零改动，这是整个方案便宜的关键。
3. **重试纪律**：产出任何 token 后断连不重试（用户已看到的字收不回）；产出前可重试。
4. **usage 口径**：发 `include_usage`，取最后非 null 帧（DeepSeek 中间帧是 null，真实端点抓出来的 bug）；端点 400 不认识该参数时降级重试一次。

## 踩过的坑（CR + 实测发现）

- 客户端直接调渲染回调无兜底：一个 GBK 不支持的字符就能崩整轮流式（Windows 管道）→ 回调全包 try/except
- Rich Live 跨轮 buffer 污染：第二轮会把第一轮全文重复渲染 → on_tool_start 时清 buffer
- 聚合容错会产出非法 JSON arguments → 引擎 json.loads 失败改为构造失败 ToolResult 回喂 LLM 自愈，不穿透
- plain 模式 ✓/✗ 在 GBK 下炸 → 改 [OK]/[FAIL]

## 结果

- 973 passed / 1 skipped（+30 测试）；mypy 52 文件、ruff 全绿
- 真实端点（DeepSeek v4-flash）验证：thinking+stream 正常、reasoning_content 回传/不回传均不 400、usage 修复确认

## 遗留

- Web 端流式未做（并入 TD-022 一起：SSE 端点 + 前端）
- reasoning_content 不回传是当前安全选择，若未来端点要求回传，改 Message 序列化一处即可
