"""Tests for the tool router — generates prompts that guide tool selection."""






from agent.core.tool_router import ToolRouter
from agent.core.types import ToolSpec


def _make_tool(name: str, description: str) -> ToolSpec:

    return ToolSpec(

        name=name,

        description=description,

        parameters={"type": "object", "properties": {}},

        handler=lambda: None,

    )





class TestToolRouter:

    """Tests for ToolRouter — builds routing prompts and suggests tools."""



    def test_build_routing_prompt_includes_all_tools(self):

        tools = {

            "sandbox_exec": _make_tool("sandbox_exec", "Execute Python code in sandbox"),

            "file_read": _make_tool("file_read", "Read a file from disk"),

            "finish": _make_tool("finish", "Mark task complete and deliver results"),

        }

        router = ToolRouter(tools)

        prompt = router.build_routing_prompt()



        assert "sandbox_exec" in prompt

        assert "file_read" in prompt

        assert "finish" in prompt



    def test_routing_prompt_has_guidance_header(self):

        router = ToolRouter({"t": _make_tool("t", "desc")})

        prompt = router.build_routing_prompt()



        assert "工具" in prompt
        assert "使用" in prompt


    def test_empty_tools_returns_minimal_prompt(self):

        router = ToolRouter({})

        prompt = router.build_routing_prompt()

        assert len(prompt) > 0  # still returns something



    def test_suggest_tool_data_analysis(self):

        """Steps about loading/analyzing/processing should suggest sandbox_exec."""

        router = ToolRouter({})

        assert router.suggest_tool_category("load CSV and clean data") == "sandbox_exec"

        assert router.suggest_tool_category("calculate monthly averages") == "sandbox_exec"



    def test_suggest_tool_delivery(self):

        """Steps about finalizing should suggest finish."""

        router = ToolRouter({})

        assert router.suggest_tool_category("compile final report") == "finish"

        assert router.suggest_tool_category("deliver results to user") == "finish"



    def test_suggest_tool_unknown_falls_back(self):

        """Unknown step types should still return a sensible default."""

        router = ToolRouter({})

        result = router.suggest_tool_category("do something weird")

        assert result in ("sandbox_exec", "file_ops", "finish")

