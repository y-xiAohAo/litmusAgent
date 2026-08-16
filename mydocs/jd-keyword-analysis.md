# JD 关键词分析 × 简历覆盖矩阵 — LLM/Agent 应用工程（校招/实习）

> 创建：2026-07-19 | 依据：spec §7 执行计划 Round 2
> 用途：ATS 关键词覆盖检查 + 措辞对齐（用 JD 原词替换内部说法）
> 关联：`2026-07-19_resume-benchmark-analysis.md`（写法方法论）、spec §3（数字证据）

---

## 1. JD 样本清单（7 份真实在招岗位，2026-2027 届）

| # | 公司/岗位 | 来源 | 关键要求摘录 |
|---|---|---|---|
| J1 | 美团 · AI Agent（校招） | zhaopin.meituan.com | Agent 架构设计与核心模块研发；Agentic 工作流；**精通 Prompt Engineering、RAG、Function Calling/Tool Binding**；复杂 Agent（**任务规划、工具调用、记忆与学习机制**）设计开发调优；**构建面向 Agent 的评估体系** |
| J2 | 阿里巴巴 · AI Agent 优化工程师（27届实习） | campus-talent.alibaba.com | 上下文工程；**自动化评估体系/量化评估能力**；知识库（RAG）、**长短期记忆系统（Memory）**、工具调用、多 Agent 协作；MCP/Skills 协议；较强 Python 工程能力 |
| J3 | 中科院系统 · AI Agent 工程师 J26946 | gaoxiaojob.com | 智能体核心架构：**任务分解、工具调用、记忆管理与自我反思**；提示工程、RAG、Function Calling；**Self-Reflection 与 Self-Correction 落地经验**；异步编程与高并发 |
| J4 | 格科微 · AI Agent 工程师（含实习） | yingjiesheng.com | **benchmark 任务与评分规则构建；Agent 失败模式分析**；工具调用、RAG、function calling、多步任务执行、agent orchestration；**Git、测试、文档、可复现实验流程**；能展示过往项目/代码/Demo |
| J5 | 钛动科技 · Agent 开发工程师（2026 校招） | wondercv.com | RAG 与工具调用；LLM API、Prompt Engineering；加分：**GitHub 开源项目**或高质量技术博客 |
| J6 | AIA · AI Agent 实习 | cn.indeed.com | Agent 核心模块：**规划推理、工具调用、记忆管理**；多轮对话推理与任务规划；性能调优、日志分析；提示词编写 |
| J7 | 厦门众诚则 · AI Agent 应用开发工程师（校招） | career.xujc.com | **Prompt Engineering、RAG 检索增强、工具调用、工作流编排**；Python；LangChain/LlamaIndex/Dify/Coze 经验优先 |

## 2. 关键词频次表（7 份 JD 统计）

| 关键词 | 出现次数 | 出处 |
|---|---|---|
| 工具调用 / Function Calling | 7/7 | J1-J7 全部 |
| RAG / 检索增强 | 6/7 | J1 J2 J3 J4 J5 J7 |
| Prompt Engineering / 提示词 | 6/7 | J1 J3 J5 J6 J7（J2 上下文工程近似） |
| 记忆 / Memory（长短期记忆、记忆管理） | 5/7 | J1 J2 J3 J4(隐含) J6 |
| 任务规划 / 任务分解 / 规划推理 | 5/7 | J1 J3 J4(多步任务) J6 J7 |
| 评估体系 / 量化评估 / benchmark | 4/7 | J1 J2 J4（J3 评估体系近似） |
| Python | 5/7 | J2 J3 J4 J5 J7 |
| 自我反思 / Self-Correction | 2/7 | J3（另 J1"记忆与学习机制"近似） |
| 上下文工程 / 上下文管理 | 2/7 | J2 J6 |
| 工作流编排 / orchestration | 2/7 | J4 J7 |
| Git / 测试 / 文档 / 可复现 | 2/7 | J4 J5 |
| 框架（LangChain/LlamaIndex/Dify 等） | 3/7 | J3 J4(协议) J7 |

## 3. 覆盖矩阵：JD 关键词 × 本项目证据 × B v2 现状

| JD 关键词 | 本项目证据（可溯源） | B v2 是否显性覆盖 | 处理建议 |
|---|---|---|---|
| 工具调用 / Function Calling | 可插拔工具系统；反思使**无效工具调用** -26% | ⚠️ 半覆盖（"无效调用"未点明是工具调用） | 措辞改为"无效**工具**调用" |
| 任务规划 / 任务分解 | 自动 Planner：LLM **分解任务**为 TaskPlan，0/8→3/3 | ✅ | 可用 JD 原词"**任务分解**" |
| 记忆 / Memory | 长期记忆三层重构，召回 0/2→2/2 | ✅ | 已覆盖 |
| 自我反思 / Self-Correction | 反思纠错链路 + A/B 量化 | ✅ | 措辞可对齐"**自我反思（Self-Correction）**" |
| 评估体系 / 量化评估 | **13 场景真实联调套件 + A/B 对照实验**（核心差异化，J1/J2/J4 明确要求） | ❌ **缺失**（B v2 只在反思条提到 A/B） | **必须补**：简介或独立 bullet 点出"评估体系" |
| RAG / 检索增强 | 记忆分层检索（recency 兜底+语义重排+快照）、memory_search 语义搜索 | ⚠️ 半覆盖 | 记忆条可加"**检索**"字样，自然命中 |
| Prompt Engineering / 上下文工程 | 规划注入进度提示、反思策略注入、上下文压缩与外迁 | ⚠️ 隐含 | 简介"配置驱动"可顺带"上下文管理" |
| Python / 工程能力 | 679 测试 / 91% 覆盖 / mypy / async | ✅（标题行） | 已覆盖 |
| 工作流编排 / orchestration | TaskPlan 分步推进 + 工具注册表 | ⚠️ 隐含 | 不单列，规划条已近似 |
| Git / 测试 / 可复现实验 | TDD、evaluation-log 全程记录、公开仓库 litmusAgent | ⚠️ 半覆盖 | 简介或结尾可附 GitHub 链接（J5 加分项） |
| 框架（LangChain 等） | **零依赖自研框架** | ❌ | 转述为优势："未依赖 LangChain 等框架，从零实现" |

## 4. 对 R3 打磨的约束（新增，叠加在对标分析 §4 之上）

1. **评估体系必须显性化**：J1/J2/J4 三份 JD 明确要求评估/benchmark 能力，这正是我们最强差异点——B v2 把它埋没了，下一版优先修。
2. **措辞对齐 JD 原词**：任务分解、工具调用、记忆管理、自我反思——ATS 与面试官扫读都认这些词。
3. **附 GitHub 链接**：J5 明确加分，J4 要求"能展示项目代码"——仓库已上线，简历应放链接。
4. **零框架自研是卖点不是缺口**：JD 写"有 LangChain 经验者优先"，"从零实现框架"在深度上覆盖该要求，但措辞要避免显得"没用过框架"（面试可展开）。
5. 维持既有约束：数字零虚构、痛点→方案→量化结果结构。
