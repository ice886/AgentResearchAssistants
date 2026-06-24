# 预算/恢复/e2e 冒烟

状态：✅ 已实现并通过验证（ruff / mypy strict / 97 个 pytest 全绿）。

## Context

全部功能模块就绪后，本里程碑补全 `BudgetController` 并用一个 e2e 冒烟测试串通三阶段 StateGraph，验证从 `lit_review → plan → experiment → paper` 的完整流水线：四个组件（MLESolver/PaperSolver/MessageBus/Orchestrator）协同工作，CheckpointGate 自动通过，Blackboard 持有全部制品，BudgetController 正确计费。

## 关键设计决策

1. **BudgetController 按 (role, phase) 双维度计费**：`by_role` + `by_phase` 分开记账，`report()` 返回不可变 `CostBreakdown`，便于后续分析。
2. **`check(scope)` 双模式**：无 scope → 全局检查；传 phase 名 → 该阶段独立检查（为阶段级限额留口）。
3. **e2e 冒烟全用 fake**：fake Docker client + fake SDK agent，零网络依赖，< 0.1s 完成，可在 CI 中常态运行。
4. **单一 smoke test 覆盖所有里程碑**：一个测试验证 8 个里程碑的集成正确性，比多个集成测试更能发现跨模块回归。

## 交付物

| 文件 | 内容 |
|------|------|
| `agent_research/harness/budget.py` | `BudgetController`（charge / check / spent / report）+ `CostBreakdown` + `BudgetExceededError` |
| `tests/test_e2e_smoke.py` | 端到端冒烟：三阶段四检查点全流程验证 |

## 验证方式

```bash
pytest -q           # 97 passed
ruff check .        # All checks passed
mypy agent_research # Success (strict)
```

## 系统完成状态

所有 8 个里程碑已全部实现：

| # | 模块 | 核心交付 |
|---|------|---------|
| 1 | 骨架+数据层 | models / blackboard / config |
| 2 | SandboxManager | Docker 生命周期/限额/断网 |
| 3 | RoleAgent+ToolRegistry | SDK subagent 封装/工具授权 |
| 4 | SolverEngine | MLESolver propose→evaluate→select |
| 5 | MessageBus | dialogue 多回合磋商收敛 |
| 6 | Orchestrator+Workflow | StateGraph / CheckpointGate / resume-safe |
| 7 | PaperSolver+Reviewer | LaTeX 改稿 + 四维评分闭环 |
| 8 | 预算/恢复/e2e | BudgetController + 三阶段端到端冒烟 |
