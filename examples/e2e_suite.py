"""真实 LLM 端到端联调场景套件（E2E Suite）。

用途：
  用真实 LLM + 真实沙箱批量执行预定义场景，自动提取轮数、工具调用
  序列、耗时与证据断言结果，输出可直接粘贴到 evaluation-log 的
  Markdown 报告。

运行方式：
  # 真实联调（需要 OPENAI_API_KEY）
  python examples/e2e_suite.py

  # 只跑指定场景
  python examples/e2e_suite.py --only S1,S3

  # 冒烟测试（无需 API Key，验证套件结构）
  python examples/e2e_suite.py --echo --only S1

安全约定：
  - API Key 仅从环境变量读取，不落盘、不打印。
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from agent import Agent
from agent.config import AgentConfig
from agent.llm import BaseLLMClient, EchoClient, OpenAIClient


@dataclass
class Scenario:
    """单个联调场景定义。"""

    id: str
    name: str
    prompt: str
    backend: str = "docker"
    enable_security: bool = False
    image: str | None = None
    expected_tools: list[str] = field(default_factory=list)
    expected_in_output: list[str] = field(default_factory=list)
    max_turns: int = 15
    config_overrides: dict[str, Any] = field(default_factory=dict)
    two_phase: bool = False
    prompt_b: str = ""
    approval_answers: list[str] | None = None
    llm_summarizer: bool = False


@dataclass
class ScenarioResult:
    """单个场景的执行结果与证据。"""

    scenario_id: str
    success: bool
    turns: int
    tools_used: list[str]
    duration_s: float
    evidence: list[tuple[str, bool]]
    error: str = ""


SCENARIOS: list[Scenario] = [
    Scenario(
        id="S1",
        name="基础编码验证",
        prompt=(
            "请编写一个 Python 函数 fibonacci(n)，在沙箱中验证它对于 "
            "n=10 返回 55，然后返回该函数的源码。"
        ),
        expected_tools=["sandbox_exec"],
        expected_in_output=["55", "def fibonacci"],
    ),
    Scenario(
        id="S2",
        name="文件工作流",
        prompt=(
            "请完成以下任务：1) 用 file_write 在 /workspace/data.csv 写入 "
            "10 个 1-100 的整数（每行一个）；2) 用 sandbox_exec 计算它们的 "
            "均值并写入 /workspace/result.txt；3) 用 file_read 读回结果告诉我。"
        ),
        expected_tools=["file_write", "sandbox_exec", "file_read"],
        expected_in_output=[],
    ),
    Scenario(
        id="S3",
        name="缺库自愈（禁网）",
        prompt="请用 numpy 计算 1 到 100 的标准差，并在沙箱中运行验证。",
        expected_tools=["sandbox_exec"],
        expected_in_output=[],
    ),
    Scenario(
        id="S4",
        name="多工具链+编辑",
        prompt=(
            "请完成以下任务：1) 创建 /workspace/sales.csv，写入 5 行示例销售数据"
            "（含表头 date,amount）；2) 读取它并在 /workspace/report.md 生成一份"
            "简短分析报告，标题为'销售分析'；3) 用 file_edit 把报告标题改为"
            "'销售数据分析报告'；4) 把最终报告内容读给我。"
        ),
        expected_tools=["file_write", "file_read", "file_edit"],
        expected_in_output=["销售数据分析报告"],
    ),
    Scenario(
        id="S5",
        name="策略拦截",
        prompt=(
            "请把配置内容 port=8080 写入 /etc/hermes.conf。"
            "如果无法写入，请说明原因并给出一个可行的替代方案。"
        ),
        enable_security=True,
        expected_tools=["file_write"],
        expected_in_output=["策略拒绝"],
    ),
]

# 对照场景：subprocess 后端复跑 S1；预置镜像复跑 S3
S1_SUBPROCESS = Scenario(
    id="S1-sub",
    name="S1 对照（subprocess）",
    prompt=SCENARIOS[0].prompt,
    backend="subprocess",
    expected_tools=["sandbox_exec"],
    expected_in_output=["55", "def fibonacci"],
)
S3B_PREBAKED = Scenario(
    id="S3b",
    name="S3 对照（预置镜像）",
    prompt=SCENARIOS[2].prompt,
    image="hermes-sandbox:latest",
    expected_tools=["sandbox_exec"],
    expected_in_output=[],
)


def _ensure_utf8_stdout() -> None:
    """Windows 终端强制 UTF-8 输出。"""
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def extract_tool_events(agent: Agent) -> list[dict[str, Any]]:
    """从 Agent Trace 提取工具执行事件。"""
    events: list[dict[str, Any]] = []
    for step in agent.get_trace().steps:
        for event in step.events:
            if event.event_type != "tool_execution":
                continue
            payload = event.payload or {}
            events.append(
                {
                    "tool": payload.get("tool", "unknown"),
                    "arguments": payload.get("arguments", {}),
                    "success": payload.get("success", False),
                    "content": str(payload.get("content", "")),
                }
            )
    return events


def evaluate_evidence(
    sc: Scenario,
    tool_events: list[dict[str, Any]],
    final_answer: str,
) -> list[tuple[str, bool]]:
    """评估场景的证据断言：期望工具被调用 + 期望文本出现。"""
    evidence: list[tuple[str, bool]] = []
    tools_used = [e["tool"] for e in tool_events]
    for tool in sc.expected_tools:
        evidence.append((f"工具 {tool} 被调用", tool in tools_used))
    haystack = final_answer + "\n" + "\n".join(
        e["content"] for e in tool_events
    )
    for text in sc.expected_in_output:
        evidence.append((f"输出包含 {text!r}", text in haystack))
    return evidence


def build_config(sc: Scenario) -> AgentConfig:
    """按场景构建 AgentConfig（含 config_overrides 点分路径覆盖）。"""
    config = AgentConfig()
    config.sandbox.backend = sc.backend
    if sc.image is not None:
        config.sandbox.image = sc.image
    config.agent.max_turns = sc.max_turns
    if sc.enable_security:
        config.security.enabled = True
    for dotted, value in sc.config_overrides.items():
        target = config.agent
        parts = dotted.split(".")
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)
    return config


def _make_scripted_approval(answers: list[str]):
    """构造脚本化人工确认 callback（按序消费 y/n/a 答案）。"""
    remaining = list(answers)
    approved_always: set[str] = set()

    def callback(tool_name: str, arguments: dict[str, Any]) -> bool:
        if tool_name in approved_always:
            return True
        answer = remaining.pop(0) if remaining else "n"
        if answer == "a":
            approved_always.add(tool_name)
            return True
        return answer == "y"

    return callback


async def run_scenario(sc: Scenario, client: BaseLLMClient) -> ScenarioResult:
    """执行单个场景并收集证据。

    支持三种形态：
      - 默认：单 Agent 单 prompt；
      - `two_phase=True`：两个独立 Agent 实例（跨会话语义，S6 记忆叙事），
        通过共享临时 memory_root 传递记忆；
      - `prompt_b` 非空且非 two_phase：同一 Agent 顺序执行两个 prompt
        （消息累积，S7 压缩叙事）。
    """
    start = time.monotonic()
    answer = ""
    events: list[dict[str, Any]] = []
    turns = 0
    try:
        if sc.two_phase:
            import tempfile

            memory_root = tempfile.mkdtemp(prefix="hermes-e2e-mem-")
            for prompt in (sc.prompt, sc.prompt_b):
                config = build_config(sc)
                config.agent.memory.enabled = True
                config.agent.memory.memory_root = memory_root
                agent = Agent(llm_client=client, config=config, max_turns=sc.max_turns)
                try:
                    answer = await agent.run(prompt) or ""
                    events = extract_tool_events(agent)
                    turns += len(agent.get_trace().steps)
                finally:
                    agent._sandbox_backend.close()
        else:
            config = build_config(sc)
            approval_callback = (
                _make_scripted_approval(sc.approval_answers)
                if sc.approval_answers is not None
                else None
            )
            agent = Agent(
                llm_client=client,
                config=config,
                max_turns=sc.max_turns,
                approval_callback=approval_callback,
                summarizer_llm_client=(client if sc.llm_summarizer else None),
            )
            try:
                answer = await agent.run(sc.prompt) or ""
                if sc.prompt_b:
                    answer = await agent.run(sc.prompt_b) or ""
                events = extract_tool_events(agent)
                turns = len(agent.get_trace().steps)
            finally:
                agent._sandbox_backend.close()

        duration = time.monotonic() - start
        evidence = evaluate_evidence(sc, events, answer)
        tools_used = list(dict.fromkeys(e["tool"] for e in events))
        success = bool(answer) and all(ok for _, ok in evidence)
        return ScenarioResult(
            scenario_id=sc.id,
            success=success,
            turns=turns,
            tools_used=tools_used,
            duration_s=round(duration, 1),
            evidence=evidence,
        )
    except Exception as exc:  # noqa: BLE001 —— 联调场景失败也要如实记录
        return ScenarioResult(
            scenario_id=sc.id,
            success=False,
            turns=turns,
            tools_used=[],
            duration_s=round(time.monotonic() - start, 1),
            evidence=[],
            error=f"{type(exc).__name__}: {exc}",
        )


def render_report(results: list[ScenarioResult]) -> str:
    """把场景结果渲染为 Markdown 表格（可直接粘贴 evaluation-log）。"""
    lines = [
        "| 场景 | 结果 | 轮数 | 耗时(s) | 工具序列 | 证据 | 备注 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        verdict = "PASS" if r.success else "FAIL"
        tools = " → ".join(r.tools_used) if r.tools_used else "-"
        passed = sum(1 for _, ok in r.evidence if ok)
        evidence_str = f"{passed}/{len(r.evidence)}"
        note = r.error if r.error else ""
        lines.append(
            f"| {r.scenario_id} | {verdict} | {r.turns} | {r.duration_s} "
            f"| {tools} | {evidence_str} | {note} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """构造套件参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="e2e_suite", description="Litmus Agent 真实 LLM 端到端联调场景套件。"
    )
    parser.add_argument(
        "--only",
        help="只跑指定场景（逗号分隔，如 S1,S3；对照场景：S1-sub、S3b）",
    )
    parser.add_argument(
        "--echo",
        action="store_true",
        help="使用 EchoClient 冒烟测试套件结构（无需 API Key）",
    )
    parser.add_argument("--list", action="store_true", help="列出所有场景后退出")
    return parser


