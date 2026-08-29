"""Agent 配置系统 —— 类型安全的 YAML 配置加载。

设计原则：
  1. 配置与代码分离：敏感信息（API Key）、环境差异（模型名、温度）
     不应该硬编码在代码中
  2. 类型安全：用 Pydantic 模型替代 dict，IDE 能自动补全，
     写错字段名在加载时就报错
  3. 默认值友好：只配关键参数，其余有合理默认值

配置层级（从高到低）：
  AgentConfig            ← 顶层，聚合所有子系统配置
  ├── LLMConfig          ← LLM 后端配置（provider、model、api_key）
  ├── AgentRuntimeConfig ← Agent 运行时配置（max_turns、system_prompt）
  └── SandboxConfig      ← 代码沙箱配置（backend、image、timeout）

为什么用 Pydantic 而不是 dataclass？
  - Pydantic 有自动类型校验：YAML 里写 temperature: "hot" 会直接报错
  - Pydantic 有序列化能力：可以 .model_dump() 导出 JSON 用于日志
  - Pydantic 支持嵌套模型：AgentConfig 直接包含 LLMConfig 等子模型
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from agent.core.security import PolicyEngine


class LLMConfig(BaseModel):
    """LLM 后端配置。

    base_url 的设计：
      默认是 OpenAI 的 API 地址，但可以改成任何兼容 OpenAI API 的端点。
      例如：
        - DeepSeek: https://api.deepseek.com/v1
        - 本地模型: http://localhost:1234/v1
        - 代理: http://my-proxy:8080/v1
      这就是 "OpenAI 兼容" 的价值 —— 一个接口适配所有。

    temperature 的含义：
      0.0 = 确定性输出（每次都一样）
      1.0 = 高随机性（每次可能不同）
      对于代码生成 Agent，建议 0.1-0.3（需要准确，不需要创意）
    """

    provider: str = "openai"                          # 提供商：openai / deepseek / anthropic
    model: str = "gpt-4o"                             # 模型名称
    api_key: str = ""                                  # API 密钥（通过环境变量或 YAML 配置）
    base_url: str = "https://api.openai.com/v1"       # API 端点地址
    temperature: float = 0.7                           # 生成温度（0-1）
    max_tokens: int = 4096                             # 每次回复的最大 token 数


class ContextCompressionConfig(BaseModel):
    """上下文压缩配置（Phase 7）。

    默认全部关闭，避免静默改变现有 Agent 行为。
    用户显式启用后，Agent 才会创建压缩相关组件。
    """

    enabled: bool = False
    context_window: int = 8192
    reserve_tokens: int = 1024
    externalize_threshold: int = 800
    file_read_preview_chars: int = 500
    exec_success_preview_chars: int = 200
    exec_error_preview_chars: int = 1000
    cleanup_on_exit: bool = True
    cache_root: str = ".hermes/context_cache"
    register_context_read: bool = True
    protect_first_n: int = 2
    protect_last_n_turns: int = 2
    summary_model: str = "gpt-4o-mini"
    summary_max_tokens: int = 512


class MemoryConfig(BaseModel):
    """长期记忆配置（Phase 8）。

    默认关闭，避免静默改变现有 Agent 行为。
    用户显式启用后，Agent 才会创建长期记忆相关组件。
    """

    enabled: bool = False
    backend: str = "structured"           # 仅 structured，语义检索/图记忆预留
    memory_root: str = ".hermes/memory"
    store_backend: str = "jsonl"          # 存储后端：jsonl（默认）/ sql（SQLAlchemy Core）
    sql_url: str | None = None            # store_backend=sql 时的连接串（SQLite/MySQL）
    cache_enabled: bool = False           # Redis 注入结果缓存（generation 失效 + 降级）
    redis_url: str = "redis://localhost:6379/0"
    max_entries_per_category: int = 100
    retrieval_top_k: int = 5
    recency_fallback: bool = True        # L0：零命中时注入最近 top_k 条（防失忆）
    semantic_retrieval: bool = False     # L2：L1 未命中时 LLM 语义重排
    inject_max_entries: int = 5
    inject_max_tokens: int = 800
    persist_error_patterns: bool = True
    filter_sensitive: bool = True
    sensitive_patterns: list[str] = Field(default_factory=lambda: [
        "api_key", "password", "secret", "token", "private_key",
    ])
    llm_extraction_enabled: bool = False
    query_expansion_enabled: bool = False  # 查询扩展：L1 失配时 LLM 生成同义变体再检索
    max_age_days: int | None = None       # 记忆最大保留天数；None = 不做时间清理（默认）
    summarizer_model: str = "gpt-4o-mini"
    summarizer_max_tokens: int = 512
    cleanup_on_exit: bool = False         # 长期记忆默认不清理
    register_memory_read: bool = True
    stale_threshold_days: int = 30        # 通用类别记忆半衰期（天）
    environment_stale_days: int = 7       # environment 类别记忆半衰期（天）


class HumanApprovalConfig(BaseModel):
    """写操作人工确认配置（TD-008）。

    enabled 为三态：
      - None（默认）：未显式配置；host_dir（bind）模式下装配层按 True
        生效（默认保护宿主工作区），其余模式按不启用处理。
      - True / False：用户显式配置，优先于一切默认推导。
    仅 callback 存在时确认流程才真正生效。
    """

    enabled: bool | None = None   # None = 未显式配置；host_dir 模式下装配层按 True 生效
    tools: list[str] = Field(default_factory=lambda: ["file_write", "file_edit"])


class PlannerConfig(BaseModel):
    """自动规划配置（Auto-Planner）。

    默认关闭。启用后 `Agent.run()` 会先调用 LLM 把任务分解为有序步骤，
    再走 Planner 进度注入机制（多步任务可靠性显著提升，代价是每 run
    多一次 LLM 调用）。
    """

    enabled: bool = False
    max_steps: int = 6


class AgentRuntimeConfig(BaseModel):
    """Agent 运行时行为配置。

    max_turns：
      安全限制，防止 Agent 陷入无限循环调用工具。
      每轮 = 一次 LLM 调用 + 可能的一次工具执行。
      默认 20 轮足够应对大多数分析任务。

    system_prompt：
      Agent 的"人格设定"，会作为第一条消息发给 LLM。
      默认提示鼓励 Agent 编写和执行代码。

    compression：
      Phase 7 上下文压缩配置，默认关闭。
    """

    max_turns: int = 20
    system_prompt: str = "你是一个有用的 AI 助手，可以编写和执行代码。"
    compression: ContextCompressionConfig = Field(default_factory=ContextCompressionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    human_approval: HumanApprovalConfig = Field(default_factory=HumanApprovalConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)


class SecurityConfig(BaseModel):
    """安全策略配置（Phase 9）。

    默认关闭，避免静默改变现有 Agent 行为。用户显式启用后，若未提供
    自定义规则，则使用内置宽松默认规则集；若提供自定义规则，则完全
    由自定义规则接管。
    """

    enabled: bool = False
    default_action: str = "allow"      # allow / deny
    rules: list[dict[str, Any]] = Field(default_factory=list)
    # TD-006：file/path write 的允许根（POSIX 风格，统一小写，去尾部 /）。
    # 仅在使用默认规则集时生效；自定义规则集完全接管，不注入边界。
    workspace_path: str = "/workspace"
    # 为后续文件/记忆策略预留的扩展字段
    file_read_deny_patterns: list[str] = Field(default_factory=list)
    memory_read_only_categories: list[str] = Field(default_factory=list)
    # TD-015 单元 C：host_dir bind 模式时由装配层置 True，在默认规则集上
    # 追加敏感文件 read deny（优先级 90）。自定义规则集完全接管，不注入。
    bind_read_deny: bool = False

    def build_policy_engine(self) -> PolicyEngine | None:
        """根据配置构建 PolicyEngine；未启用时返回 None。"""
        if not self.enabled:
            return None
        if not self.rules:
            engine = PolicyEngine.default(default_action=self.default_action)
            self._apply_workspace_override(engine)
            if self.bind_read_deny:
                self._apply_bind_read_deny(engine)
            return engine
        return PolicyEngine.from_config(
            rules=list(self.rules),
            default_action=self.default_action,
        )

    # TD-015 保险三：bind 模式追加的敏感文件 read deny（subject 已归一化
    # 为小写 POSIX 风格路径，pattern 使用正则小写）。
    _BIND_READ_DENY: ClassVar[tuple[tuple[str, str], ...]] = (
        (r"(^|/)\.env", "禁止读取 .env 等环境密钥文件（bind 工作区保护）"),
        (r"(^|/)\.ssh/", "禁止读取 .ssh 目录（bind 工作区保护）"),
        (r"\.(pem|key)$", "禁止读取 pem/key 密钥文件（bind 工作区保护）"),
        (r"(^|/)id_rsa", "禁止读取 id_rsa 私钥（bind 工作区保护）"),
        (r"(^|/)\.git/", "禁止读取 .git 内部对象（bind 工作区保护）"),
    )

    def _apply_bind_read_deny(self, engine: PolicyEngine) -> None:
        """在默认规则集上追加 bind 模式敏感文件 read deny（优先级 90）。

        对应 spec 模式：`**/.env*`、`**/.ssh/**`、`**/*.{pem,key}`、
        `**/id_rsa*`、`**/.git/**`。read 不加 catch-all（项目文件需可读）。
        """
        from agent.core.security import PolicyAction, PolicyRule

        for pattern, reason in self._BIND_READ_DENY:
            engine.add_rule(
                PolicyRule(
                    resource="file/path",
                    operation="read",
                    pattern=pattern,
                    action=PolicyAction.DENY,
                    reason=reason,
                    priority=90,
                    use_regex=True,
                )
            )

    def _apply_workspace_override(self, engine: PolicyEngine) -> None:
        """当 workspace_path 非默认值时，在默认规则集上追加边界覆盖规则。

        覆盖规则（TD-006）：
          - allow `^{custom}(/|$)`（priority 60）：新边界内允许写入；
          - deny `^/workspace(/|$)`（priority 55）：撤销默认 /workspace 边界。
        """
        import re

        from agent.core.security import PolicyAction, PolicyRule

        custom = self.workspace_path.rstrip("/").lower()
        if not custom or custom == "/workspace":
            return
        escaped = re.escape(custom)
        engine.add_rule(
            PolicyRule(
                resource="file/path",
                operation="write",
                pattern=f"^{escaped}(/|$)",
                action=PolicyAction.ALLOW,
                reason=f"允许写入自定义 workspace 边界内路径（{custom}）",
                priority=60,
                use_regex=True,
            )
        )
        engine.add_rule(
            PolicyRule(
                resource="file/path",
                operation="write",
                pattern="^/workspace(/|$)",
                action=PolicyAction.DENY,
                reason="workspace 边界已迁移，/workspace 不再允许写入",
                priority=55,
                use_regex=True,
            )
        )


class SandboxConfig(BaseModel):
    """代码执行沙箱配置。

    backend：沙箱实现方式
      - "docker"：使用 Docker 容器隔离（最安全，需要 Docker Engine）
      - "subprocess"：使用 Python subprocess（轻量，安全性较低）

    timeout：代码执行超时时间（秒）
      如果 LLM 生成的代码有死循环，这个限制能防止资源耗尽。

    memory_limit_mb：内存限制（MB）
      通过 Docker 的 cgroup 实现，防止 LLM 的代码耗尽宿主机内存。

    volume_name（TD-015 单元 B）：持久工作区卷名
      配置后实际使用 Docker 卷 `litmus-ws-<volume_name>`，跨会话保留
      工作区文件；为 None（默认）时使用随机卷并在关闭时清理。

    host_dir（TD-015 单元 C）：宿主机目录 bind 挂载
      配置后沙箱直接操作宿主机真实项目目录（/workspace → host_dir）。
      强制 git 快照保险（非 git 目录拒绝启动）、写确认与敏感文件
      read deny 默认生效；docker 后端 Docker 不可用时明确报错不降级。

    本类同时承载 host_dir 模式的安全件装配推导（is_bind_mode /
    effective_human_approval_enabled / effective_security_enabled），
    供 CLI / Web 装配层统一调用。
    """

    backend: str = "docker"            # 沙箱后端：docker / subprocess
    image: str = "python:3.11-slim"    # Docker 镜像（仅 docker 后端使用）
    image_registry: str | None = None  # 镜像源地址（TD-007），None = Docker Hub
    timeout: int = 30                  # 执行超时（秒）
    memory_limit_mb: int = 256         # 内存上限（MB）
    volume_name: str | None = None     # 持久卷名 → 实际卷 litmus-ws-<volume_name>
    host_dir: str | None = None        # 宿主目录 bind 挂载（单元 C）
    # TD-010：容器池网络模式，原样透传给 Docker（none/bridge/...），默认禁网。
    network_mode: str = "none"
    # TD-010：安装阶段自动放行——pip install 意图的执行改用有网（bridge）
    # 临时容器，用完即销毁不入池；其余执行仍走禁网池。默认关闭。
    allow_setup_network: bool = False

    @model_validator(mode="after")
    def _validate_workspace_fields(self) -> SandboxConfig:
        """校验工作区字段：卷名合法、双字段互斥。"""
        if self.volume_name is not None:
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", self.volume_name):
                raise ValueError(
                    f"volume_name 含非法字符：{self.volume_name!r}"
                    "（只允许字母、数字、_、.、-）"
                )
        if self.host_dir is not None and self.volume_name is not None:
            raise ValueError("host_dir 与 volume_name 互斥，只能配置其一")
        return self

    def is_bind_mode(self) -> bool:
        """是否处于 host_dir（bind）工作区模式。"""
        return self.host_dir is not None

    def resolve_human_approval(self, approval: HumanApprovalConfig) -> bool:
        """推导人工确认生效值（TD-015 保险二）。

        bind 模式且用户未显式配置时按 True 生效（默认保护）；
        其余情况尊重显式配置，未配置视为不启用。
        """
        if approval.enabled is not None:
            return approval.enabled
        return self.is_bind_mode()

    def resolve_security_enabled(self, security: SecurityConfig) -> bool:
        """推导安全策略生效值（TD-015 保险三）。

        bind 模式且用户未显式配置时按 True 生效；其余情况尊重显式配置。
        显式与否用 model_fields_set 判断（enabled 字段保持 bool 默认 False，
        不引入三态，兼容既有测试与行为）。
        """
        if "enabled" in security.model_fields_set:
            return security.enabled
        return self.is_bind_mode()


class ToolsConfig(BaseModel):
    """工具加载配置。

    enabled：显式启用的工具名列表。
      - None 表示启用所有默认工具（向后兼容）。
      - 列表为空 `[]` 表示不启用任何工具。
      - 列表中包含未知工具名时，会被忽略并记录警告。

    示例 YAML：
        tools:
          enabled:
            - sandbox_exec
            - finish
    """

    enabled: list[str] | None = None


class MCPServerConfig(BaseModel):
    """单个 MCP server 的配置（TD-016）。

    两种形态互斥且必居其一：
      - stdio：command + args（+ 可选 env），server 是宿主子进程；
      - SSE/HTTP：url（+ 可选 headers），server 是远程/本地 HTTP 服务。

    transport（同行评审 Y2）：显式传输判别，``stdio`` / ``sse`` / ``http``；
    None（默认）时维持启发式——有 command → stdio，url 路径以 ``/sse``
    结尾 → SSE，否则 → Streamable HTTP。显式配置时校验一致性：
    stdio 须有 command，sse/http 须有 url。

    trust：server 级信任开关。False（默认）时该 server 的全部工具进入
    人工确认清单；True 时豁免确认（等价于 pip install 级别的信任声明）。

    name 会进入工具名前缀 mcp__<name>__<tool>，故限制为字母/数字/_/-。
    """

    name: str
    command: str | None = None            # stdio 形态：启动命令
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None     # stdio 形态：附加环境变量
    url: str | None = None                # SSE/HTTP 形态：服务端点
    headers: dict[str, str] | None = None
    transport: Literal["stdio", "sse", "http"] | None = None  # 显式传输判别
    trust: bool = False

    @model_validator(mode="after")
    def _validate_server(self) -> MCPServerConfig:
        """校验 name 合法、command 与 url 互斥且必居其一、transport 一致。"""
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.name):
            raise ValueError(
                f"mcp server name 含非法字符：{self.name!r}"
                "（只允许字母、数字、_、-，将用于工具名前缀）"
            )
        if (self.command is None) == (self.url is None):
            raise ValueError(
                f"mcp server {self.name!r}：command 与 url 互斥且必居其一"
            )
        if self.transport == "stdio" and self.command is None:
            raise ValueError(
                f"mcp server {self.name!r}：transport=stdio 必须配置 command"
            )
        if self.transport in ("sse", "http") and self.url is None:
            raise ValueError(
                f"mcp server {self.name!r}：transport={self.transport} 必须配置 url"
            )
        return self


class MCPConfig(BaseModel):
    """MCP（Model Context Protocol）工具接入配置（TD-016）。

    ⚠️ 供应链风险：MCP server 是宿主进程/远程服务，其工具在宿主执行、
    不经沙箱——配置即信任声明。默认全部工具需人工确认（trust 豁免）。

    tool_timeout：单次 MCP 工具调用的强制超时（秒），asyncio.wait_for
    外层兜底，防 server 僵死（SDK 已知 cancel 不保证送达）。
    degrade_ttl（TD-019）：server 调用超时/失败后的降级冷却秒数——
    TTL 内对该 server 的调用快速失败；TTL 过期后下一次调用先惰性重连
    该 server，成功则恢复并正常执行，失败则刷新降级时间戳继续快速失败
    （纯惰性，无后台线程/定时任务）。
    servers：server 列表；为空或缺省 mcp 段时完全不激活。
    """

    tool_timeout: int = 30
    degrade_ttl: int = 60
    servers: list[MCPServerConfig] = Field(default_factory=list)


class AgentConfig(BaseModel):
    """顶层配置 —— 聚合所有子系统。

    使用 Pydantic 的 Field(default_factory=...) 模式：
      每个子配置都有默认值，但用户可以在 YAML 中按需覆盖。

    示例 YAML：
        llm:
          model: deepseek-chat
          temperature: 0.2
        agent:
          max_turns: 15
        sandbox:
          timeout: 60
        tools:
          enabled:
            - sandbox_exec
            - finish
    """

    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


def load_config(path: str | Path) -> AgentConfig:
    """从 YAML 文件加载配置，返回类型安全的 AgentConfig 对象。

    加载流程：
      1. 检查文件是否存在 → 不存在则抛 FileNotFoundError
      2. 用 yaml.safe_load() 解析（safe_load 防止 YAML 注入攻击）
      3. 将解析后的 dict 传给 AgentConfig(**raw)
      4. Pydantic 自动校验所有字段类型和默认值

    为什么用 safe_load 而不是 load？
      yaml.load() 可以执行任意 Python 代码（安全漏洞），
      yaml.safe_load() 只解析基本数据类型（dict、list、str、int 等）。

    参数：
      path: YAML 配置文件的路径（支持 str 或 pathlib.Path）

    返回：
      一个完整初始化的 AgentConfig 对象

    抛出：
      FileNotFoundError：文件不存在
      ValueError：YAML 格式损坏或字段类型不对
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")

    with open(path, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return AgentConfig(**raw)
