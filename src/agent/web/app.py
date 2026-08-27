"""Litmus Agent Web UI —— 基于 FastAPI 的最小聊天界面。

设计原则：
  1. 不依赖前端构建工具，纯 HTML + 少量 JS。
  2. 无 API Key 时自动回退到 EchoClient，确保可访问和可测试。
  3. 每个浏览器会话对应一个独立的 Agent 实例，保持对话历史。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from agent import Agent
from agent.cli.workspace_guard import apply_bind_safeguards
from agent.config import AgentConfig, load_config
from agent.core.types import Message, ToolCall
from agent.llm import EchoClient, OpenAIClient

app = FastAPI(
    title="Litmus Agent Web UI",
    description="一个用于展示多轮对话、工具调用和沙箱执行的极简 Web 界面。",
)

# 静态文件与模板
_static_dir = Path(__file__).parent / "static"
_templates_dir = Path(__file__).parent / "templates"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")
templates = Jinja2Templates(directory=_templates_dir)

# 内存会话存储：session_id -> Agent
_sessions: dict[str, Agent] = {}


class ChatRequest(BaseModel):
    """聊天请求体。"""

    message: str


class ChatResponse(BaseModel):
    """聊天响应体。"""

    messages: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]


def _has_api_key() -> bool:
    """检查是否存在可用的 API Key。"""
    return bool(os.environ.get("OPENAI_API_KEY", ""))


def _load_web_config() -> AgentConfig:
    """加载 Web 入口使用的配置。

    默认使用内置 AgentConfig；设置环境变量 AGENT_CONFIG 指向 YAML 文件时
    从该文件加载（与 CLI 的 --config 同格式）。
    """
    config_path = os.environ.get("AGENT_CONFIG")
    if config_path:
        return load_config(config_path)
    return AgentConfig()


def _create_agent() -> Agent:
    """根据环境创建一个 Agent 实例。

    有 OPENAI_API_KEY 时使用真实 LLM，否则使用 EchoClient 保证可运行。

    TD-015 单元 C：Web 无写确认交互界面。检测到 host_dir（bind 模式）且
    human_approval 未显式关闭时拒绝创建 Agent 并报错引导；显式
    `human_approval.enabled: false` 才放行（风险自担）。

    同行评审回炉：审批显式关闭的放行路径同样强制与 CLI 共用的
    `apply_bind_safeguards`（git 校验 + 强制快照 + security/read deny
    默认推导），git 校验失败的 ValueError 同样由路由层转 400。
    """
    config = _load_web_config()
    if (
        config.sandbox.host_dir is not None
        and config.agent.human_approval.enabled is not False
    ):
        raise ValueError(
            "Web UI 不支持 bind 工作区（sandbox.host_dir）的写确认流程，已拒绝启动。"
            "请改用 CLI（agent run/chat，支持 y/n/a 确认）；如确需在 Web 下使用"
            " bind 模式，请在配置中显式设置 human_approval.enabled: false（风险自担）。"
        )
    if config.sandbox.host_dir is not None:
        # 保险一/三对 Web 放行路径同样强制（快照 + read deny），与 CLI 同一份实现。
        apply_bind_safeguards(config)
    llm_client: Any
    if _has_api_key():
        # EVAL-011：model/base_url 必须环境变量优先，否则 from_env 收到的
        # 显式值会屏蔽 OPENAI_MODEL / OPENAI_BASE_URL（与 EVAL-001 同类）。
        llm_client = OpenAIClient.from_env(
            api_key=config.llm.api_key or None,
            model=os.environ.get("OPENAI_MODEL") or config.llm.model,
            base_url=os.environ.get("OPENAI_BASE_URL") or config.llm.base_url,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    else:
        llm_client = EchoClient()
    return Agent(
        llm_client=llm_client,
        system_prompt=config.agent.system_prompt,
        max_turns=config.agent.max_turns,
        config=config,
    )


def _get_or_create_agent(session_id: str) -> Agent:
    """获取或创建指定会话的 Agent。"""
    if session_id not in _sessions:
        _sessions[session_id] = _create_agent()
    return _sessions[session_id]


def _serialize_tool_call(tool_call: ToolCall) -> dict[str, Any]:
    """将 ToolCall 序列化为可 JSON 化的字典。"""
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
    }


def _serialize_message(message: Message) -> dict[str, Any]:
    """将 Message 序列化为可 JSON 化的字典。"""
    result: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_calls:
        result["tool_calls"] = [
            _serialize_tool_call(tc) for tc in message.tool_calls
        ]
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    if message.name:
        result["name"] = message.name
    return result


def _extract_tool_events(agent: Agent) -> list[dict[str, Any]]:
    """从 Agent Trace 中提取工具执行事件。"""
    events: list[dict[str, Any]] = []
    for step in agent.get_trace().steps:
        for event in step.events:
            if event.event_type != "tool_execution":
                continue
            payload = event.payload or {}
            events.append({
                "tool": payload.get("tool", "unknown"),
                "arguments": payload.get("arguments", {}),
                "success": payload.get("success", False),
                "content": str(payload.get("content", "")),
            })
    return events


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """返回聊天页面，自动生成一个新的 session_id。"""
    session_id = uuid.uuid4().hex
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"session_id": session_id},
    )


@app.post("/api/chat/{session_id}", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest) -> ChatResponse:
    """处理一次用户消息并返回更新后的消息历史和工具事件。"""
    try:
        agent = _get_or_create_agent(session_id)
    except ValueError as exc:
        # TD-015 单元 C：bind 工作区在 Web 下未显式关闭审批时拒绝启动，
        # 以 400 + 引导信息呈现，不裸 500。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await agent.run(request.message)

    messages = [_serialize_message(m) for m in agent.messages]
    tool_events = _extract_tool_events(agent)
    return ChatResponse(messages=messages, tool_events=tool_events)


@app.on_event("shutdown")
async def _shutdown_close_sessions() -> None:
    """进程退出时统一关闭所有 session 的 Agent，收口沙箱 backend（TD-015）。

    Web session 为进程内常驻，不做 TTL 回收（Non-Goal）；仅依赖进程退出
    钩子释放资源。单个 Agent 关闭异常不影响其余 session。
    使用异步 ``aclose()``（TD-016 同行评审 O3）：等待 MCP server 连接
    回收完成（stdio 子进程退出）后再做同步收尾。
    """
    for agent in _sessions.values():
        try:
            await agent.aclose()
        except Exception:  # noqa: BLE001 —— 关闭异常静默，避免阻塞 shutdown
            pass
    _sessions.clear()


def main() -> None:
    """Web UI 入口。"""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
