# Orchestrator + Workflow + CheckpointGate

状态：✅ 已实现并通过验证（ruff / mypy strict / 80 个 pytest 全绿）。

## Context

里程碑 1-5 完成数据层、沙箱、Agent、Solver、MessageBus 后，本里程碑实现编排核心：`StateGraph` 驱动 `Orchestrator` 串起各阶段，`CheckpointGate` 在关键节点等待人工决议，并通过读取 `decisions.main` 支持 resume-safe 跳过已确认检查点。

## 关键设计决策

1. **StateGraph 纯数据结构**：有序 `Node` 序列 + O(1) id→index，不依赖 SDK 或 Agent。handler 作为 zero-arg callable 注入，编排层与执行层解耦。
2. **线性驱动，无条件转移**：当前阶段为线性序列（照 §9 里程碑顺序），转移条件不依赖外部状态——简化实现，为 M8 e2e 扩展留口。
3. **CheckpointGate 可注入**：`decision_fn` 完全可替换；`enabled=False` 全局短路为 auto-approve（纯自动基准模式）。
4. **Resume-safe via Blackboard**：Orchestrator 启动时读 `decisions.main`，已 `approve` 的 checkpoint_id 直接跳过，不重触 gate。
5. **每节点结束即 snapshot**：非 checkpoint 节点执行后立即调 `Blackboard.snapshot()`，满足"全程制品落盘"要求。

## 交付物

| 文件 | 内容 |
|------|------|
| `agent_research/workflow/__init__.py` | 导出 `Node / StateGraph` |
| `agent_research/workflow/pipeline.py` | `Node`（dataclass）+ `StateGraph`（有序序列 + 查找） |
| `agent_research/harness/checkpoint.py` | `CheckpointGate`（gate / enabled / decision_fn）+ `_auto_approve` |
| `agent_research/harness/orchestrator.py` | `Orchestrator`（run / resume-safe）+ `RunResult` |
| `tests/test_orchestrator.py` | 11 个单测（节点顺序、approve/reject、resume、Blackboard 写入等） |

## 验证方式

```bash
pytest -q           # 80 passed
ruff check .        # All checks passed
mypy agent_research # Success (strict)
```

## 后续里程碑衔接

- 里程碑 7（PaperSolver + Reviewer）：作为 StateGraph 的 paper 阶段节点注入 handler。
- 里程碑 8（预算/恢复/e2e 冒烟）：`Orchestrator.run()` 接收真实 RoleAgent handler，串通三阶段端到端。
