"""工具执行策略拦截测试。"""

from __future__ import annotations

import pytest

from agent.core.engine import ToolRegistry
from agent.core.security import PolicyAction, PolicyEngine, PolicyRule
from agent.core.types import ToolCall, ToolResult, ToolSpec


class DummyBackend:
    """用于文件工具测试的简单 backend 占位。"""

    async def get_file(self, path: str) -> bytes | None:
        return b"dummy content"

    async def execute_code(self, code: str):
        class DummyResult:
            success = True
            stdout = "ok"
            stderr = ""
        return DummyResult()


def make_call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=arguments)


class TestToolRegistryPolicyDisabled:
    """策略未注入时，ToolRegistry 行为不变。"""

    @pytest.mark.asyncio
    async def test_no_policy_allows_tool_execution(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="echo",
                description="echo",
                parameters={"type": "object", "properties": {}},
                handler=lambda: "ok",
            )
        )
        result = await registry.execute(make_call("echo", {}))
        assert result.success is True
        assert result.content == "ok"


class TestToolRegistryToolLevelDeny:
    """工具名级别的策略拒绝。"""

    @pytest.mark.asyncio
    async def test_deny_specific_tool_by_name(self) -> None:
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="dangerous_tool",
                    action=PolicyAction.DENY,
                    reason="禁止调用该工具",
                    use_regex=False,
                ),
            ],
        )
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="dangerous_tool",
                description="dangerous",
                parameters={"type": "object", "properties": {}},
                handler=lambda: "should not run",
            )
        )
        result = await registry.execute(make_call("dangerous_tool", {}))
        assert result.success is False
        assert "策略拒绝" in result.content
        assert "禁止调用该工具" in result.content

    @pytest.mark.asyncio
    async def test_allow_other_tools(self) -> None:
        policy = PolicyEngine(
            rules=[
                PolicyRule(
                    resource="tool",
                    operation="execute",
                    pattern="dangerous_tool",
                    action=PolicyAction.DENY,
                    reason="禁止",
                    use_regex=False,
                ),
            ],
        )
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="safe_tool",
                description="safe",
                parameters={"type": "object", "properties": {}},
                handler=lambda: "ok",
            )
        )
        result = await registry.execute(make_call("safe_tool", {}))
        assert result.success is True
        assert result.content == "ok"


