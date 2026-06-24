# MessageBus + dialogue：计划磋商收敛

状态：✅ 已实现并通过验证（ruff / mypy strict / 69 个 pytest 全绿）。

## Context

里程碑 4 完成 MLESolver 闭环后，本里程碑实现 agent 间通信与多回合磋商收敛机制。对标架构设计 §3.3 与 §4.2（计划磋商控制流）：`MessageBus.dialogue([PhD, Postdoc], topic=plan, max_turns=N)` 驱动 PhD↔Postdoc 交替，Postdoc 发出 `intent=approve` 即收敛。

## 关键设计决策

1. **`send()` 仅落审计日志**：消息不入 Blackboard，保持两者职责分离（Blackboard 存制品，MessageBus 存通信记录）。
2. **`dialogue()` 无状态驱动**：交替调用 `RoleAgent.run()`，每轮将上一条消息作为 context 传入；agent 的 `output` dict 决定新消息的 `intent` / `blackboard_refs` / `payload`。
3. **`intent` 解析宽容**：未知 intent 值降级为 `REPORT`，确保 dialogue 不因 agent 输出格式问题中断。
4. **`converge_fn` 可注入**：标准实现 `approve_on_intent` 检测 `intent=approve`；调用方可替换为自定义逻辑（如分数阈值）。
5. **`Transcript` 不可变**：`frozen=True` Pydantic 模型，与 Blackboard Artifact 风格一致。

## 交付物

| 文件 | 内容 |
|------|------|
| `agent_research/harness/messagebus.py` | `MessageBus`（send / audit_log / dialogue）+ `Transcript` + `approve_on_intent` |
| `tests/test_messagebus.py` | 9 个单测（send、audit_log 隔离、收敛、全程迭代、交替角色、审计日志、intent 兜底、空参数、不可变性） |

## 验证方式

```bash
pytest -q           # 69 passed
ruff check .        # All checks passed
mypy agent_research # Success (strict)
```

## 后续里程碑衔接

- 里程碑 6（Orchestrator + Workflow）：Orchestrator 在检查点②前调用 `bus.dialogue([phd, postdoc], ...)` 完成计划磋商。
- 里程碑 7（PaperSolver + Reviewer）：Reviewer 多人评分可走 `dialogue([reviewer1, reviewer2], ...)` 或直接 fan-out；`MessageBus` 已就绪。
