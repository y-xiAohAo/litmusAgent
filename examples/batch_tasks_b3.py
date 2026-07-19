"""批量 E2E 评测任务集 Batch 3（T41-T60，20 个开放式任务）。

与 b1/b2 的核心差异：
  - prompt 只描述目标产物与验收标准，**零步骤枚举**——恢复 planner 的
    测量条件（Batch 2 根因：显式分步 prompt 抵消了 planner 价值）。
  - 8 个任务带 expected_tools 工具路径断言——产物对但没用指定工具也算
    FAIL（Batch 2 根因：产物断言吞掉 S4 式"跳过 file_edit"失败）。
  - 判分：18 断言 + 2 LLM-judge；断言脚本仅标准库。

自审记录：T53 字符串比较陷阱（'2.0.0-beta' > '2.0.0'）、T54 已破并列、
T49 全字母计数已核对（26 字母各现次数）、T58 禁 eval 且验证源码。
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
# file_edit 专项（6，工具路径断言：必须用 file_edit 完成修改）
# ---------------------------------------------------------------------------

T41 = BatchTask(
    id="T41",
    name="报告改标题（S4 开放版）",
    category="file_edit 专项",
    difficulty="L4",
    prompt=(
        "基于以下月度销售数据：2026-01 100、2026-02 150、2026-03 120、2026-04 180，"
        "在 /workspace/report.md 生成一份分析报告：标题为 '月度报告'，正文须包含"
        "四个月的总额。完成后把报告标题改成 '月度经营分析报告'（其余内容保持不变），"
        "并读回最终报告确认。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "r = Path('/workspace/report.md').read_text()\n"
        "ok = '月度经营分析报告' in r and '550' in r\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
    expected_tools=["file_edit"],
)

T42 = BatchTask(
    id="T42",
    name="配置项最小修改",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "请在 /workspace/app.conf 建立如下配置：host=localhost、port=8080、"
        "debug=true（每行一项）。随后把 port 改为 9090、debug 改为 false，"
        "其余配置行保持不变。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = sorted(Path('/workspace/app.conf').read_text().strip().splitlines())\n"
        "ok = lines == ['debug=false', 'host=localhost', 'port=9090']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
    expected_tools=["file_edit"],
)

T43 = BatchTask(
    id="T43",
    name="跨文件改名（开放版）",
    category="file_edit 专项",
    difficulty="L4",
    prompt=(
        "在 /workspace 写一个小项目：utils.py 提供函数 triple(x)（返回 x 的 3 倍），"
        "main.py 导入它并打印 triple(7) 的结果。随后把函数改名为 triple_value"
        "（两个文件保持一致），并运行确认输出正确。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "u = Path('/workspace/utils.py').read_text()\n"
        "m = Path('/workspace/main.py').read_text()\n"
        "ok = 'def triple_value' in u and 'triple(' not in u.replace('triple_value(', '')\n"
        "ok = ok and 'triple_value' in m\n"
        "from utils import triple_value\n"
        "ok = ok and triple_value(7) == 21\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
    expected_tools=["file_edit"],
)

T44 = BatchTask(
    id="T44",
    name="定点插入行",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "在 /workspace/notes.txt 写入三行：'第一行'、'第二行'、'第四行'。"
        "随后在 '第二行' 之后插入一行 '第三行'，其余内容保持不变。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/notes.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['第一行', '第二行', '第三行', '第四行']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
    expected_tools=["file_edit"],
)

T45 = BatchTask(
    id="T45",
    name="注释修正",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "创建 /workspace/calc.py：实现函数 add(a, b) 返回两数之和，"
        "函数上方写一行注释 '# 返回两数之差'。随后把注释修正为 '# 返回两数之和'"
        "（函数代码不变），并验证函数仍正常。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "src = Path('/workspace/calc.py').read_text()\n"
        "ok = '# 返回两数之和' in src and '# 返回两数之差' not in src\n"
        "from calc import add\n"
        "ok = ok and add(1, 2) == 3\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
    expected_tools=["file_edit"],
)

T46 = BatchTask(
    id="T46",
    name="变量全文件改名",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "创建 /workspace/scoring.py：变量 base_score = 100，再写两个函数，"
        "分别返回 base_score * 2 和 base_score + 50。随后把变量改名为 base_points"
        "（全文件所有引用同步改名），运行验证两个函数仍正确。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "src = Path('/workspace/scoring.py').read_text()\n"
        "ok = 'base_points' in src and 'base_score' not in src\n"
        "import scoring\n"
        "ok = ok and scoring.base_points == 100\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
    expected_tools=["file_edit"],
)

# ---------------------------------------------------------------------------
# 多目标开放任务（5，planner 考场：一句话多个交付物）
# ---------------------------------------------------------------------------

T47 = BatchTask(
    id="T47",
    name="气温数据整理",
    category="多目标开放",
    difficulty="L4",
    prompt=(
        "以下原始气温记录（注意含一条缺失温度的记录和一条完全重复的记录）：\n"
        "city,temp\nbeijing,32\nshanghai,\nshanghai,30\nbeijing,35\nguangzhou,28\n"
        "请把它们整理成干净的数据集（剔除缺失和重复），算出每个城市的平均气温"
        "（保留一位小数），把结果写入 /workspace/agg.txt"
        "（每行 'city:avg'，按城市名升序），并告诉我哪个城市最热。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "agg = Path('/workspace/agg.txt').read_text().strip().splitlines()\n"
        "ok = agg == ['beijing:33.5', 'guangzhou:28.0', 'shanghai:30.0']\n"
        "print('PASS' if ok else f'FAIL: {agg!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

T48 = BatchTask(
    id="T48",
    name="密码校验+自测",
    category="多目标开放",
    difficulty="L3",
    prompt=(
        "实现函数 is_strong_password(s)：密码长度≥8 且同时含字母和数字时返回 True，"
        "否则返回 False。保存到 /workspace/password_utils.py，为它配一套自测并跑通，"
        "最后把测试结果记录到 /workspace/test_outcome.txt。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "from password_utils import is_strong_password\n"
        "ok = is_strong_password('abc12345') is True\n"
        "ok = ok and is_strong_password('short') is False\n"
        "ok = ok and is_strong_password('12345678') is False\n"
        "ok = ok and is_strong_password('abcdefgh') is False\n"
        "outcome = Path('/workspace/test_outcome.txt').read_text()\n"
        "ok = ok and ('PASS' in outcome or 'OK' in outcome)\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T49 = BatchTask(
    id="T49",
    name="字母频率统计+条形图",
    category="多目标开放",
    difficulty="L4",
    prompt=(
        "统计这句话里每个字母的出现次数（只计字母，忽略空格）："
        "'the quick brown fox jumps over the lazy dog'。"
        "需要两个产物：按字母升序的统计文件 /workspace/counts.txt"
        "（每行 '字母:次数'），和文本条形图 /workspace/chart.txt"
        "（每行 '字母:星号'，星号数量等于次数）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/counts.txt').read_text().strip().splitlines()\n"
        "expect = ['a:1','b:1','c:1','d:1','e:3','f:1','g:1','h:2','i:1',"
        "'j:1','k:1','l:1','m:1','n:1','o:4','p:1','q:1','r:2',"
        "'s:1','t:2','u:2','v:1','w:1','x:1','y:1','z:1']\n"
        "ok = lines == expect\n"
        "chart = Path('/workspace/chart.txt').read_text()\n"
        "ok = ok and 'e:***' in chart and 'o:****' in chart\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

T50 = BatchTask(
    id="T50",
    name="完全平方数",
    category="多目标开放",
    difficulty="L3",
    prompt=(
        "1 到 100（含）之间的完全平方数有哪些？把它们存成数据文件 "
        "/workspace/squares.txt（每行一个），再算出它们的总和与个数分别存入 "
        "/workspace/sum.txt 和 /workspace/count.txt，并告诉我答案。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "nums = Path('/workspace/squares.txt').read_text().strip().splitlines()\n"
        "s = Path('/workspace/sum.txt').read_text().strip()\n"
        "c = Path('/workspace/count.txt').read_text().strip()\n"
        "expect = ['1','4','9','16','25','36','49','64','81','100']\n"
        "ok = nums == expect and s == '385' and c == '10'\n"
        "print('PASS' if ok else f'FAIL: {nums!r} {s!r} {c!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T51 = BatchTask(
    id="T51",
    name="温度转换一致性",
    category="多目标开放",
    difficulty="L3",
    prompt=(
        "在 /workspace/converter.py 实现函数 c_to_f(c)：把摄氏温度转为华氏温度。"
        "用它把 0、100、37 三个摄氏温度转换一遍，结果整理成表格文件 "
        "/workspace/table.txt（每行 '摄氏:华氏'，华氏保留一位小数），"
        "确保表格与函数实现一致。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "from converter import c_to_f\n"
        "ok = abs(c_to_f(0) - 32.0) < 1e-9 and abs(c_to_f(37) - 98.6) < 1e-9\n"
        "lines = Path('/workspace/table.txt').read_text().strip().splitlines()\n"
        "ok = ok and lines == ['0:32.0', '100:212.0', '37:98.6']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

# ---------------------------------------------------------------------------
# 陷阱数据开放版（5）
# ---------------------------------------------------------------------------

T52 = BatchTask(
    id="T52",
    name="坏行 JSONL（开放版）",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/events.jsonl，内容如下（其中混了两行坏数据）：\n"
        '{"type": "click", "value": 5}\n'
        "not a json\n"
        '{"type": "view", "value": 3}\n'
        '{"type": "click", "value": 7}\n'
        '{"broken": \n'
        '{"type": "view", "value": 2}\n'
        "统计所有合法记录里各 type 的 value 总和，写入 /workspace/events.txt"
        "（每行 'type:total'，按 type 升序）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/events.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['click:12', 'view:5']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T53 = BatchTask(
    id="T53",
    name="最高版本号",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "以下版本号里找出语义上最高的一个：1.9.0、1.10.0、1.0.1、2.0.0-beta、2.0.0。"
        "把结果（单个版本号）写入 /workspace/highest.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/highest.txt').read_text().strip()\n"
        "ok = content == '2.0.0'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T54 = BatchTask(
    id="T54",
    name="最活跃 IP",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/access.log，内容如下：\n"
        "192.168.1.1 GET /a\n10.0.0.2 GET /b\n192.168.1.1 GET /c\n"
        "10.0.0.2 GET /a\n192.168.1.1 GET /d\n10.0.0.3 GET /e\n"
        "10.0.0.2 GET /f\n192.168.1.1 GET /g\n"
        "找出请求次数最多的 IP，把它的地址和次数写入 /workspace/top.txt"
        "（格式 'IP:count'）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/top.txt').read_text().strip()\n"
        "ok = content == '192.168.1.1:4'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T55 = BatchTask(
    id="T55",
    name="混合分隔符（开放版）",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "这些成绩记录的分隔符不统一（分号和逗号混用）：\n"
        "alice;30\nbob,25\ncarol;35\ndave,40\n"
        "存入 /workspace/mixed.txt 后，算出平均分（保留一位小数）"
        "写入 /workspace/avg.txt（格式 'avg:32.5'）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/avg.txt').read_text().strip()\n"
        "ok = content == 'avg:32.5'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T56 = BatchTask(
    id="T56",
    name="含逗号商品名（开放版）",
    category="陷阱数据",
    difficulty="L4",
    prompt=(
        "这份订单数据的商品名里含逗号（CSV 引号转义），"
        "且其中有缺失销量的行和完全重复的行：\n"
        "id,product,amount\n"
        "1,apple,10\n"
        '2,"banana, large",20\n'
        "3,apple,\n"
        '2,"banana, large",20\n'
        "4,cherry,15\n"
        "存入 /workspace/orders.csv 后，剔除无效行，统计每个商品的总销量，"
        "写入 /workspace/clean.txt（每行 'product:total'，按商品名升序）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/clean.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['apple:10', 'banana, large:20', 'cherry:15']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 工程挑战（2）
# ---------------------------------------------------------------------------

T57 = BatchTask(
    id="T57",
    name="环形缓冲区",
    category="工程挑战",
    difficulty="L3",
    prompt=(
        "在 /workspace/ring.py 实现 RingBuffer：构造时指定固定容量，"
        "put 追加元素，写满后覆盖最旧的元素，get_all 按写入顺序返回现存元素。"
        "自行验证：容量 3，依次放入 1、2、3、4、5 后内容应为 [3, 4, 5]。"
    ),
    verify_script=(
        "import sys\n"
        "sys.path.insert(0, '/workspace')\n"
        "from ring import RingBuffer\n"
        "buf = RingBuffer(3)\n"
        "for i in [1, 2, 3, 4, 5]:\n"
        "    buf.put(i)\n"
        "ok = buf.get_all() == [3, 4, 5]\n"
        "buf2 = RingBuffer(2)\n"
        "buf2.put(1)\n"
        "ok = ok and buf2.get_all() == [1]\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T58 = BatchTask(
    id="T58",
    name="迷你表达式求值",
    category="工程挑战",
    difficulty="L4",
    prompt=(
        "在 /workspace/calc_expr.py 实现 evaluate(expr)：支持非负整数、"
        "加减法和括号，不允许使用 eval。自行验证：'2+3' 得 5、"
        "'10-2-3' 得 5、'(2+3)-(1+1)' 得 3。"
    ),
    verify_script=(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, '/workspace')\n"
        "src = Path('/workspace/calc_expr.py').read_text()\n"
        "ok = 'eval(' not in src\n"
        "from calc_expr import evaluate\n"
        "ok = ok and evaluate('2+3') == 5\n"
        "ok = ok and evaluate('10-2-3') == 5\n"
        "ok = ok and evaluate('(2+3)-(1+1)') == 3\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 开放报告（2，LLM-judge）
# ---------------------------------------------------------------------------

T59 = BatchTask(
    id="T59",
    name="根因分析（开放版）",
    category="开放报告",
    difficulty="L3",
    prompt=(
        "应用半夜挂了，日志如下：\n"
        "10:01:05 ERROR db connection timeout\n"
        "10:01:06 WARN retry 1/3\n"
        "10:01:09 WARN retry 2/3\n"
        "10:01:15 ERROR db connection timeout\n"
        "10:01:16 ERROR service unavailable\n"
        "10:02:01 INFO db connection restored\n"
        "10:02:05 INFO service recovered\n"
        "给我一份根因分析报告，写入 /workspace/incident_report.md。"
    ),
    judge_rubric=(
        "报告须满足：1) 时间线正确（10:01:05 首发异常 → 10:02:05 恢复，"
        "持续约 60 秒）；2) 根因候选指向 db 连接超时（非 service 本身）；"
        "3) 影响范围：服务不可用约 45-60 秒；4) 至少一条具体改进建议。"
        "5 分=四项全对且时间推算精确；4 分=四项全对但时间模糊；"
        "3 分=缺一项；≤2 分=根因判断错误或缺两项以上。"
    ),
    artifact_path="/workspace/incident_report.md",
)

T60 = BatchTask(
    id="T60",
    name="缓存选型评审",
    category="开放报告",
    difficulty="L4",
    prompt=(
        "团队要为一个日活 10 万的 API 加缓存，候选方案 A：本地内存缓存；"
        "方案 B：Redis。写一份选型建议到 /workspace/cache_decision.md，"
        "并读给我听。"
    ),
    judge_rubric=(
        "文档须满足：1) 有明确的选型推荐（或明确的适用边界划分）；"
        "2) 至少 3 个对比维度（如数据一致性、容量上限、可用性/单点、"
        "运维成本、多实例共享）；3) 结论场景化而非绝对化"
        "（如区分单机/多实例部署）；4) 结构清晰。"
        "5 分=四项全满足；4 分=维度足够但结论略绝对；"
        "3 分=缺一项；≤2 分=无论证或事实错误。"
    ),
    artifact_path="/workspace/cache_decision.md",
)

BATCH3_TASKS: list[BatchTask] = [
    T41, T42, T43, T44, T45, T46,
    T47, T48, T49, T50, T51,
    T52, T53, T54, T55, T56,
    T57, T58,
    T59, T60,
]