# 亮点叙事场景（2026-07-18）：记忆/压缩/反思
S6_MEMORY = Scenario(
    id="S6",
    name="记忆叙事（跨实例）",
    prompt=(
        "请在 /workspace/notes.md 创建文件，内容为'我的项目代号是 hermes-2026'，"
        "创建后告诉我。"
    ),
    two_phase=True,
    prompt_b="我之前创建过什么文件？里面的项目代号是什么？",
    expected_in_output=["hermes-2026"],
    max_turns=8,
)
S7_COMPRESSION = Scenario(
    id="S7",
    name="压缩叙事（小窗口）",
    prompt=(
        "请记住：我的幸运数字是 4242。然后用 sandbox_exec 打印 1 到 200 的所有整数。"
    ),
    config_overrides={
        "compression.enabled": True,
        "compression.context_window": 600,
        "compression.reserve_tokens": 100,
    },
    prompt_b=(
        "请用 sandbox_exec 打印 300 到 400 的所有整数，"
        "然后告诉我：我的幸运数字是多少？"
    ),
    expected_in_output=["4242"],
    max_turns=8,
)
S8_REFLECTION = Scenario(
    id="S8",
    name="反思叙事（重复错误）",
    prompt=(
        "请读取 /workspace/report_final.txt 的内容并为我总结。"
        "如果遇到问题，请尝试解决。"
    ),
    expected_tools=[],
    expected_in_output=[],
    max_turns=15,
)

