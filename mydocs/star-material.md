# 简历 STAR 素材（从 docs/evaluation-log.md 迁出，本地保留）

> 迁出时间：2026-07-19，原因：公开仓库仅保留项目内容

## 简历 STAR 素材

### 6.1 工程规范与测试

> **S**：面试项目需要在短时间内展示完整的 Agent 工程能力。  
> **T**：构建具备自我纠错能力的代码沙箱 Agent，并保证代码质量。  
> **A**：采用 src-layout、Pydantic 配置、pytest + mypy + ruff 质量门禁、TDD 开发。  
> **R**：最终达到 566 个测试通过、44 个源文件 mypy 零错误、ruff 全绿，文档和示例均有测试守护防止腐烂。

### 6.2 真实 LLM 端到端能力

> **S**：需要验证 Agent 在真实 LLM 驱动下能否完成代码编写与验证任务。  
> **T**：使用 DeepSeek 端点运行端到端 Demo。  
> **A**：实现支持 OpenAI 兼容端点的 LLM Client，并修复环境变量优先级问题。  
> **R**：在 `deepseek-chat` 模型上 5 轮对话完成 fibonacci 函数编写与验证，证明了工具调用和自我纠错闭环可用。

### 6.3 安全意识

> **S**：LLM 生成的代码存在潜在安全风险。  
> **T**：在沙箱中隔离执行代码并配置策略引擎。  
> **A**：实现 Docker 沙箱后端（cgroup、seccomp、网络限制）和可配置的安全策略引擎 `PolicyEngine`。  
> **R**：工具调用前经过策略拦截，支持按资源/操作/参数粒度配置 allow/deny 规则。

### 6.4 可用性工程与架构抽象

> **S**：开发环境无法连接 Docker Hub，Docker 沙箱不可用，Coding Agent 的「写代码→改代码→运行验证」闭环断裂。  
> **T**：在不破坏既有 Docker 路径的前提下，让 Agent 在无 Docker 环境下恢复完整闭环。  
> **A**：引入 `SandboxBackend` Protocol 结构化抽象解耦工具层与具体后端；实现 `SubprocessSandboxBackend`（实例临时目录 workspace、POSIX 路径映射、`../` 逃逸防护、async 子进程执行）；通过 `create_sandbox_backend` 工厂让 `config.sandbox.backend` 真正生效；执行中发现 `file_list` 经 `execute_code` 绝对路径绕过映射，以后端可选能力 `list_dir` 修复。  
> **R**：新增 25 个测试（真实子进程执行、零 Docker 依赖），全量 566 passed、mypy 44 文件零错误；配置 `backend: subprocess` 即插即用，Docker 后端行为零变化。
