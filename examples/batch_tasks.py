"""批量 E2E 评测任务集（Batch 1：20 任务）。

设计约定：
  - 判分方式二选一：verify_script（断言类，沙箱内执行，退出码 0 = 通过）
    或 judge_rubric（开放类，LLM-judge 按 rubric 打分 1-5，≥4 通过）。
  - 断言类任务的数据在 prompt 中内联固定，保证判分确定性。
  - 所有产物路径限定在 /workspace 下（TD-006 边界）。
  - verify_script 仅使用 Python 标准库（沙箱镜像禁网、无第三方包）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BatchTask:
    """批量评测任务定义。

    Attributes:
        id: 任务编号（T01..T20）。
        name: 任务短名。
        category: 算法 / 文件处理 / 数据分析 / 多步链路 / 开放报告。
        difficulty: 难度层级 L1（单步）/ L2（2-3 步）/ L3（多步链路）。
        prompt: 给 Agent 的任务指令。
        verify_script: 断言类判分脚本（沙箱内执行，退出码 0 = 通过）。
        judge_rubric: 开放类 LLM-judge 评分标准（1-5 分，≥4 通过）。
        max_turns: Agent 最大轮数。
    """

    id: str
    name: str
    category: str
    difficulty: str
    prompt: str
    verify_script: str | None = None
    judge_rubric: str | None = None
    artifact_path: str = ""  # 开放类：judge 读取的产物路径（/workspace/...）
    max_turns: int = 12
    expected_tools: list[str] = field(default_factory=list)  # 工具路径断言：这些工具必须被调用
    prompt_b: str = ""  # 两阶段任务的 phase B 查询（非空即两阶段执行）
    expected_in_answer: list[str] = field(default_factory=list)  # 答案须包含的关键事实（记忆召回判分）


# ---------------------------------------------------------------------------
# 算法（5）
# ---------------------------------------------------------------------------

T01 = BatchTask(
    id="T01",
    name="快速排序",
    category="算法",
    difficulty="L1",
    prompt=(
        "请用 Python 实现快速排序算法，用它对列表 [38, 27, 43, 3, 9, 82, 10] "
        "排序，并把排序结果以逗号分隔（无空格）写入 /workspace/sorted.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/sorted.txt').read_text().strip()\n"
        "ok = content == '3,9,10,27,38,43,82'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T02 = BatchTask(
    id="T02",
    name="斐波那契",
    category="算法",
    difficulty="L1",
    prompt=(
        "请编写一个计算斐波那契数列第 n 项的 Python 函数（F(1)=1, F(2)=1），"
        "在沙箱中运行它计算 F(20)，并把结果（单个整数）写入 /workspace/fib.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/fib.txt').read_text().strip()\n"
        "ok = content == '6765'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T03 = BatchTask(
    id="T03",
    name="素数筛",
    category="算法",
    difficulty="L2",
    prompt=(
        "请用埃拉托斯特尼筛法计算 100 以内（含 100）的素数个数，"
        "把个数（单个整数）写入 /workspace/prime_count.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/prime_count.txt').read_text().strip()\n"
        "ok = content == '25'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T04 = BatchTask(
    id="T04",
    name="词频统计",
    category="算法",
    difficulty="L2",
    prompt=(
        "请统计以下文本中各单词的出现次数（忽略大小写，按空白分词）：\n"
        "'the quick brown fox jumps over the lazy dog the fox'\n"
        "把出现次数最多的单词及其次数按 '单词:次数' 格式写入 /workspace/top_word.txt"
        "（如有并列取字典序最小者）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/top_word.txt').read_text().strip()\n"
        "ok = content == 'the:3'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T05 = BatchTask(
    id="T05",
    name="爬楼梯 DP",
    category="算法",
    difficulty="L3",
    prompt=(
        "爬楼梯问题：每次可以爬 1 级或 2 级台阶，爬到第 n 级共有多少种不同方法？"
        "请用动态规划求解 n=15 的情况，在沙箱中验证后把方法数（单个整数）"
        "写入 /workspace/climb.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/climb.txt').read_text().strip()\n"
        "ok = content == '987'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 文件处理（5）
# ---------------------------------------------------------------------------

T06 = BatchTask(
    id="T06",
    name="CSV 创建与读回",
    category="文件处理",
    difficulty="L1",
    prompt=(
        "请用 file_write 创建 /workspace/users.csv，内容为表头 name,age 加 3 行数据：\n"
        "alice,30\nbob,25\ncarol,35\n"
        "然后用 file_read 读回确认内容正确。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/users.csv').read_text().strip().splitlines()\n"
        "ok = lines == ['name,age', 'alice,30', 'bob,25', 'carol,35']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T07 = BatchTask(
    id="T07",
    name="合并去重排序",
    category="文件处理",
    difficulty="L2",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/a.txt，每行一个整数：5, 2, 8, 2；\n"
        "2) 创建 /workspace/b.txt，每行一个整数：9, 5, 1；\n"
        "3) 用 sandbox_exec 把两个文件的整数合并、去重、升序排序后写入 "
        "/workspace/merged.txt（每行一个整数）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/merged.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['1', '2', '5', '8', '9']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T08 = BatchTask(
    id="T08",
    name="CSV 转 JSON",
    category="文件处理",
    difficulty="L2",
    prompt=(
        "请创建 /workspace/scores.csv，内容为：\n"
        "name,score\nalice,88\nbob,92\n"
        "然后用 sandbox_exec 读取它并生成 /workspace/scores.json，"
        "格式为对象列表，每个对象含 name（字符串）和 score（整数）两个字段。"
    ),
    verify_script=(
        "import json\n"
        "from pathlib import Path\n"
        "data = json.loads(Path('/workspace/scores.json').read_text())\n"
        "ok = data == [{'name': 'alice', 'score': 88}, {'name': 'bob', 'score': 92}]\n"
        "print('PASS' if ok else f'FAIL: {data!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T09 = BatchTask(
    id="T09",
    name="批量行生成与统计",
    category="文件处理",
    difficulty="L2",
    prompt=(
        "请用 sandbox_exec 生成 /workspace/numbers.txt，内容为 1 到 1000 的整数"
        "（每行一个），然后把该文件的总行数（单个整数）写入 /workspace/line_count.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "nums = Path('/workspace/numbers.txt').read_text().strip().splitlines()\n"
        "count = Path('/workspace/line_count.txt').read_text().strip()\n"
        "ok = len(nums) == 1000 and nums[0] == '1' and nums[-1] == '1000' and count == '1000'\n"
        "print('PASS' if ok else f'FAIL: lines={len(nums)} count={count!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T10 = BatchTask(
    id="T10",
    name="配置编辑链",
    category="文件处理",
    difficulty="L3",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/app.conf，内容为三行：\n"
        "host=localhost\nport=8080\ndebug=true\n"
        "2) 用 file_edit 把 port 改为 9090；\n"
        "3) 用 file_edit 把 debug 改为 false；\n"
        "4) 用 file_read 读回最终内容确认。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = sorted(Path('/workspace/app.conf').read_text().strip().splitlines())\n"
        "ok = lines == ['debug=false', 'host=localhost', 'port=9090']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 数据分析（3）
# ---------------------------------------------------------------------------

T11 = BatchTask(
    id="T11",
    name="均值与最大值",
    category="数据分析",
    difficulty="L2",
    prompt=(
        "请创建 /workspace/data.csv，内容为 10 个整数（每行一个）：\n"
        "12, 7, 19, 3, 15, 8, 21, 6, 11, 9\n"
        "然后用 sandbox_exec 计算均值（保留两位小数）和最大值，"
        "按 'mean:11.10\\nmax:21' 格式写入 /workspace/stats.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/stats.txt').read_text().strip()\n"
        "ok = content == 'mean:11.10\\nmax:21'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T12 = BatchTask(
    id="T12",
    name="分组求和",
    category="数据分析",
    difficulty="L2",
    prompt=(
        "请创建 /workspace/sales.csv，内容为：\n"
        "category,amount\nfruit,10\nveg,20\nfruit,15\nveg,5\nfruit,7\n"
        "然后用 sandbox_exec 按 category 汇总 amount，"
        "把结果按 'fruit:32\\nveg:25' 格式（每行一组，按类别名升序）"
        "写入 /workspace/summary.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/summary.txt').read_text().strip()\n"
        "ok = content == 'fruit:32\\nveg:25'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T13 = BatchTask(
    id="T13",
    name="中位数与标准差",
    category="数据分析",
    difficulty="L3",
    prompt=(
        "请仅用 Python 标准库（不依赖 numpy）计算数据 [4, 8, 15, 16, 23, 42] "
        "的中位数和总体标准差（population std，保留两位小数），"
        "按 'median:15.50\\nstd:12.32' 格式写入 /workspace/moments.txt。"
        "请在沙箱中实际运行验证。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/moments.txt').read_text().strip()\n"
        "try:\n"
        "    kv = dict(line.split(':', 1) for line in content.splitlines())\n"
        "    med = float(kv['median'])\n"
        "    std = float(kv['std'])\n"
        "except Exception:\n"
        "    print(f'FAIL: {content!r}')\n"
        "    raise SystemExit(1)\n"
        "ok = abs(med - 15.5) < 1e-9 and abs(std - 12.3153) < 0.01\n"
        "print('PASS' if ok else f'FAIL: median={med} std={std}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 多步链路（3）
# ---------------------------------------------------------------------------

T14 = BatchTask(
    id="T14",
    name="代码-运行-报告链",
    category="多步链路",
    difficulty="L3",
    prompt=(
        "请完成以下链路：1) 用 file_write 把一段计算 1 到 100 累加和的 Python 脚本"
        "写入 /workspace/sum_script.py；2) 用 sandbox_exec 运行它，"
        "把输出（单个整数）保存到 /workspace/sum_result.txt；\n"
        "3) 把 '/workspace/sum_script.py 运行成功' 写入 /workspace/run_log.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "r = Path('/workspace/sum_result.txt').read_text().strip()\n"
        "log = Path('/workspace/run_log.txt').read_text()\n"
        "ok = r == '5050' and '运行成功' in log\n"
        "print('PASS' if ok else f'FAIL: result={r!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T15 = BatchTask(
    id="T15",
    name="文本柱状图",
    category="多步链路",
    difficulty="L3",
    prompt=(
        "请完成以下链路：1) 创建 /workspace/votes.csv，内容为：\n"
        "option,votes\nA,3\nB,7\nC,5\n"
        "2) 用 sandbox_exec 读取数据并生成文本柱状图写入 /workspace/chart.txt，"
        "格式为每行 '选项:星号'（星号数量等于票数），例如 'A:***'。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/chart.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['A:***', 'B:*******', 'C:*****']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T16 = BatchTask(
    id="T16",
    name="模块+自测修复",
    category="多步链路",
    difficulty="L2",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/calc.py，实现函数 add(a, b) 和 "
        "divide(a, b)（divide 在除数为 0 时抛出 ValueError）；\n"
        "2) 创建 /workspace/test_calc.py，对两个函数各写至少一个断言并运行；\n"
        "3) 若测试失败请修复后重跑，最终把测试运行结果（PASS 或 OK 字样）"
        "写入 /workspace/test_outcome.txt。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "from calc import add, divide\n"
        "ok = add(2, 3) == 5\n"
        "try:\n"
        "    divide(1, 0)\n"
        "    ok = False\n"
        "except ValueError:\n"
        "    pass\n"
        "outcome = Path('/workspace/test_outcome.txt').read_text()\n"
        "ok = ok and ('PASS' in outcome or 'OK' in outcome)\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 开放报告（4，LLM-judge）
# ---------------------------------------------------------------------------

T17 = BatchTask(
    id="T17",
    name="销售分析报告",
    category="开放报告",
    difficulty="L2",
    prompt=(
        "请创建 /workspace/sales.csv，内容为：\n"
        "month,amount\n1,120\n2,95\n3,140\n4,160\n5,130\n6,175\n"
        "然后分析数据并把一份简短分析报告写入 /workspace/report.md，"
        "包含数据摘要和趋势观察。最后把报告内容读给我。"
    ),
    judge_rubric=(
        "报告须满足：1) 有明确标题；2) 包含正确的数据摘要（总量 820 或均值约 136.7 "
        "或最高 6 月 175，至少两项且数字正确）；3) 至少一条合理的趋势/波动观察；"
        "4) 结构清晰（分段或列表）。5 分=全部满足且数字精确；4 分=全部满足仅个别数字"
        "舍入差异；3 分=缺一项；≤2 分=缺两项以上或数字明显错误。"
    ),
    artifact_path="/workspace/report.md",
)

T18 = BatchTask(
    id="T18",
    name="函数文档",
    category="开放报告",
    difficulty="L1",
    prompt=(
        "请创建一个 Python 文件 /workspace/password_utils.py，实现函数 "
        "is_strong_password(s)：长度≥8 且同时含字母和数字则返回 True。"
        "然后为它写一份说明文档 /workspace/README.md，包含用途、参数、返回值"
        "和使用示例。"
    ),
    judge_rubric=(
        "文档须满足：1) 函数用途说明准确；2) 参数说明（类型与含义）；3) 返回值说明"
        "（何时 True/False，规则描述与实现一致：长度≥8 且含字母和数字）；"
        "4) 至少一个可运行的使用示例。5 分=四项齐全且规则描述精确；4 分=齐全但不精确；"
        "3 分=缺一项；≤2 分=缺两项以上。"
    ),
    artifact_path="/workspace/README.md",
)

T19 = BatchTask(
    id="T19",
    name="代码审查",
    category="开放报告",
    difficulty="L3",
    prompt=(
        "以下 Python 代码存在问题，请审查并把审查意见写入 /workspace/review.md：\n"
        "def average(nums):\n"
        "    total = 0\n"
        "    for n in nums:\n"
        "        total = total + n\n"
        "        return total / len(nums)\n"
        "data = [1, 2, 3]\n"
        "print(average(data))\n"
        "print(average([]))\n"
        "要求：指出问题、说明后果、给出修复建议。最后把审查意见读给我。"
    ),
    judge_rubric=(
        "审查须指出至少两个真实问题：1) return 缩进错误（在循环内，只累加首元素即返回，"
        "average([1,2,3]) 得到 0.33 而非 2）；2) 空列表输入行为未定义（当前静默返回 None；"
        "若只修复缩进不做空值处理，将触发 ZeroDivisionError）。加分项：修复建议正确"
        "（return 移出循环 + 空输入处理）。5 分=两问题全中且修复建议正确；"
        "4 分=两问题全中建议不完整；3 分=只指出一个；≤2 分=未指出实质问题或指出错误问题。"
    ),
    artifact_path="/workspace/review.md",
)

T20 = BatchTask(
    id="T20",
    name="沙箱方案对比",
    category="开放报告",
    difficulty="L2",
    prompt=(
        "请写一份简短的技术对比文档 /workspace/sandbox_compare.md，"
        "对比 Docker 容器与 subprocess 子进程两种代码沙箱方案的优劣，"
        "并给出选型建议。可以结合本项目（双沙箱后端）的实际场景。"
    ),
    judge_rubric=(
        "文档须满足：1) 至少 3 个对比维度（如隔离强度、启动开销、资源占用、"
        "平台兼容性、安全性）；2) 每个维度两方均有具体说明而非空泛评价；"
        "3) 有明确的选型建议且与权衡一致（如可信/演示场景用 subprocess，"
        "不可信代码用 Docker）。5 分=三项全满足；4 分=维度足够但建议模糊；"
        "3 分=维度不足或一方说明空泛；≤2 分=严重偏颇或事实错误。"
    ),
    artifact_path="/workspace/sandbox_compare.md",
)

BATCH_TASKS: list[BatchTask] = [
    T01, T02, T03, T04, T05,
    T06, T07, T08, T09, T10,
    T11, T12, T13,
    T14, T15, T16,
    T17, T18, T19, T20,
]