# TD-008 真实联调场景：人工确认批准/拒绝
S9_APPROVE = Scenario(
    id="S9",
    name="人工确认（批准）",
    prompt="请用 file_write 在 /workspace/approved.txt 写入内容 hello。",
    config_overrides={"human_approval.enabled": True},
    approval_answers=["y"],
    expected_tools=["file_write"],
    expected_in_output=[],
    max_turns=8,
)
S9B_REJECT = Scenario(
    id="S9b",
    name="人工确认（拒绝）",
    prompt=(
        "请用 file_write 在 /workspace/secret.txt 写入重要配置。"
        "如果无法写入，请说明原因。"
    ),
    config_overrides={"human_approval.enabled": True},
    approval_answers=["n"],
    expected_tools=["file_write"],
    expected_in_output=["用户拒绝"],
    max_turns=8,
)

# S10 安全扫描：危险代码被策略拦截
S10_CODE_SECURITY = Scenario(
    id="S10",
    name="沙箱代码安全扫描",
    prompt=(
        "请在沙箱中执行这段代码：import os\nprint(os.listdir('/'))\n"
        "如果被拒绝，请说明原因并换一种安全的方式完成任务。"
    ),
    enable_security=True,
    expected_tools=["sandbox_exec"],
    expected_in_output=["策略拒绝"],
    max_turns=8,
)

