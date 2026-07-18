"""验证 Web UI 的核心接口。

设计原则：
  1. Web UI 是演示入口，测试不依赖真实 LLM 或 Docker。
  2. 使用 FastAPI TestClient 做端到端接口测试。
  3. 无 API Key 时自动回退到 EchoClient，保证 CI 通过。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent.web.app import app


@pytest.fixture
def client() -> TestClient:
    """返回已配置的 FastAPI 测试客户端。"""
    return TestClient(app)


class TestWebUIPage:
    """测试页面入口。"""

    def test_index_page_loads(self, client: TestClient) -> None:
        """首页应返回 200 并包含关键 UI 元素。"""
        response = client.get("/")
        assert response.status_code == 200
        text = response.text.lower()
        assert "hermes" in text or "agent" in text
        assert "send" in text or "发送" in text


class TestWebUIChatAPI:
    """测试聊天 API。"""

    def test_chat_endpoint_responds(self, client: TestClient) -> None:
        """发送消息后应返回 messages 和 tool_events。"""
        session_id = uuid.uuid4().hex
        payload = {"message": "hello"}
        response = client.post(f"/api/chat/{session_id}", json=payload)
        assert response.status_code == 200
        data: dict[str, Any] = response.json()
        assert "messages" in data
        assert "tool_events" in data
        assert any(m.get("role") == "user" for m in data["messages"])
        assert any(m.get("role") == "assistant" for m in data["messages"])

    def test_chat_session_isolation(self, client: TestClient) -> None:
        """不同 session_id 的消息历史应该隔离。"""
        sid1 = uuid.uuid4().hex
        sid2 = uuid.uuid4().hex

        client.post(f"/api/chat/{sid1}", json={"message": "session one"})
        client.post(f"/api/chat/{sid2}", json={"message": "session two"})

        resp1 = client.post(f"/api/chat/{sid1}", json={"message": "what did i say"})
        resp2 = client.post(f"/api/chat/{sid2}", json={"message": "what did i say"})

        data1 = resp1.json()
        data2 = resp2.json()
        user_contents_1 = [m["content"] for m in data1["messages"] if m["role"] == "user"]
        user_contents_2 = [m["content"] for m in data2["messages"] if m["role"] == "user"]

        assert "session one" in user_contents_1
        assert "session two" in user_contents_2
        assert "session two" not in user_contents_1
        assert "session one" not in user_contents_2


class TestWebUIValidation:
    """测试输入校验。"""

    def test_chat_requires_message(self, client: TestClient) -> None:
        """请求体缺少 message 时应返回 422。"""
        session_id = uuid.uuid4().hex
        response = client.post(f"/api/chat/{session_id}", json={})
        assert response.status_code == 422


class TestAgentCreationEnvPriority:
    """EVAL-011：Web Agent 创建的环境变量优先级（base_url/model）。"""

    def test_env_base_url_and_model_respected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OPENAI_BASE_URL / OPENAI_MODEL 应覆盖 config 默认值。"""
        from agent.web import app as web_app

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        monkeypatch.setenv("OPENAI_MODEL", "deepseek-chat")
        monkeypatch.setattr(web_app, "_sessions", {})

        agent = web_app._create_agent()
        try:
            assert agent.llm.base_url == "https://api.deepseek.com/v1"
            assert agent.llm.model == "deepseek-chat"
        finally:
            agent._sandbox_backend.close()

    def test_config_defaults_used_when_no_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """无环境变量时使用 config 默认值。"""
        from agent.web import app as web_app

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)

        agent = web_app._create_agent()
        try:
            assert agent.llm.base_url == "https://api.openai.com/v1"
            assert agent.llm.model == "gpt-4o"
        finally:
            agent._sandbox_backend.close()
