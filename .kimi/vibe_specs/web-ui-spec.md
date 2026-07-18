# Web UI 规格

## 背景

当前 Hermes Agent 主要通过终端 CLI 交互。为了更直观地展示多轮对话、工具调用和沙箱执行结果，新增一个最小可用的 Web UI。

## 目标

提供一个基于浏览器的单页聊天界面，能够：

1. 与 Agent 进行多轮对话。
2. 展示每一轮中的工具调用（tool name、arguments、success、output）。
3. 展示 Agent Trace 中的关键事件。
4. 无需前端构建工具，纯 HTML + 少量 JS 即可运行。

## 非目标

- 不实现流式 SSE（第一版采用请求-响应模式，降低复杂度）。
- 不支持用户登录、持久化会话、多用户并发隔离（会话仅存内存）。
- 不替代 CLI，只作为演示和调试入口。

## 架构

```
用户浏览器
    ↓ HTTP / POST
FastAPI (src/agent/web/app.py)
    ↓ 调用
Agent（内存中按 session_id 保存）
    ↓ 工具调用
DockerSandboxBackend
```

## 接口

### 页面

- `GET /`：返回聊天页面，自动生成 `session_id`。

### API

- `POST /api/chat/{session_id}`
  - Body: `{"message": "用户输入"}`
  - Response:
    ```json
    {
      "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "...", "tool_calls": [...]}
      ],
      "tool_events": [
        {"tool": "sandbox_exec", "arguments": {...}, "success": true, "content": "..."}
      ]
    }
    ```

## 会话管理

- 使用内存字典 `sessions: dict[str, Agent]` 保存 Agent 实例。
- 每个 session 独立维护自己的 `messages` 和 `trace`。
- 无 API Key 时自动回退到 `EchoClient`，保证页面可访问和测试通过。

## 页面结构

```html
- 顶部：标题 + 新会话按钮
- 左侧：消息历史
- 右侧：工具调用 / Trace 面板
- 底部：输入框 + 发送按钮
```

## 依赖

新增到 `pyproject.toml`：

- `fastapi>=0.110.0`
- `uvicorn[standard]>=0.27.0`
- `jinja2>=3.1.0`

## 运行方式

```bash
pip install -e ".[dev]"
python -m agent.web.app
# 或
uvicorn agent.web.app:app --reload
```

浏览器打开 `http://localhost:8000`。

## 验收标准

- `GET /` 返回 200 且页面包含聊天界面元素。
- `POST /api/chat/{session_id}` 在无 API Key 环境下使用 EchoClient 正常返回。
- 返回的 JSON 包含 messages 和 tool_events 字段。
- `pytest tests/test_web_ui.py` 全部通过。
- 全量质量门禁通过。
