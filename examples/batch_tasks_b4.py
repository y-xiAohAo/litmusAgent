"""批量 E2E 评测任务集 Batch 4（T61-T80，20 个 L5 任务）。

难度设计（针对 b3 结论：开放任务仍不够难）：
  - 长链路 ×10：上步产物是下步输入，断链即失败；埋中途约束变化迫使 replan。
  - 错误注入 ×10：自然地雷（禁网缺库 / 预埋语法错误 / nobody 写 /etc 权限 /
    不可行约束 / 脏中间产物），恢复成功即 PASS（与自愈叙事一致）。
  - 判分：18 断言 + 2 LLM-judge；T67/T69 带 file_edit 工具路径断言。

自审记录：T61 聚合与占比已核对（30/30/20、37.5/37.5/25.0）；T64 避免舍入
歧义（10/15/20 → 15.0 → 60.0）；T68 中位数 5.5、diff 0.20 已核对；
T71 与 T13 同口径容差校验；T76 空组 N/A 显式约定。
"""

from __future__ import annotations

try:
    from batch_tasks import BatchTask
except ImportError:  # 测试以 runpy 动态加载时，脚本目录不在 sys.path
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from batch_tasks import BatchTask

# ---------------------------------------------------------------------------
# 长链路（10）：上步产物是下步输入
# ---------------------------------------------------------------------------

