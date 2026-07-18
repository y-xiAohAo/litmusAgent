"""工具路由器 —— 帮助 LLM 理解"什么时候该用什么工具"。

这个模块不替 Agent 做决定。它的职责是：
  1. 生成一段清晰的工具说明，注入到 system prompt 中
  2. 提供一个简单的关键词匹配方法，给 planner 做初步建议

为什么不是 AI 路由器？
  真正的工具选择是 LLM（通过 function calling）完成的。
  LLM 看到 tool schema + system prompt 后，自己判断该调用哪个。
  ToolRouter 只是确保 LLM 有足够的信息来做这个判断。

suggest_tool_category() 是一个启发式方法：
  - 基于关键词匹配，不是 AI
  - 给 planner 提供一个默认的 tool 类别建议
  - planner 可以将这个建议传给 LLM，LLM 有最终决定权
"""

from __future__ import annotations

from agent.core.types import ToolSpec


class ToolRouter:
    """工具路由器 —— 生成路由提示和工具类别建议。

    使用示例：
        tools = {
            "sandbox_exec": ToolSpec(name="sandbox_exec", ...),
            "file_list": ToolSpec(name="file_list", ...),
            "finish": ToolSpec(name="finish", ...),
        }
        router = ToolRouter(tools)

        # 生成注入到 system prompt 的工具说明
        prompt_section = router.build_routing_prompt()

        # 给 planner 提供建议："这个步骤大概需要什么类型的工具？"
        suggestion = router.suggest_tool_category("读取 CSV 文件")
        # → "sandbox_exec"
    """

    def __init__(self, tools: dict[str, ToolSpec]) -> None:
        """初始化路由器。

        Args:
            tools: 工具名称 → ToolSpec 的映射
                   注意这里是工具的"元数据"，不是工具的可调用实例
        """
        self._tools = tools

    def build_routing_prompt(self) -> str:
        """构建一段系统提示，描述有哪些工具可用以及如何使用。

        这段文本会被追加到 Agent 的 system prompt 中。
        LLM 在每次决策时会看到它，从而知道：
          - 有哪些工具可用
          - 每个工具是干什么的
          - 什么情况下应该用哪个

        如果没有注册任何工具，返回一个简洁的提示。

        设计考虑：
          提示要足够长以提供信息，但不能太长以免抢占 LLM 注意力。
          目前大约 5-10 行，足够清晰又不冗长。
        """
        if not self._tools:
            return "你没有任何可用工具。请直接回答问题。"

        # 逐条列出每工具的名称和描述
        lines = ["你可以使用以下工具，请在合适的时候调用它们：\n"]
        for name, spec in self._tools.items():
            lines.append(f"- **{name}**：{spec.description}")

        # 添加使用指导——告诉 LLM 什么时候用什么
        lines.append(
            "\n使用指导："
            "\n- 需要运行代码或分析数据时，使用 `sandbox_exec`"
            "\n- 持久文件（代码、产物、数据）建议放在 `/workspace` 目录下"
            "\n- 需要读取或查看文件时，使用 `file_list` 或 `file_read`，路径建议为 `/workspace/...`"
            "\n- 需要创建新文件或覆盖整个文件时，使用 `file_write`，路径建议为 `/workspace/...`"
            "\n- 需要修改已有文件的局部内容时，使用 `file_edit`，路径建议为 `/workspace/...`"
            "\n- 任务完全完成时，调用 `finish` 交付结果"
            "\n- 其他情况，直接回复用户"
        )
        return "\n".join(lines)

    def suggest_tool_category(self, step_description: str) -> str:
        """根据步骤描述，建议一个工具类别。

        这是一个纯关键词匹配的启发式方法，不是 AI 推理。
        只有在 planner 需要给 LLM 一个初步建议时才使用。
        LLM 有 function calling 能力，会自行决定最终用哪个工具。

        返回值：
          "sandbox_exec" — 需要执行代码或分析数据
          "finish"       — 任务完成，需要交付结果
          "sandbox_exec" — 默认值（大多数步骤都需要执行代码）

        关键词列表可以根据实际使用情况扩展。
        """
        desc = step_description.lower()

        # 数据处理相关关键词
        data_keywords = [
            "load", "read", "csv", "数据", "clean", "analyze",
            "calculate", "compute", "plot", "chart", "statistics",
            "pandas", "numpy", "code", "execute", "run", "script",
            "读取", "加载", "分析", "计算", "绘图", "图表", "执行",
        ]

        # 交付/完成相关关键词
        finish_keywords = [
            "final", "complete", "deliver", "report", "summary",
            "compile", "present", "output", "完成", "交付", "报告", "总结",
        ]

        # 先检查数据处理关键词（更常见）
        for kw in data_keywords:
            if kw in desc:
                return "sandbox_exec"

        # 再检查交付关键词
        for kw in finish_keywords:
            if kw in desc:
                return "finish"

        # 默认：大多数步骤都需要执行代码
        return "sandbox_exec"
