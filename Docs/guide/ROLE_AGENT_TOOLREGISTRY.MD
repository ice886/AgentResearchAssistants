# RoleAgent + ToolRegistry 现状总结

## 模块定位

`RoleAgent` 位于 Agent 层，负责把角色、模型、system prompt 与授权工具打包成一次 SDK subagent 调用。`ToolRegistry` 位于 Harness 层，负责统一注册工具并按角色返回最小权限工具集。

## 核心文件

| 文件 | 职责 |
|---|---|
| `agent_research/agents/base.py` | `RoleAgent`、`AgentTask`、`AgentResult`、`SDKInvocation`、`SDKAgentClient` 协议 |
| `agent_research/agents/prompts/__init__.py` | 内置角色 system prompt 与 `prompt_for(role)` |
| `agent_research/harness/tools/registry.py` | `ToolRegistry`、`ToolSpec`、授权错误、`make_run_code_tool()` |
| `tests/test_role_agent.py` | fake SDK 单测，验证模型/prompt/工具注入 |
| `tests/test_tool_registry.py` | 工具注册、授权、越权拒绝与 sandbox 路由单测 |

## 核心契约

- `ToolRegistry.register(tool, allowed_roles)`：注册工具并绑定允许角色。
- `ToolRegistry.tools_for(role)`：返回角色可见工具子集。
- `ToolRegistry.call(role, tool_name, payload)`：调用前强制授权检查，越权抛 `ToolAuthorizationError`。
- `RoleAgent.run(task)`：构造 `SDKInvocation(role, model, system_prompt, tools, task)` 并交给注入的 `SDKAgentClient`。
- `make_run_code_tool(sandbox)`：创建 `run_code` 工具，内部只调用 `SandboxManager.spawn()` / `run()` / `teardown()`。

## 安全约束

- `run_code` 不暴露宿主机 shell，只接受命令 payload 并通过 `SandboxManager` 执行。
- 默认授权建议只给 `RoleName.ML_ENGINEER` 与 `RoleName.SW_ENGINEER`。
- 真实 Claude Agent SDK 被隔离在 `SDKAgentClient` Protocol 后面，单测不依赖网络或真实 SDK。

## 后续衔接

- Orchestrator 创建任务时可按角色实例化 `RoleAgent`，并注入同一个 `ToolRegistry`。
- MessageBus/dialogue 可复用 `AgentTask.input_refs` 与 `context`，由上层负责 Blackboard slice。
- SolverEngine 的执行评估工具应从 registry 获取 `run_code`，不要直接触达 Docker 或宿主机。
