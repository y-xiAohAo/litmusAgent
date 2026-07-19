"""批量 E2E 评测任务集 Batch 2（T21-T40，20 个高难任务）。

设计原则（与 b1 的差异）：
  - 判别力优先：每个任务含确定性陷阱——naive 解法必然失败，针对
    evaluation-log 已暴露的失败模式（工具一把梭 / 跳过 file_edit / 边界遗漏）。
  - 判分保持精确断言为主（18 断言 + 2 LLM-judge），断言脚本仅标准库。
  - 难度分布：L3 为主，L4（长链路/多约束）穿插；max_turns 按链路长度放宽。

陷阱自审记录（设计期）：
  - T22 引号逗号 + 重复行 + 缺失值三重陷阱；T24 并列次数按 IP 字典序；
  - T26 预埋恰好 3 个 bug；T27 LRU 更新刷新语义；T29 RLE 多位数计数。
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
# 陷阱数据（5）
# ---------------------------------------------------------------------------

T21 = BatchTask(
    id="T21",
    name="语义版本排序",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/versions.txt，每行一个版本号：\n"
        "1.9.0\n1.10.0\n1.0.1\n2.0.0\n1.9.1\n"
        "然后按语义版本号升序排序（数值比较，非字符串比较），"
        "写入 /workspace/sorted_versions.txt（每行一个）。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/sorted_versions.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['1.0.1', '1.9.0', '1.9.1', '1.10.0', '2.0.0']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T22 = BatchTask(
    id="T22",
    name="脏 CSV 清洗聚合",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/orders.csv，内容如下（注意第 3 行含引号逗号、"
        "第 4 行 amount 缺失、第 5 行与第 3 行完全重复）：\n"
        "id,product,amount\n"
        "1,apple,10\n"
        '2,"banana, large",20\n'
        "3,apple,\n"
        '2,"banana, large",20\n'
        "4,cherry,15\n"
        "任务：1) 清洗——删除 amount 缺失的行、删除完全重复的行（保留首次出现）；\n"
        "2) 按 product 汇总 amount；3) 按 product 名升序，"
        "以 'product:total' 格式（每行一组）写入 /workspace/clean.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/clean.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['apple:10', 'banana, large:20', 'cherry:15']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T23 = BatchTask(
    id="T23",
    name="混合分隔符",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/mixed.txt，内容如下（每行一条记录，"
        "但分隔符混用了分号和逗号）：\n"
        "alice;30\nbob,25\ncarol;35\ndave,40\n"
        "请统一解析全部记录，计算 score 的平均值（保留一位小数），"
        "以 'avg:32.5' 的格式写入 /workspace/avg.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/avg.txt').read_text().strip()\n"
        "ok = content == 'avg:32.5'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T24 = BatchTask(
    id="T24",
    name="日志 top-K 并列约定",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/access.log，内容如下：\n"
        "192.168.1.1 GET /a\n10.0.0.2 GET /b\n192.168.1.1 GET /c\n"
        "10.0.0.2 GET /a\n192.168.1.1 GET /d\n10.0.0.3 GET /e\n10.0.0.2 GET /f\n"
        "统计每个 IP 的请求次数，取次数最多的前 2 个，"
        "按次数降序、次数相同按 IP 字符串字典序升序，"
        "以 'IP:count' 格式（每行一条）写入 /workspace/top.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/top.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['10.0.0.2:3', '192.168.1.1:3']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T25 = BatchTask(
    id="T25",
    name="坏行 JSONL",
    category="陷阱数据",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/events.jsonl，每行一个 JSON 对象"
        "（注意第 2 行和第 5 行是损坏的，无法解析）：\n"
        '{"type": "click", "value": 5}\n'
        "not a json\n"
        '{"type": "view", "value": 3}\n'
        '{"type": "click", "value": 7}\n'
        '{"broken": \n'
        '{"type": "view", "value": 2}\n'
        "请跳过无法解析的行，按 type 汇总 value，按 type 名升序，"
        "以 'type:total' 格式（每行一条）写入 /workspace/events.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/events.txt').read_text().strip().splitlines()\n"
        "ok = lines == ['click:12', 'view:5']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# 多步工程（5）
# ---------------------------------------------------------------------------

T26 = BatchTask(
    id="T26",
    name="预埋 bug 修复",
    category="多步工程",
    difficulty="L3",
    prompt=(
        "以下代码恰好有 3 个 bug。请把它写入 /workspace/bugs.py，"
        "逐一找出并修复，然后在沙箱中验证修复结果：\n"
        "def stats(nums):\n"
        "    total = 0\n"
        "    for i in range(len(nums) + 1):\n"
        "        total += nums[i]\n"
        "    return total / len(nums)\n\n"
        "def median(nums):\n"
        "    s = sorted(nums)\n"
        "    n = len(s)\n"
        "    return s[n // 2]\n"
        "要求：stats([1,2,3]) == 2.0；stats([4]) == 4.0；空列表调用 stats 应抛出 "
        "ValueError；median([3,1,2]) == 2；median([4,1,2,3]) == 2.5。"
    ),
    verify_script=(
        "import sys\n"
        "sys.path.insert(0, '/workspace')\n"
        "from bugs import stats, median\n"
        "ok = abs(stats([1, 2, 3]) - 2.0) < 1e-9 and abs(stats([4]) - 4.0) < 1e-9\n"
        "try:\n"
        "    stats([])\n"
        "    ok = False\n"
        "except ValueError:\n"
        "    pass\n"
        "ok = ok and median([3, 1, 2]) == 2 and abs(median([4, 1, 2, 3]) - 2.5) < 1e-9\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T27 = BatchTask(
    id="T27",
    name="LRU 缓存",
    category="多步工程",
    difficulty="L4",
    prompt=(
        "请在 /workspace/lru.py 实现 LRUCache 类：\n"
        "- 构造函数接收容量 capacity；\n"
        "- get(key)：命中返回对应值并刷新为最近使用，未命中返回 -1；\n"
        "- put(key, value)：写入；key 已存在时更新值并刷新为最近使用；\n"
        "  超出容量时淘汰最久未使用的项。\n"
        "写完后在沙箱中自行验证。"
    ),
    verify_script=(
        "import sys\n"
        "sys.path.insert(0, '/workspace')\n"
        "from lru import LRUCache\n"
        "c = LRUCache(2)\n"
        "c.put(1, 1); c.put(2, 2)\n"
        "ok = c.get(1) == 1\n"
        "c.put(3, 3)\n"
        "ok = ok and c.get(2) == -1\n"
        "c.put(4, 4)\n"
        "ok = ok and c.get(1) == -1 and c.get(3) == 3 and c.get(4) == 4\n"
        "c2 = LRUCache(2)\n"
        "c2.put(1, 1); c2.put(2, 2); c2.put(1, 10); c2.put(3, 3)\n"
        "ok = ok and c2.get(1) == 10 and c2.get(2) == -1\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T28 = BatchTask(
    id="T28",
    name="闸机状态机",
    category="多步工程",
    difficulty="L3",
    prompt=(
        "请在 /workspace/fsm.py 实现 Turnstile 类（地铁闸机状态机）：\n"
        "- 初始状态 locked；\n"
        "- event('coin')：locked → unlocked；已 unlocked 时无效（保持 unlocked）；\n"
        "- event('push')：unlocked → locked；已 locked 时无效（保持 locked）；\n"
        "- state 属性返回当前状态字符串；\n"
        "- 非法事件名抛出 ValueError。\n"
        "写完后在沙箱中自行验证。"
    ),
    verify_script=(
        "import sys\n"
        "sys.path.insert(0, '/workspace')\n"
        "from fsm import Turnstile\n"
        "t = Turnstile()\n"
        "ok = t.state == 'locked'\n"
        "t.event('push')\n"
        "ok = ok and t.state == 'locked'\n"
        "t.event('coin')\n"
        "ok = ok and t.state == 'unlocked'\n"
        "t.event('coin')\n"
        "ok = ok and t.state == 'unlocked'\n"
        "t.event('push')\n"
        "ok = ok and t.state == 'locked'\n"
        "try:\n"
        "    t.event('bad')\n"
        "    ok = False\n"
        "except ValueError:\n"
        "    pass\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T29 = BatchTask(
    id="T29",
    name="RLE 编解码",
    category="多步工程",
    difficulty="L3",
    prompt=(
        "请在 /workspace/rle.py 实现游程编码：\n"
        "- encode(s)：如 'aaabcc' → 'a3b1c2'；\n"
        "- decode(s)：如 'a3b1c2' → 'aaabcc'；\n"
        "- 要求对任意只含小写字母的字符串 s，decode(encode(s)) == s。\n"
        "注意正确处理连续出现 10 次以上的情况。写完后在沙箱中自行验证。"
    ),
    verify_script=(
        "import sys\n"
        "sys.path.insert(0, '/workspace')\n"
        "from rle import encode, decode\n"
        "ok = encode('aaabcc') == 'a3b1c2'\n"
        "ok = ok and decode('a3b1c2') == 'aaabcc'\n"
        "ok = ok and encode('a') == 'a1'\n"
        "ok = ok and encode('a' * 12) == 'a12'\n"
        "ok = ok and decode('a12') == 'a' * 12\n"
        "ok = ok and decode(encode('xyz')) == 'xyz'\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

T30 = BatchTask(
    id="T30",
    name="混合类型迭代修复",
    category="多步工程",
    difficulty="L3",
    prompt=(
        "请把以下代码写入 /workspace/broken.py：\n"
        "def compute():\n"
        "    data = [1, 2, 'three', 4]\n"
        "    return sum(data)\n"
        "print(compute())\n"
        "然后运行它，观察报错并修复：使函数跳过非数字元素完成求和。"
        "最后把运行输出（单个整数）写入 /workspace/output.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "content = Path('/workspace/output.txt').read_text().strip()\n"
        "ok = content == '7'\n"
        "print('PASS' if ok else f'FAIL: {content!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
)

# ---------------------------------------------------------------------------
# file_edit 专项（4）
# ---------------------------------------------------------------------------

T31 = BatchTask(
    id="T31",
    name="跨文件函数改名",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/utils.py，内容为：\n"
        "def old_name(x):\n    return x * 2\n"
        "2) 创建 /workspace/main.py，内容为：\n"
        "from utils import old_name\nprint(old_name(21))\n"
        "3) 用 file_edit 把函数改名为 double——注意 utils.py 和 main.py "
        "两个文件都要同步修改；\n"
        "4) 运行 main.py，把输出写入 /workspace/out.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "u = Path('/workspace/utils.py').read_text()\n"
        "m = Path('/workspace/main.py').read_text()\n"
        "o = Path('/workspace/out.txt').read_text().strip()\n"
        "ok = 'def double' in u and 'old_name' not in u\n"
        "ok = ok and 'double' in m and 'old_name' not in m and o == '42'\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T32 = BatchTask(
    id="T32",
    name="配置矩阵编辑",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/settings.conf，内容为：\n"
        "env=dev\nthreads=2\ndebug=true\nlog=verbose\n"
        "2) 用 file_edit 把 env 改为 prod；3) 用 file_edit 把 threads 改为 8；\n"
        "4) 用 file_edit 把 debug 改为 false；5) 删除 log 那一整行；\n"
        "6) 用 file_read 读回确认。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = sorted(Path('/workspace/settings.conf').read_text().strip().splitlines())\n"
        "ok = lines == ['debug=false', 'env=prod', 'threads=8']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T33 = BatchTask(
    id="T33",
    name="文档精确修订",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/guide.md，内容为：\n"
        "# 用户指南\n版本: v1.0\n本指南介绍安装步骤。\n详见附录 A。\n"
        "2) 用 file_edit 把标题改为 '# 用户手册'；\n"
        "3) 用 file_edit 把版本改为 v2.0；\n"
        "4) 用 file_edit 把 '安装步骤' 改为 '安装与配置步骤'；\n"
        "5) 用 file_edit 删除 '详见附录 A。' 那一整行。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/guide.md').read_text().strip().splitlines()\n"
        "ok = lines == ['# 用户手册', '版本: v2.0', '本指南介绍安装与配置步骤。']\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T34 = BatchTask(
    id="T34",
    name="双文件版本同步",
    category="file_edit 专项",
    difficulty="L3",
    prompt=(
        "请完成以下任务：1) 创建 /workspace/deploy.yaml，内容为：\n"
        "image: app:v1\nreplicas: 2\n"
        "2) 创建 /workspace/notes.md，内容为：\n"
        "当前版本 app:v1，副本数 2。\n"
        "3) 升级发布：用 file_edit 把镜像改为 app:v2、副本数改为 5，"
        "deploy.yaml 和 notes.md 两个文件都要同步更新；\n"
        "4) 用 file_read 读回两个文件确认。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "y = Path('/workspace/deploy.yaml').read_text()\n"
        "n = Path('/workspace/notes.md').read_text()\n"
        "ok = 'app:v2' in y and 'replicas: 5' in y and 'app:v1' not in y\n"
        "ok = ok and 'app:v2' in n and '5' in n and 'app:v1' not in n\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

# ---------------------------------------------------------------------------
# 长链路（4）
# ---------------------------------------------------------------------------

T35 = BatchTask(
    id="T35",
    name="ETL 迷你管道",
    category="长链路",
    difficulty="L4",
    prompt=(
        "请完成一个迷你 ETL 管道：\n"
        "1) Extract：创建 /workspace/raw.csv，内容为：\n"
        "city,temp\nbeijing,32\nshanghai,\nshanghai,30\nbeijing,35\nguangzhou,28\n"
        "2) Transform：清洗（删除 temp 缺失行、删除完全重复行），"
        "计算每个 city 的平均 temp（保留一位小数），按 city 名升序，"
        "以 'city:avg' 格式写入 /workspace/agg.txt；\n"
        "3) Load：把 'ETL OK' 写入 /workspace/etl_done.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "lines = Path('/workspace/agg.txt').read_text().strip().splitlines()\n"
        "done = Path('/workspace/etl_done.txt').read_text()\n"
        "ok = lines == ['beijing:33.5', 'guangzhou:28.0', 'shanghai:30.0']\n"
        "ok = ok and 'ETL OK' in done\n"
        "print('PASS' if ok else f'FAIL: {lines!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

T36 = BatchTask(
    id="T36",
    name="多阶段统计链",
    category="长链路",
    difficulty="L3",
    prompt=(
        "请完成以下链路：1) 把 1 到 50 中所有 3 的倍数（每行一个）"
        "写入 /workspace/mult3.txt；2) 计算它们的和（单个整数）"
        "写入 /workspace/sum.txt；3) 计算它们的个数（单个整数）"
        "写入 /workspace/count.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "nums = Path('/workspace/mult3.txt').read_text().strip().splitlines()\n"
        "s = Path('/workspace/sum.txt').read_text().strip()\n"
        "c = Path('/workspace/count.txt').read_text().strip()\n"
        "ok = len(nums) == 16 and nums[0] == '3' and nums[-1] == '48'\n"
        "ok = ok and s == '408' and c == '16'\n"
        "print('PASS' if ok else f'FAIL: {len(nums)} {s!r} {c!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T37 = BatchTask(
    id="T37",
    name="三步依赖链",
    category="长链路",
    difficulty="L3",
    prompt=(
        "请完成以下链路（每步依赖上一步产物）：\n"
        "1) 创建 /workspace/step1.txt，写入 5 个整数（每行一个）：4, 9, 2, 7, 5；\n"
        "2) 读取 step1.txt，把数字升序排序后写入 /workspace/step2.txt（每行一个）；\n"
        "3) 读取 step2.txt，计算最大值与最小值的差，"
        "以 'range:7' 的格式写入 /workspace/step3.txt。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "s2 = Path('/workspace/step2.txt').read_text().strip().splitlines()\n"
        "s3 = Path('/workspace/step3.txt').read_text().strip()\n"
        "ok = s2 == ['2', '4', '5', '7', '9'] and s3 == 'range:7'\n"
        "print('PASS' if ok else f'FAIL: {s2!r} {s3!r}')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=14,
)

T38 = BatchTask(
    id="T38",
    name="报告链（S4 批量版）",
    category="长链路",
    difficulty="L4",
    prompt=(
        "请完成以下链路：1) 创建 /workspace/monthly.csv，内容为：\n"
        "month,amount\n2026-01,100\n2026-02,150\n2026-03,120\n2026-04,180\n"
        "2) 读取数据并生成分析报告 /workspace/report.md，标题为 '月度报告'，"
        "正文须包含四个月的总额；\n"
        "3) 用 file_edit 把报告标题改为 '月度经营分析报告'；\n"
        "4) 把最终报告读回来确认。"
    ),
    verify_script=(
        "from pathlib import Path\n"
        "r = Path('/workspace/report.md').read_text()\n"
        "ok = '月度经营分析报告' in r and '550' in r\n"
        "print('PASS' if ok else 'FAIL')\n"
        "raise SystemExit(0 if ok else 1)\n"
    ),
    max_turns=16,
)

# ---------------------------------------------------------------------------
# 开放报告（2，LLM-judge）
# ---------------------------------------------------------------------------

T39 = BatchTask(
    id="T39",
    name="故障分析报告",
    category="开放报告",
    difficulty="L3",
    prompt=(
        "请创建 /workspace/incident.log，内容为：\n"
        "10:01:05 ERROR db connection timeout\n"
        "10:01:06 WARN retry 1/3\n"
        "10:01:09 WARN retry 2/3\n"
        "10:01:15 ERROR db connection timeout\n"
        "10:01:16 ERROR service unavailable\n"
        "10:02:01 INFO db connection restored\n"
        "10:02:05 INFO service recovered\n"
        "然后分析日志，把故障分析报告写入 /workspace/incident_report.md，"
        "包含时间线、根因候选、影响范围和改进建议。最后把报告读给我。"
    ),
    judge_rubric=(
        "报告须满足：1) 时间线正确（10:01:05 首发异常 → 10:02:05 恢复，"
        "持续约 60 秒）；2) 根因候选指向 db 连接超时（非 service 本身）；"
        "3) 影响范围：服务不可用约 45-60 秒（10:01:16 → 10:02:05 区间均可接受）；"
        "4) 至少一条具体改进建议（重试策略/连接池/监控告警等）。"
        "5 分=四项全对且时间推算精确；4 分=四项全对但时间模糊；"
        "3 分=缺一项；≤2 分=根因判断错误或缺两项以上。"
    ),
    artifact_path="/workspace/incident_report.md",
)

T40 = BatchTask(
    id="T40",
    name="限流设计文档",
    category="开放报告",
    difficulty="L4",
    prompt=(
        "请为 API 网关写一份限流设计文档 /workspace/ratelimit_design.md，"
        "说明算法选型、关键参数和边界情况处理。最后把文档读给我。"
    ),
    judge_rubric=(
        "文档须满足：1) 明确的算法选型（令牌桶/漏桶/滑动窗口/固定窗口其一），"
        "且工作原理描述准确；2) 至少 2 个边界情况的具体处理（突发流量、"
        "分布式部署一致性、时钟漂移、长尾 key 等）；3) 给出关键参数及量级"
        "（如速率、桶容量、窗口大小）；4) 结构清晰（分节）。"
        "5 分=四项全满足且描述准确；4 分=满足但边界情况较泛；"
        "3 分=缺一项；≤2 分=算法描述错误或缺两项以上。"
    ),
    artifact_path="/workspace/ratelimit_design.md",
)

BATCH2_TASKS: list[BatchTask] = [
    T21, T22, T23, T24, T25,
    T26, T27, T28, T29, T30,
    T31, T32, T33, T34,
    T35, T36, T37, T38,
    T39, T40,
]
