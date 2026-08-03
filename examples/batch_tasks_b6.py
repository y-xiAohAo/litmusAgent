"""批量 E2E 评测任务集 Batch 6（T103-T122，20 个大记忆库压力任务）。

测量设计：
  - 程序化预置 100 条背景记忆（零 API 成本），仅查询阶段花 token。
  - 注入预算覆盖率 ~5%（inject_max_entries=5 / 100 条），检索必须选对。
  - 判分：expected_in_answer（空白不敏感）；工具序列记录用于检索路径分析。

自审记录：
  - 噪声条目（svc-i/param-i）与查询关键词零共享，避免 L1 误命中；
  - 相似干扰任务（T111-T116）的 decoy 与目标共享"缓存阈值"，是刻意的
    语义区分度测量；
  - 搜索必需任务（T120-T122）采用同义改写查询（literal 失配），
    **不带 expected_tools**——语义臂 L2 注入即可回答时断言搜索是误杀
    （b5 T98 教训），答案判分 + 工具序列记录即可。
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
# 大海捞针（8）：100 噪声 + 1-3 目标（目标 2 天龄，出 L0 窗口）
# ---------------------------------------------------------------------------

T103 = BatchTask(
    id="T103",
    name="捞针-项目代号",
    category="大海捞针",
    difficulty="L4",
    prompt="根据你的长期记忆，我之前记录的项目代号是什么？",
    expected_in_answer=["苍鹭-9"],
    seed_facts=["项目代号是'苍鹭-9'"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

T104 = BatchTask(
    id="T104",
    name="捞针-熔断阈值",
    category="大海捞针",
    difficulty="L4",
    prompt="根据你的长期记忆，我之前记录的熔断阈值是多少？",
    expected_in_answer=["66.1"],
    seed_facts=["熔断阈值是 66.1"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

T105 = BatchTask(
    id="T105",
    name="捞针-双目标",
    category="大海捞针",
    difficulty="L4",
    prompt="根据你的长期记忆，我之前记录的队列名和构建标签分别是什么？",
    expected_in_answer=["q-settle", "b6688"],
    seed_facts=["队列名是 q-settle", "构建标签是 b6688"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

T106 = BatchTask(
    id="T106",
    name="捞针-负责人",
    category="大海捞针",
    difficulty="L4",
    prompt="根据你的长期记忆，我之前记录的负责人是谁？",
    expected_in_answer=["岑蔚"],
    seed_facts=["负责人是岑蔚"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

T107 = BatchTask(
    id="T107",
    name="捞针-端口",
    category="大海捞针",
    difficulty="L4",
    prompt="根据你的长期记忆，我之前记录的服务端口是多少？",
    expected_in_answer=["6201"],
    seed_facts=["服务端口是 6201"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

T108 = BatchTask(
    id="T108",
    name="捞针-三目标",
    category="大海捞针",
    difficulty="L5",
    prompt="根据你的长期记忆，我之前记录的系统代号、部署环境和评审人分别是什么？",
    expected_in_answer=["玄武-12", "prod-eu-2", "祁湛"],
    seed_facts=["系统代号是'玄武-12'", "部署环境是 prod-eu-2", "评审人是祁湛"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T109 = BatchTask(
    id="T109",
    name="捞针-英文代号",
    category="大海捞针",
    difficulty="L4",
    prompt="According to your long-term memory, what was the codename I recorded?",
    expected_in_answer=["falcon-ridge-3"],
    seed_facts=["codename is 'falcon-ridge-3'"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

T110 = BatchTask(
    id="T110",
    name="捞针-保留周期",
    category="大海捞针",
    difficulty="L4",
    prompt="根据你的长期记忆，我之前记录的保留周期是多少天？",
    expected_in_answer=["180"],
    seed_facts=["保留周期是 180 天"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=10,
)

# ---------------------------------------------------------------------------
# 相似干扰（6）：15 条相似 decoy + 100 噪声，查特定服务
# ---------------------------------------------------------------------------

_THRESHOLD_DECOYS = [
    f"服务 {svc} 的缓存阈值是 {val}"
    for svc, val in [
        ("billing", 42.8), ("search", 43.1), ("auth", 41.9), ("push", 44.0),
        ("media", 42.5), ("order", 43.7), ("stock", 41.2), ("pay", 44.5),
        ("risk", 40.9), ("report", 43.3), ("notify", 42.1), ("audit", 44.8),
        ("track", 41.6), ("feed", 43.9), ("geo", 40.5),
    ]
]

T111 = BatchTask(
    id="T111",
    name="相似干扰-gateway",
    category="相似干扰",
    difficulty="L5",
    prompt="根据你的长期记忆，gateway 服务的缓存阈值是多少？",
    expected_in_answer=["42.7"],
    seed_facts=["服务 gateway 的缓存阈值是 42.7"],
    seed_decoys=_THRESHOLD_DECOYS,
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T112 = BatchTask(
    id="T112",
    name="相似干扰-billing",
    category="相似干扰",
    difficulty="L5",
    prompt="根据你的长期记忆，billing 服务的缓存阈值是多少？",
    expected_in_answer=["42.8"],
    seed_facts=["服务 billing 的缓存阈值是 42.8"],
    seed_decoys=[d for d in _THRESHOLD_DECOYS if "billing" not in d],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T113 = BatchTask(
    id="T113",
    name="相似干扰-pay",
    category="相似干扰",
    difficulty="L5",
    prompt="根据你的长期记忆，pay 服务的缓存阈值是多少？",
    expected_in_answer=["44.5"],
    seed_facts=["服务 pay 的缓存阈值是 44.5"],
    seed_decoys=[d for d in _THRESHOLD_DECOYS if "pay" not in d],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

_PARAM_DECOYS = [
    f"服务 {svc} 的超时时间是 {val} 秒"
    for svc, val in [
        ("billing", 31), ("search", 28), ("auth", 45), ("push", 19),
        ("media", 52), ("order", 26), ("stock", 60), ("pay", 33),
        ("risk", 48), ("report", 22), ("notify", 41), ("audit", 55),
        ("track", 29), ("feed", 38), ("geo", 44),
    ]
]

T114 = BatchTask(
    id="T114",
    name="相似干扰-gateway 超时",
    category="相似干扰",
    difficulty="L5",
    prompt="根据你的长期记忆，gateway 服务的超时时间是多少秒？",
    expected_in_answer=["37"],
    seed_facts=["服务 gateway 的超时时间是 37 秒"],
    seed_decoys=_PARAM_DECOYS,
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T115 = BatchTask(
    id="T115",
    name="相似干扰-audit 超时",
    category="相似干扰",
    difficulty="L5",
    prompt="根据你的长期记忆，audit 服务的超时时间是多少秒？",
    expected_in_answer=["55"],
    seed_facts=["服务 audit 的超时时间是 55 秒"],
    seed_decoys=[d for d in _PARAM_DECOYS if "audit" not in d],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T116 = BatchTask(
    id="T116",
    name="相似干扰-geo 超时",
    category="相似干扰",
    difficulty="L5",
    prompt="根据你的长期记忆，geo 服务的超时时间是多少秒？",
    expected_in_answer=["44"],
    seed_facts=["服务 geo 的超时时间是 44 秒"],
    seed_decoys=[d for d in _PARAM_DECOYS if "geo" not in d],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

# ---------------------------------------------------------------------------
# 深埋旧值（3）：目标 10/20/30 天龄，100 噪声全部更新
# ---------------------------------------------------------------------------

T117 = BatchTask(
    id="T117",
    name="深埋-初始管理员",
    category="深埋旧值",
    difficulty="L4",
    prompt="根据你的长期记忆，系统的初始管理员是谁？",
    expected_in_answer=["韩砺"],
    seed_facts=["系统的初始管理员是韩砺"],
    noise_count=100,
    target_age_days=10.0,
    max_turns=10,
)

T118 = BatchTask(
    id="T118",
    name="深埋-初代版本号",
    category="深埋旧值",
    difficulty="L4",
    prompt="根据你的长期记忆，项目的初代版本号是什么？",
    expected_in_answer=["v0.9.3"],
    seed_facts=["项目的初代版本号是 v0.9.3"],
    noise_count=100,
    target_age_days=20.0,
    max_turns=10,
)

T119 = BatchTask(
    id="T119",
    name="深埋-立项日期",
    category="深埋旧值",
    difficulty="L5",
    prompt="根据你的长期记忆，项目的立项日期是哪一天？",
    expected_in_answer=["2024-11-02"],
    seed_facts=["项目的立项日期是 2024-11-02"],
    noise_count=100,
    target_age_days=30.0,
    max_turns=12,
)

# ---------------------------------------------------------------------------
# 搜索必需（3）：同义改写查询，literal 失配（不带工具断言，见自审）
# ---------------------------------------------------------------------------

T120 = BatchTask(
    id="T120",
    name="语义搜索-内存上限",
    category="搜索必需",
    difficulty="L5",
    prompt="根据你的长期记忆，控制内存占用的那个上限数字是多少？",
    expected_in_answer=["42.7"],
    seed_facts=["缓存阈值是 42.7"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T121 = BatchTask(
    id="T121",
    name="语义搜索-总负责人",
    category="搜索必需",
    difficulty="L5",
    prompt="根据你的长期记忆，谁对这个项目负总责？",
    expected_in_answer=["林晚"],
    seed_facts=["负责人是林晚"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T122 = BatchTask(
    id="T122",
    name="语义搜索-发布编号",
    category="搜索必需",
    difficulty="L5",
    prompt="根据你的长期记忆，发布用的那个编号是什么？",
    expected_in_answer=["b2077"],
    seed_facts=["构建标签是 b2077"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

# ---------------------------------------------------------------------------
# 查询扩展复验（3，QE 验收）：T122 同型硬 paraphrase
# ---------------------------------------------------------------------------

T123 = BatchTask(
    id="T123",
    name="QE复验-访问标识",
    category="搜索必需",
    difficulty="L5",
    prompt="根据你的长期记忆，对外提供访问的那个数字标识是什么？",
    expected_in_answer=["9187"],
    seed_facts=["服务端口是 9187"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T124 = BatchTask(
    id="T124",
    name="QE复验-归谁管",
    category="搜索必需",
    difficulty="L5",
    prompt="根据你的长期记忆，这个项目现在归谁管？",
    expected_in_answer=["沈确"],
    seed_facts=["负责人是沈确"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

T125 = BatchTask(
    id="T125",
    name="QE复验-临界值",
    category="搜索必需",
    difficulty="L5",
    prompt="根据你的长期记忆，触发通知的那个临界值是多少？",
    expected_in_answer=["42.7"],
    seed_facts=["告警阈值是 42.7"],
    noise_count=100,
    target_age_days=2.0,
    max_turns=12,
)

BATCH6_TASKS: list[BatchTask] = [
    T103, T104, T105, T106, T107, T108, T109, T110,
    T111, T112, T113, T114, T115, T116,
    T117, T118, T119,
    T120, T121, T122,
    T123, T124, T125,
]