T61 = BatchTask(
    id="T61",
    name="六步数据管道",
    category="长链路",
    difficulty="L5",
    prompt=(
        "用以下 8 行销售数据做一条完整处理管道：\n"
        "cat,amt\na,10\nb,20\na,15\nb,\nc,5\na,5\nb,10\nc,15\n"
        "要求：原始数据存为 /workspace/raw.csv；清洗（去缺失、去完全重复行）后存 "
        "/workspace/clean.csv；按类别聚合写入 /workspace/agg.txt（每行 'cat:total'，"
        "升序）；计算每类占比写入 /workspace/pct.txt（每行 'cat:pct'，一位小数）；"
        "最后把数据结论写入 /workspace/conclusion.txt（须含总额）。"
        "每一步产物必须能被下一步直接使用。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "agg = Path('/workspace/agg.txt').read_text().strip().splitlines()\n"
        "pct = Path('/workspace/pct.txt').read_text().strip().splitlines()\n"
        "concl = Path('/workspace/conclusion.txt').read_text()\n"
        "ok = agg == ['a:30', 'b:30', 'c:20']\n"
        "ok = ok and pct == ['a:37.5', 'b:37.5', 'c:25.0']\n"
        "ok = ok and '80' in concl\n"
        "print('PASS' if ok else f'FAIL: {agg!r} {pct!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=18,
)

T62 = BatchTask(
    id="T62",
    name="中途格式变化",
    category="长链路",
    difficulty="L5",
    prompt=(
        "处理订单数据 x,1 / y,2 / x,3（存入 /workspace/orders.csv）。\n"
        "约定：聚合结果写入 /workspace/agg.txt，格式为 'category=total'（每行一条，"
        "按 category 升序）。注意：生成图表这一步时，读取 agg.txt 的数据但输出格式"
        "改为 'category | total | bar'（bar 为与 total 等长的星号），"
        "写入 /workspace/chart.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "agg = Path('/workspace/agg.txt').read_text().strip().splitlines()\n"
        "chart = Path('/workspace/chart.txt').read_text().strip().splitlines()\n"
        "ok = agg == ['x=4', 'y=2']\n"
        "ok = ok and chart == ['x | 4 | ****', 'y | 2 | **']\n"
        "print('PASS' if ok else f'FAIL: {agg!r} {chart!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

T63 = BatchTask(
    id="T63",
    name="跨文件导入链",
    category="长链路",
    difficulty="L5",
    prompt=(
        "构建一个小项目：/workspace/core.py 提供 normalize(text)（去除首尾空格、"
        "转小写）；/workspace/analyzer.py 导入 core 并统计规范化后的单词数；"
        "/workspace/main.py 导入 analyzer，处理文本 '  The Quick BROWN fox  '。"
        "运行 main，把输出（单词数）写入 /workspace/result.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/result.txt').read_text().strip()\n"
        "ok = content == '4'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

T64 = BatchTask(
    id="T64",
    name="数字接力",
    category="长链路",
    difficulty="L5",
    prompt=(
        "完成三步数值接力：把 10、15、20 三个数写入 /workspace/step1.txt"
        "（每行一个）；读取 step1 算出平均值（保留一位小数）写入 /workspace/step2.txt；"
        "读取 step2 的数值，乘以 4 后（保留一位小数）写入 /workspace/step3.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "s2 = Path('/workspace/step2.txt').read_text().strip()\n"
        "s3 = Path('/workspace/step3.txt').read_text().strip()\n"
        "ok = s2 == '15.0' and s3 == '60.0'\n"
        "print('PASS' if ok else f'FAIL: {s2!r} {s3!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T65 = BatchTask(
    id="T65",
    name="配置驱动计算",
    category="长链路",
    difficulty="L5",
    prompt=(
        "先创建 /workspace/config.txt，内容为：\n"
        "multiplier=3\nvalues=2,4,6\n"
        "然后写脚本读取该配置，把 values 中每个值乘以 multiplier，"
        "结果（每行一个）写入 /workspace/out.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/out.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['6', '12', '18']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T66 = BatchTask(
    id="T66",
    name="日志过滤管道",
    category="长链路",
    difficulty="L5",
    prompt=(
        "创建 /workspace/app.log，内容如下：\n"
        "10.0.0.1 INFO start\n10.0.0.2 WARN disk\n10.0.0.1 INFO ping\n"
        "10.0.0.2 WARN disk\n10.0.0.3 WARN mem\n10.0.0.2 INFO ok\n"
        "10.0.0.2 WARN disk\n10.0.0.3 WARN mem\n10.0.0.1 INFO stop\n10.0.0.3 INFO ok\n"
        "从中过滤出 WARN 级别行，统计每个 IP 的 WARN 次数，"
        "把次数最多的 IP 及次数写入 /workspace/top_warn.txt（格式 'IP:count'）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/top_warn.txt').read_text().strip()\n"
        "ok = content == '10.0.0.2:3'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T67 = BatchTask(
    id="T67",
    name="三文件链式改名",
    category="长链路",
    difficulty="L5",
    prompt=(
        "项目有三个文件：/workspace/api.py（定义函数 getData，返回 42）、"
        "/workspace/caller.py（导入并两次调用 getData）、/workspace/notes.md"
        "（文字说明里提到 getData）。请创建它们，然后把函数改名为 fetch_data——"
        "三个文件全部同步（包括 notes.md 中的文字）。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "a = Path('/workspace/api.py').read_text()\n"
        "c = Path('/workspace/caller.py').read_text()\n"
        "n = Path('/workspace/notes.md').read_text()\n"
        "ok = 'fetch_data' in a and 'getData' not in a\n"
        "ok = ok and 'fetch_data' in c and 'getData' not in c\n"
        "ok = ok and 'fetch_data' in n and 'getData' not in n\n"
        "from api import fetch_data\n"
        "ok = ok and fetch_data() == 42\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
    expected_tools=["file_edit"],
)

T68 = BatchTask(
    id="T68",
    name="多阶段校验链",
    category="长链路",
    difficulty="L5",
    prompt=(
        "给定 20 个数：3,7,1,9,4,6,8,2,5,10,3,6,9,1,7,4,8,2,5,6。"
        "把它们存入 /workspace/data.txt（每行一个）；计算均值（一位小数）写入 "
        "/workspace/mean.txt；计算中位数（一位小数）写入 /workspace/median.txt；"
        "最后把均值与中位数之差的绝对值（两位小数）写入 /workspace/diff.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "m1 = Path('/workspace/mean.txt').read_text().strip()\n"
        "m2 = Path('/workspace/median.txt').read_text().strip()\n"
        "d = Path('/workspace/diff.txt').read_text().strip()\n"
        "ok = m1 == '5.3' and m2 == '5.5' and d == '0.20'\n"
        "print('PASS' if ok else f'FAIL: {m1!r} {m2!r} {d!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

T69 = BatchTask(
    id="T69",
    name="报告链+编辑",
    category="长链路",
    difficulty="L5",
    prompt=(
        "用数据 q1,100 / q2,200（存入 /workspace/q.csv）生成一份分析报告到 "
        "/workspace/report.md：标题为 '分析'，正文含总额。随后把标题改为 '季度分析'，"
        "并在报告末尾追加一行 '完'。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "r = Path('/workspace/report.md').read_text()\n"
        "lines = r.strip().splitlines()\n"
        "ok = '季度分析' in r and '300' in r and lines[-1].strip() == '完'\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
    expected_tools=["file_edit"],
)

T70 = BatchTask(
    id="T70",
    name="管道+结论报告",
    category="长链路",
    difficulty="L5",
    prompt=(
        "以下 6 行实验数据：group,score\nalpha,80\nbeta,90\nalpha,70\nbeta,60\nalpha,90\n"
        "走完整管道：存入 CSV → 按组聚合平均分 → 基于聚合结果写一段分析报告到 "
        "/workspace/analysis_report.md（须说明哪组更强及差距）。"
    ),
    judge_rubric=(
        "报告须满足：1) 聚合数字正确（alpha 平均 80、beta 平均 75，或出现对应的"
        "三个原始分）；2) 结论正确（alpha 更强，差距 5 分）；3) 有数据依据而非空话。"
        "5 分=三项全对；4 分=数字对但结论模糊；3 分=数字错但结论方向对；≤2 分=方向错。"
    ),
    artifact_path="/workspace/analysis_report.md",
    max_turns=16,
)

# ---------------------------------------------------------------------------
# 错误注入（10）：自然地雷，恢复成功即 PASS
# ---------------------------------------------------------------------------

T71 = BatchTask(
    id="T71",
    name="缺库自愈（numpy）",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "请用 numpy 计算数据 [4, 8, 15, 16, 23, 42] 的均值和总体标准差"
        "（保留两位小数），写入 /workspace/stats.txt（格式 'mean:18.00\\nstd:12.32'）。"
        "如果环境不满足，自行想办法完成并验证。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/stats.txt').read_text().strip()\n"
        "try:\n"
        "    kv = dict(line.split(':', 1) for line in content.splitlines())\n"
        "    mean = float(kv['mean'])\n"
        "    std = float(kv['std'])\n"
        "except Exception:\n"
        "    print(f'FAIL: {content!r}')\n"
        "    raise SystemExit(1)\n"
        "ok = abs(mean - 18.0) < 1e-9 and abs(std - 12.3153) < 0.01\n"
        "print('PASS' if ok else f'FAIL: mean={mean} std={std}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T72 = BatchTask(
    id="T72",
    name="预埋语法错误",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "把以下代码写入 /workspace/broken.py 并运行：\n"
        "def double(x)\n"
        "    return x * 2\n"
        "print(double(21)\n"
        "观察报错，修复全部问题后重跑，把最终输出写入 /workspace/out.txt。"
    ),
    verify_script=(
        "import ast\n"
        "from pathlib import Path\n"
        "ast.parse(Path('/workspace/broken.py').read_text())\n"
        "content = Path('/workspace/out.txt').read_text().strip()\n"
        "ok = content == '42'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T73 = BatchTask(
    id="T73",
    name="etc 权限拒绝",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "请把配置内容 'mode=production' 写入 /etc/app.conf。"
        "如果环境不允许，写入 /workspace/app.conf 作为替代并说明原因。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/app.conf').read_text()\n"
        "ok = 'mode=production' in content\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=12,
)

T74 = BatchTask(
    id="T74",
    name="pandas 不可行约束",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "请用 pandas 读取以下数据并计算 price 总额：\n"
        "item,price\na,10\nb,20\nc,15\n"
        "（先存入 /workspace/goods.csv。）把总额写入 /workspace/total.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/total.txt').read_text().strip()\n"
        "ok = content == '45'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T75 = BatchTask(
    id="T75",
    name="坏行中间产物",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "创建 /workspace/raw.txt，内容为：\n"
        "a,1\nb,2\nbroken line\na,3\n"
        "读取它做聚合（跳过无法解析的行），把结果写入 /workspace/agg.txt"
        "（每行 'key:total'，升序）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/agg.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['a:4', 'b:2']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=12,
)

T76 = BatchTask(
    id="T76",
    name="空组除零",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "计算三组数据的均值：A 组 [10, 20]，B 组 []（空），C 组 [5]。"
        "把结果写入 /workspace/means.txt（每行 '组:均值'，保留一位小数；"
        "空组记为 N/A）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/means.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['A:15.0', 'B:N/A', 'C:5.0']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=12,
)

T77 = BatchTask(
    id="T77",
    name="千分位数字",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "把以下三个数写入 /workspace/nums.txt：1,234 / 567 / 2,001（每行一个，"
        "注意含千分位逗号）。计算它们的总和，写入 /workspace/total.txt（纯数字）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/total.txt').read_text().strip()\n"
        "ok = content == '3802'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=12,
)

T78 = BatchTask(
    id="T78",
    name="缺失父目录",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "把文本 '年度总结完成' 写入 /workspace/reports/2026/summary.txt。"
        "注意路径中的目录可能不存在，请妥善处理。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/reports/2026/summary.txt').read_text()\n"
        "ok = '年度总结完成' in content\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=12,
)

T79 = BatchTask(
    id="T79",
    name="部分失败批处理",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "依次计算以下表达式：'1+1'、'2*3'、'bad expr'、'10/2'、'2+'。"
        "把能算出的结果写入 /workspace/results.txt（每行 'expr=result'，"
        "结果取整数），无法计算的表达式跳过且不能中断处理。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/results.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['1+1=2', '2*3=6', '10/2=5']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T80 = BatchTask(
    id="T80",
    name="部署失败分析",
    category="错误注入",
    difficulty="L5",
    prompt=(
        "一次部署失败的完整日志如下：\n"
        "12:00:01 INFO deploy start\n"
        "12:00:05 INFO pulling image\n"
        "12:01:30 ERROR pull timeout\n"
        "12:01:31 WARN retry 1/2\n"
        "12:02:45 ERROR pull timeout\n"
        "12:02:46 ERROR deploy failed: image unavailable\n"
        "12:03:00 INFO rollback completed\n"
        "把故障分析写入 /workspace/deploy_analysis.md（时间线/根因/改进）。"
    ),
    judge_rubric=(
        "报告须满足：1) 时间线正确（12:00:01 开始 → 12:03:00 回滚完成，约 3 分钟）；"
        "2) 根因指向镜像拉取超时（两次 timeout 后失败，非应用代码问题）；"
        "3) 有回滚事实（rollback completed）；4) 至少一条改进建议"
        "（镜像源/预拉取/超时策略）。5 分=四项全对；4 分=缺改进或时间模糊；"
        "3 分=缺两项；≤2 分=根因错误。"
    ),
    artifact_path="/workspace/deploy_analysis.md",
    max_turns=12,
)

BATCH4_TASKS: list[BatchTask] = [
    T61, T62, T63, T64, T65, T66, T67, T68, T69, T70,
    T71, T72, T73, T74, T75, T76, T77, T78, T79, T80,
]
