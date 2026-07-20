"""批量 E2E 评测任务集 Batch 5（T81-T100，20 个记忆专项两阶段任务）。

测量设计：
  - 两阶段执行：phase A 用 file_write 把事实写入文件（规则提取器捕获产物
    内容快照）→ 新会话 phase B 查询（无对话历史，记忆是唯一信息通道）。
  - 判分：expected_in_answer（答案必须包含全部关键事实，确定性零歧义）。
  - 搜索模式任务带 expected_tools=["memory_search"]（验证先搜后读行为）。

设计约束（来自记忆系统实证）：
  - 规则提取器只覆盖产物/环境/失败模式，**不提取纯对话事实**——所以事实
    必须以文件为载体（file_write 内容快照，截断 200 字）。
  - 提取器按路径去重（同路径第二次写入被跳过）——冲突更新任务必须用
    新文件承载新值，测"近期记忆优先"而非原地更新。
  - 干扰任务的事实拆两文件写入，避免 200 字快照截断。
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
# 跨会话召回（8）：file_write 写入 2-4 条事实，phase B 查询
# ---------------------------------------------------------------------------

T81 = BatchTask(
    id="T81",
    name="代号+负责人",
    category="跨会话召回",
    difficulty="L3",
    prompt="请用 file_write 把以下信息记录到 /workspace/notes.txt：项目代号是'蓝鲸计划'，负责人是林晚。完成后回复已记住。",
    prompt_b="我之前记录的项目代号和负责人分别是什么？",
    expected_in_answer=["蓝鲸计划", "林晚"],
    max_turns=8,
)

T82 = BatchTask(
    id="T82",
    name="代号+阈值+环境",
    category="跨会话召回",
    difficulty="L3",
    prompt=(
        "请用 file_write 把以下信息记录到 /workspace/notes.txt：系统代号是'北极星-7'，"
        "告警阈值是 42.7，部署环境是 staging-03。完成后回复已记住。"
    ),
    prompt_b="我之前记录的系统代号、告警阈值和部署环境分别是什么？",
    expected_in_answer=["北极星-7", "42.7", "staging-03"],
    max_turns=8,
)

T83 = BatchTask(
    id="T83",
    name="偏好三件套",
    category="跨会话召回",
    difficulty="L3",
    prompt="请用 file_write 把以下信息记录到 /workspace/notes.txt：我喜欢的主题色是黛蓝，幸运数字是 73，当前版本号是 v3.7.1。完成后回复已记住。",
    prompt_b="我之前记录的主题色、幸运数字和当前版本号分别是什么？",
    expected_in_answer=["黛蓝", "73", "v3.7.1"],
    max_turns=8,
)

T84 = BatchTask(
    id="T84",
    name="技术参数组",
    category="跨会话召回",
    difficulty="L3",
    prompt="请用 file_write 把以下信息记录到 /workspace/notes.txt：API 端口是 9187，请求超时是 37 秒，最大重试次数是 5。完成后回复已记住。",
    prompt_b="我之前记录的 API 端口、请求超时和最大重试次数分别是多少？",
    expected_in_answer=["9187", "37", "5"],
    max_turns=8,
)

T85 = BatchTask(
    id="T85",
    name="四事实混合",
    category="跨会话召回",
    difficulty="L4",
    prompt=(
        "请用 file_write 把以下信息记录到 /workspace/notes.txt：数据库主机是 db-lan-04，"
        "只读副本有 2 个，备份窗口是凌晨 2:30，保留周期是 45 天。完成后回复已记住。"
    ),
    prompt_b="我之前记录的数据库主机、只读副本数、备份窗口和保留周期分别是什么？",
    expected_in_answer=["db-lan-04", "2", "2:30", "45"],
    max_turns=8,
)

T86 = BatchTask(
    id="T86",
    name="人名+日期+版本",
    category="跨会话召回",
    difficulty="L3",
    prompt="请用 file_write 把以下信息记录到 /workspace/notes.txt：评审人是沈确，截止日期是 3 月 14 日，目标版本是'玄铁-2049'。完成后回复已记住。",
    prompt_b="我之前记录的评审人、截止日期和目标版本分别是什么？",
    expected_in_answer=["沈确", "3 月 14 日", "玄铁-2049"],
    max_turns=8,
)

T87 = BatchTask(
    id="T87",
    name="英文代号组",
    category="跨会话召回",
    difficulty="L3",
    prompt=(
        "Please use file_write to save to /workspace/notes.txt: codename is "
        "'ember-fall-9', owner is K. Voss, build tag is r5842. Reply acknowledged."
    ),
    prompt_b="What were the codename, owner, and build tag I recorded?",
    expected_in_answer=["ember-fall-9", "Voss", "r5842"],
    max_turns=8,
)

T88 = BatchTask(
    id="T88",
    name="配置三元组",
    category="跨会话召回",
    difficulty="L3",
    prompt="请用 file_write 把以下信息记录到 /workspace/notes.txt：缓存目录是 /data/cache-aux，上限是 768MB，淘汰策略是 LFU。完成后回复已记住。",
    prompt_b="我之前记录的缓存目录、上限和淘汰策略分别是什么？",
    expected_in_answer=["/data/cache-aux", "768", "LFU"],
    max_turns=8,
)

# ---------------------------------------------------------------------------
# 干扰召回（6）：10 条事实拆两文件（避免 200 字快照截断），查 2-3 条
# ---------------------------------------------------------------------------

_NOISE_A_1 = "请用 file_write 把以下信息记录到 /workspace/notes_a.txt：网关端口是 8081；日志级别是 DEBUG；会话超时是 42 分钟；项目代号是'火棘草'；依赖锁版本是 3.11.9。"
_NOISE_B_1 = "请继续用 file_write 把以下信息记录到 /workspace/notes_b.txt：缓存阈值是 42.7；负责人是林晚；队列名是 jobs-priority；构建标签是 b2077；监控间隔是 13 秒。完成后回复已记住。"

T89 = BatchTask(
    id="T89",
    name="十条干扰查阈值+代号",
    category="干扰召回",
    difficulty="L4",
    prompt=_NOISE_A_1 + "\n" + _NOISE_B_1,
    prompt_b="我之前记录的缓存阈值和项目代号分别是什么？",
    expected_in_answer=["42.7", "火棘草"],
    max_turns=10,
)

T90 = BatchTask(
    id="T90",
    name="十条干扰查队列+标签",
    category="干扰召回",
    difficulty="L4",
    prompt=_NOISE_A_1 + "\n" + _NOISE_B_1,
    prompt_b="我之前记录的队列名和构建标签分别是什么？",
    expected_in_answer=["jobs-priority", "b2077"],
    max_turns=10,
)

_NOISE_A_2 = "请用 file_write 把以下信息记录到 /workspace/notes_a.txt：集群名是 nebula-east；副本数是 6；评审人是沈确；目标版本是'玄铁-2049'；端口是 9187。"
_NOISE_B_2 = "请继续用 file_write 把以下信息记录到 /workspace/notes_b.txt：主题色是黛蓝；截止日期是 3 月 14 日；超时是 37 秒；队列是 q-backfill；环境是 staging-03。完成后回复已记住。"

T91 = BatchTask(
    id="T91",
    name="十条干扰查三项",
    category="干扰召回",
    difficulty="L4",
    prompt=_NOISE_A_2 + "\n" + _NOISE_B_2,
    prompt_b="我之前记录的目标版本、端口和队列分别是什么？",
    expected_in_answer=["玄铁-2049", "9187", "q-backfill"],
    max_turns=10,
)

T92 = BatchTask(
    id="T92",
    name="十条干扰查日期+评审人",
    category="干扰召回",
    difficulty="L4",
    prompt=_NOISE_A_2 + "\n" + _NOISE_B_2,
    prompt_b="我之前记录的截止日期和评审人分别是什么？",
    expected_in_answer=["3 月 14 日", "沈确"],
    max_turns=10,
)

_NOISE_A_3 = "请用 file_write 把以下信息记录到 /workspace/notes_a.txt：主机是 db-lan-04；副本 2 个；备份窗口是凌晨 2:30；保留周期 45 天；目录是 /data/cache-aux。"
_NOISE_B_3 = "请继续用 file_write 把以下信息记录到 /workspace/notes_b.txt：上限 768MB；策略是 LFU；幸运数字是 73；版本是 v3.7.1；告警阈值是 42.7。完成后回复已记住。"

T93 = BatchTask(
    id="T93",
    name="十条干扰查备份+周期",
    category="干扰召回",
    difficulty="L4",
    prompt=_NOISE_A_3 + "\n" + _NOISE_B_3,
    prompt_b="我之前记录的备份窗口和保留周期分别是什么？",
    expected_in_answer=["2:30", "45"],
    max_turns=10,
)

T94 = BatchTask(
    id="T94",
    name="十条干扰查目录+策略",
    category="干扰召回",
    difficulty="L4",
    prompt=_NOISE_A_3 + "\n" + _NOISE_B_3,
    prompt_b="我之前记录的缓存目录和淘汰策略分别是什么？",
    expected_in_answer=["/data/cache-aux", "LFU"],
    max_turns=10,
)

# ---------------------------------------------------------------------------
# 冲突更新（3）：旧值文件 + 更正文件，测近期记忆优先
# ---------------------------------------------------------------------------

T95 = BatchTask(
    id="T95",
    name="阈值更正",
    category="冲突更新",
    difficulty="L4",
    prompt=(
        "请用 file_write 把以下信息记录到 /workspace/config_v1.txt：告警阈值是 30。\n"
        "随后用 file_write 把更正信息记录到 /workspace/config_v2.txt："
        "更正：告警阈值改为 45。完成后回复已记住。"
    ),
    prompt_b="我最后确认的告警阈值是多少？",
    expected_in_answer=["45"],
    max_turns=10,
)

T96 = BatchTask(
    id="T96",
    name="负责人更正",
    category="冲突更新",
    difficulty="L4",
    prompt=(
        "请用 file_write 把以下信息记录到 /workspace/owner_v1.txt：项目负责人是林晚。\n"
        "随后用 file_write 把更正信息记录到 /workspace/owner_v2.txt："
        "更正：负责人改为沈确。完成后回复已记住。"
    ),
    prompt_b="我最后确认的项目负责人是谁？",
    expected_in_answer=["沈确"],
    max_turns=10,
)

T97 = BatchTask(
    id="T97",
    name="端口更正",
    category="冲突更新",
    difficulty="L4",
    prompt=(
        "请用 file_write 把以下信息记录到 /workspace/port_v1.txt：服务端口是 9187。\n"
        "随后用 file_write 把更正信息记录到 /workspace/port_v2.txt："
        "更正：端口改为 9201。完成后回复已记住。"
    ),
    prompt_b="我最后确认的服务端口是多少？",
    expected_in_answer=["9201"],
    max_turns=10,
)

# ---------------------------------------------------------------------------
# 搜索模式（3）：自然语言查询，必须先搜后读
# ---------------------------------------------------------------------------

T98 = BatchTask(
    id="T98",
    name="语义查询-缓存阈值",
    category="搜索模式",
    difficulty="L4",
    prompt=_NOISE_A_1 + "\n" + _NOISE_B_1,
    prompt_b="我之前记录过的一个和缓存有关的数值阈值是多少？",
    expected_in_answer=["42.7"],
    max_turns=10,
)

T99 = BatchTask(
    id="T99",
    name="语义查询-构建标识",
    category="搜索模式",
    difficulty="L4",
    prompt=_NOISE_A_1 + "\n" + _NOISE_B_1,
    prompt_b="我之前记录过的那个构建相关的标识是什么？",
    expected_in_answer=["b2077"],
    max_turns=10,
)

T100 = BatchTask(
    id="T100",
    name="语义查询-版本目标",
    category="搜索模式",
    difficulty="L4",
    prompt=_NOISE_A_2 + "\n" + _NOISE_B_2,
    prompt_b="我之前记录过的版本目标叫什么？",
    expected_in_answer=["玄铁-2049"],
    max_turns=10,
)

BATCH5_TASKS: list[BatchTask] = [
    T81, T82, T83, T84, T85, T86, T87, T88,
    T89, T90, T91, T92, T93, T94,
    T95, T96, T97,
    T98, T99, T100,
]