class TestToolRegistryDefaultPolicy:
    """使用 Phase 9 默认规则集的策略拦截。"""

    @pytest.fixture
    def policy(self) -> PolicyEngine:
        return PolicyEngine.default()

    @pytest.mark.asyncio
    async def test_sandbox_exec_deny_import_os(self, policy: PolicyEngine) -> None:
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="sandbox_exec",
                description="exec",
                parameters={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                },
                handler=lambda code: "should not run",
            )
        )
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "import os\nprint(os.getcwd())"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_file_read_deny_sensitive_path(self, policy: PolicyEngine) -> None:
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_read",
                description="read",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
                handler=lambda path: "should not run",
            )
        )
        result = await registry.execute(
            make_call("file_read", {"path": "/etc/passwd"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_memory_read_deny_unauthorized_category(self, policy: PolicyEngine) -> None:
        policy.add_rule(
            PolicyRule(
                resource="memory/category",
                operation="read",
                pattern="secrets",
                action=PolicyAction.DENY,
                reason="禁止读取 secrets 记忆",
                use_regex=False,
            )
        )
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="memory_read",
                description="read memory",
                parameters={
                    "type": "object",
                    "properties": {"uri": {"type": "string"}},
                },
                handler=lambda uri: "should not run",
            )
        )
        result = await registry.execute(
            make_call("memory_read", {"uri": "hermes://memory/secrets/entry.jsonl"})
        )
        assert result.success is False
        assert "禁止读取 secrets 记忆" in result.content

    @pytest.mark.asyncio
    async def test_file_list_deny_sensitive_path(self, policy: PolicyEngine) -> None:
        """file_list 读取敏感路径应被拒绝。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_list",
                description="list",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
                handler=lambda path: "should not run",
            )
        )
        result = await registry.execute(
            make_call("file_list", {"path": "/etc/passwd"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_file_write_deny_sensitive_path(self, policy: PolicyEngine) -> None:
        """file_write 写入敏感路径应被拒绝。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_write",
                description="write",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
                handler=lambda path, content: "should not run",
            )
        )
        result = await registry.execute(
            make_call("file_write", {"path": "/etc/passwd", "content": "hack"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_file_edit_deny_sensitive_path(self, policy: PolicyEngine) -> None:
        """file_edit 编辑敏感路径应被拒绝。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_edit",
                description="edit",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                },
                handler=lambda path, old_string, new_string: "should not run",
            )
        )
        result = await registry.execute(
            make_call(
                "file_edit",
                {"path": "/etc/passwd", "old_string": "root", "new_string": "admin"},
            )
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_memory_read_invalid_uri_allowed(self, policy: PolicyEngine) -> None:
        """非法 URI 无法解析 category，参数级检查跳过，由工具 handler 自行处理。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="memory_read",
                description="read memory",
                parameters={
                    "type": "object",
                    "properties": {"uri": {"type": "string"}},
                },
                handler=lambda uri: ToolResult(tool_call_id="", content="not found", success=False),
            )
        )
        result = await registry.execute(
            make_call("memory_read", {"uri": "invalid-uri"})
        )
        # 参数级检查无法解析，不拦截；handler 返回失败
        assert "策略拒绝" not in result.content


class TestToolRegistryPathNormalization:
    """验证 file/path 参数归一化后能拦截 Windows 路径与大小写绕过。"""

    @pytest.fixture
    def policy(self) -> PolicyEngine:
        return PolicyEngine.default()

    @pytest.mark.asyncio
    async def test_deny_windows_sam_path(self, policy: PolicyEngine) -> None:
        """Windows 风格 SAM 路径应被拒绝。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_read",
                description="read",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
                handler=lambda path: "should not run",
            )
        )
        result = await registry.execute(
            make_call("file_read", {"path": "C:\\Windows\\System32\\config\\SAM"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_case_variation_of_etc_passwd(
        self, policy: PolicyEngine
    ) -> None:
        """大写 /ETC/PASSWD 经归一化后应被拒绝。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_read",
                description="read",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
                handler=lambda path: "should not run",
            )
        )
        result = await registry.execute(
            make_call("file_read", {"path": "/ETC/PASSWD"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_backslash_ssh_path(self, policy: PolicyEngine) -> None:
        """反斜杠形式的 .ssh 路径经归一化后应被拒绝。"""
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_list",
                description="list",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
                handler=lambda path: "should not run",
            )
        )
        result = await registry.execute(
            make_call("file_list", {"path": "C:\\Users\\admin\\.ssh\\id_rsa"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content


class TestToolRegistryNonStringArguments:
    """验证非字符串参数不会导致策略评估抛异常中断主循环。"""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        policy = PolicyEngine.default()
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="sandbox_exec",
                description="exec",
                parameters={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                },
                handler=lambda code: f"executed: {code}",
            )
        )
        registry.register(
            ToolSpec(
                name="file_read",
                description="read",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
                handler=lambda path: "content",
            )
        )
        registry.register(
            ToolSpec(
                name="memory_read",
                description="read memory",
                parameters={
                    "type": "object",
                    "properties": {"uri": {"type": "string"}},
                },
                handler=lambda uri: "memory content",
            )
        )
        return registry

    @pytest.mark.asyncio
    async def test_int_code_does_not_raise(self, registry: ToolRegistry) -> None:
        """code 为整数时不应抛 TypeError，交由 handler 处理。"""
        result = await registry.execute(
            make_call("sandbox_exec", {"code": 123})
        )
        # 非字符串参数经 str() 防御后不会匹配默认规则，不抛异常即通过
        assert "TypeError" not in result.content

    @pytest.mark.asyncio
    async def test_none_path_does_not_raise(self, registry: ToolRegistry) -> None:
        """path 为 None 时不应抛 TypeError，交由 handler 处理。"""
        result = await registry.execute(
            make_call("file_read", {"path": None})
        )
        assert "TypeError" not in result.content

    @pytest.mark.asyncio
    async def test_int_uri_does_not_raise(self, registry: ToolRegistry) -> None:
        """uri 为整数时不应抛 TypeError，交由 handler 处理。"""
        result = await registry.execute(
            make_call("memory_read", {"uri": 123})
        )
        assert "TypeError" not in result.content



class TestWorkspaceWriteBoundary:
    """TD-006：file/path write 的默认 workspace 边界。

    默认规则集下：
      - /workspace 下允许写入/编辑；
      - /tmp 等 workspace 以外路径默认拒绝；
      - 含 ".." 的逃逸路径拒绝（即使前缀是 /workspace）。
    """

    @pytest.fixture
    def policy(self) -> PolicyEngine:
        return PolicyEngine.default()

    @pytest.fixture
    def registry(self, policy: PolicyEngine) -> ToolRegistry:
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="file_write",
                description="write",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
                handler=lambda path, content: "written",
            )
        )
        registry.register(
            ToolSpec(
                name="file_edit",
                description="edit",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                },
                handler=lambda path, old_string, new_string: "edited",
            )
        )
        return registry

    @pytest.mark.asyncio
    async def test_write_workspace_allowed(self, registry: ToolRegistry) -> None:
        """写 /workspace 下路径被允许。"""
        result = await registry.execute(
            make_call("file_write", {"path": "/workspace/main.py", "content": "x = 1"})
        )
        assert result.success is True
        assert result.content == "written"

    @pytest.mark.asyncio
    async def test_write_tmp_denied_by_default(self, registry: ToolRegistry) -> None:
        """写 /tmp 等 workspace 以外路径默认被拒绝。"""
        result = await registry.execute(
            make_call("file_write", {"path": "/tmp/foo.py", "content": "x = 1"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_write_dotdot_escape_denied(self, registry: ToolRegistry) -> None:
        """含 .. 的逃逸路径被拒绝（即使以 /workspace 开头）。"""
        result = await registry.execute(
            make_call(
                "file_write", {"path": "/workspace/../tmp/evil.py", "content": "x"}
            )
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_edit_workspace_allowed_tmp_denied(
        self, registry: ToolRegistry
    ) -> None:
        """file_edit 共享同一边界：/workspace 允许，/tmp 拒绝。"""
        ok = await registry.execute(
            make_call(
                "file_edit",
                {"path": "/workspace/a.py", "old_string": "1", "new_string": "2"},
            )
        )
        assert ok.success is True
        assert ok.content == "edited"

        denied = await registry.execute(
            make_call(
                "file_edit",
                {"path": "/tmp/a.py", "old_string": "1", "new_string": "2"},
            )
        )
        assert denied.success is False
        assert "策略拒绝" in denied.content

    @pytest.mark.asyncio
    async def test_sensitive_path_still_denied_first(
        self, registry: ToolRegistry
    ) -> None:
        """敏感路径拒绝规则（高优先级）不受边界 allow 影响。"""
        result = await registry.execute(
            make_call("file_write", {"path": "/etc/passwd", "content": "hack"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content
