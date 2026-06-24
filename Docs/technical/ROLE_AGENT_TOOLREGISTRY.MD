# RoleAgent + ToolRegistry 技术设计

## 设计目标

实现 Agent 层与 Harness 工具层的最小可用契约：角色化 Agent 调用不直接依赖具体 SDK API，工具暴露遵循最小权限原则，执行类工具强制路由到 `SandboxManager`。

## 架构决策

1. **SDK Protocol 隔离**：`SDKAgentClient.run(invocation)` 是唯一 SDK 调用面。真实 Claude Agent SDK 后续由 adapter 适配，核心测试使用 fake SDK。
2. **RoleAgent 无共享状态**：`RoleAgent` 只封装角色、模型、prompt、工具和本次 `AgentTask`，共享状态仍由 Blackboard 引用负责。
3. **工具用 dataclass 承载 handler**：`ToolSpec` 是 frozen dataclass，可携带 callable handler、JSON-like input schema 与 metadata。
4. **授权集中在 ToolRegistry**：注册时绑定 `allowed_roles`，查询和调用都经 registry，避免 agent 自行决定工具可见性。
5. **执行工具安全路由**：`make_run_code_tool()` 内部只调用 `SandboxManager`，并用 `finally` 保证 teardown。

## 调用链

```python
registry = ToolRegistry()
registry.register(make_run_code_tool(sandbox), {RoleName.ML_ENGINEER})

agent = RoleAgent(RoleName.ML_ENGINEER, sdk, registry=registry, settings=settings)
result = agent.run(AgentTask(goal="run experiment", input_refs=["code.main"]))
```

`RoleAgent.run()` 构造：

```python
SDKInvocation(
    role=RoleName.ML_ENGINEER,
    model=settings.models.for_role(RoleName.ML_ENGINEER),
    system_prompt=prompt_for(RoleName.ML_ENGINEER),
    tools=tuple(registry.tools_for(RoleName.ML_ENGINEER)),
    task=task,
)
```

## 工具授权语义

| API | 行为 |
|---|---|
| `register(tool, allowed_roles)` | 工具名唯一；角色集合不能为空 |
| `tools_for(role)` | 返回该角色可见工具，供 SDK subagent 白名单注入 |
| `assert_allowed(role, tool_name)` | 越权抛 `ToolAuthorizationError` |
| `call(role, tool_name, payload)` | 授权检查后调用 handler |

## run_code Payload

| 字段 | 类型 | 说明 |
|---|---|---|
| `cmd` | `str | list[str]` | 必填，容器内命令 |
| `timeout_s` | `int | float | None` | 可选，覆盖默认命令超时 |
| `sandbox` | `SandboxSpec | None` | 可选，覆盖镜像、挂载、环境变量 |

返回值为 `ExecResult`，状态沿用 `RunStatus.success/failed/timeout/oom`。

## 后续扩展点

- 增加真实 Claude Agent SDK adapter，负责把 `ToolSpec` 转为 SDK tool 定义。
- 为工具 input_schema 增加运行时 JSON Schema 校验。
- 增加 prompt 文件加载机制，将当前内置 prompt 拆到独立 Markdown 模板。
