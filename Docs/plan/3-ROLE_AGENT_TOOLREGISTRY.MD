# RoleAgent + ToolRegistry

状态：已批准，待实现。

## 目标

新增 Agent 封装与工具授权层：`RoleAgent` 作为 Claude Agent SDK subagent 的轻量适配器，`ToolRegistry` 统一注册工具并按角色暴露最小权限工具集。执行类工具必须通过 `SandboxManager` 路由，agent 不得直接触达宿主机。

## 执行计划

1. 设计 Agent 层骨架：新增 `agent_research/agents/base.py` 与必要的 prompt 入口，定义 `RoleAgent`、`AgentTask`、`AgentResult`、SDK adapter/protocol，避免编排层绑定死到具体 SDK。
2. 实现 `ToolRegistry`：新增 `agent_research/harness/tools/registry.py`，定义 `ToolSpec`、工具权限、注册/查询/越权错误，`tools_for(role)` 返回最小权限工具集。
3. 接入安全工具路由：实现 `run_code` 工具封装，确保执行类工具只能调用 `SandboxManager`，不暴露宿主机 shell。
4. 接入配置与角色模型：复用 `ModelConfig.for_role()`，让 `RoleAgent` 按 `RoleName` 选择模型、system prompt、授权工具。
5. 独立单测：用 fake SDK client 和 fake tool 覆盖角色初始化、工具白名单注入、越权拒绝、run_code 路由到 sandbox、结构化结果返回。
6. 更新文档：开发后更新 `Docs/guide/`、`Docs/technical/`、`README.md`、`Docs/dailylog/`。

## 关键影响点

- `agents`：新增 RoleAgent 封装与 prompt 管理。
- `harness/tools`：新增 ToolRegistry 与工具契约。
- `sandbox`：执行类工具通过 SandboxManager 路由。
- `config`：复用现有 `ModelConfig`。
- `tests`：新增 fake SDK/fake tool 单测，不依赖真实 Claude Agent SDK 调用。
- `docs`：ToolRegistry 属于对外工具契约变更，需要更新技术文档。

## 风险与依赖

- Claude Agent SDK 的真实 Python API 可能变化；用 adapter/protocol 隔离，核心单测不依赖真实网络或 SDK。
- `run_code` 工具权限必须保守：默认只给 `ML_ENGINEER` / `SW_ENGINEER`。
- Prompt 文件和工具 schema 保持轻量，不在本里程碑提前实现 Orchestrator/MessageBus。