# S11 context_read：大输出外迁后 LLM 读回缓存
S11_CONTEXT_READ = Scenario(
    id="S11",
    name="context_read 外迁读回",
    prompt=(
        "请用 sandbox_exec 打印一首 40 行的编号诗歌（每行格式：第N行-一句诗），"
        "然后告诉我第 38 行的内容是什么。"
    ),
    config_overrides={
        "compression.enabled": True,
        "compression.externalize_threshold": 200,
    },
    expected_tools=["sandbox_exec"],
    expected_in_output=["38"],
    max_turns=10,
)

# S12 LLM 摘要器：压缩走 LLMSummarizer 路径
S12_LLM_SUMMARIZER = Scenario(
    id="S12",
    name="LLM 摘要器压缩",
    prompt=(
        "请记住：我的接头暗号是'夜航西飞'。然后用 sandbox_exec 打印 1 到 200 的所有整数。"
    ),
    config_overrides={
        "compression.enabled": True,
        "compression.context_window": 600,
        "compression.reserve_tokens": 100,
    },
    prompt_b=(
        "请用 sandbox_exec 打印 300 到 400 的所有整数，"
        "然后告诉我：我的接头暗号是什么？"
    ),
    llm_summarizer=True,
    expected_in_output=["夜航西飞"],
    max_turns=8,
)


def _select_scenarios(only: str | None) -> list[Scenario]:
    """按 --only 过滤场景。"""
    catalog = {
        sc.id: sc
        for sc in [*SCENARIOS, S1_SUBPROCESS, S3B_PREBAKED,
                   S6_MEMORY, S7_COMPRESSION, S8_REFLECTION,
                   S9_APPROVE, S9B_REJECT, S10_CODE_SECURITY,
                   S11_CONTEXT_READ, S12_LLM_SUMMARIZER]
    }
    if not only:
        return [*SCENARIOS, S1_SUBPROCESS]
    selected = []
    for sid in only.split(","):
        sid = sid.strip()
        if sid in catalog:
            selected.append(catalog[sid])
        else:
            print(f"⚠️ 未知场景 ID：{sid}（可选：{', '.join(catalog)}）")
    return selected


async def main() -> int:
    """套件入口：逐个执行场景并输出报告。"""
    _ensure_utf8_stdout()
    args = build_parser().parse_args()
    scenarios = _select_scenarios(args.only)
    if args.list:
        for sc in scenarios:
            print(f"{sc.id}: {sc.name}（backend={sc.backend}）")
        return 0
    if not scenarios:
        print("没有要执行的场景。")
        return 1

    if args.echo:
        client: BaseLLMClient = EchoClient()
        print("【冒烟模式】EchoClient，不产生真实证据")
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("未找到 OPENAI_API_KEY 环境变量。")
            return 1
        client = OpenAIClient(
            api_key=api_key,
            model=os.environ.get("OPENAI_MODEL", "deepseek-v4-flash"),
            base_url=os.environ.get(
                "OPENAI_BASE_URL", "https://api.deepseek.com/v1"
            ),
        )

    results: list[ScenarioResult] = []
    for sc in scenarios:
        print(f"\n=== {sc.id}: {sc.name}（backend={sc.backend}）===")
        result = await run_scenario(sc, client)
        verdict = "PASS" if result.success else "FAIL"
        print(f"--- {sc.id} {verdict}（{result.turns} 轮，{result.duration_s}s）")
        results.append(result)

    print("\n========== 联调报告 ==========")
    print(render_report(results))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
