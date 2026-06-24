# SolverEngine：MLESolver propose→evaluate→select 闭环

状态：✅ 已实现并通过验证（ruff / mypy strict / 60 个 pytest 全绿）。

## Context

里程碑 1-3 完成后，系统具备数据层、Docker 沙箱与角色化 Agent 封装。本里程碑在此基础上实现 SolverEngine：`MLEngineer` Agent 反复提议代码改进、沙箱执行评估、按 score 择优写入 Blackboard，形成自动迭代优化闭环。对标架构设计 §4.1（实验阶段控制流）。

## 关键设计决策

1. **`SolverBase` 抽象基类**：定义 `solve(initial_code) → SolveResult`，保持 solver 层可替换（MLESolver / PaperSolver 共用接口）。
2. **`EditCommand`**：agent 输出的最小结构——`code`（全量新代码）+ `description`。agent 直接返回新代码而非 diff，避免 apply 逻辑复杂化。
3. **score 解析**：从 stdout 末尾 JSON 行提取 `{"score": x}`，与沙箱输出格式解耦，agent 与 solver 可独立迭代。
4. **parse 兜底**：agent 输出解析失败时回退到原代码，确保迭代不中断。
5. **Blackboard 写入**：仅在 score 提升时写 `code.main`（CAS）；每次迭代无条件追加 `runs.history`，便于事后分析。

## 交付物

| 文件 | 内容 |
|------|------|
| `agent_research/harness/solver/__init__.py` | 导出 `EditCommand / MLESolver / SolveResult / SolverBase` |
| `agent_research/harness/solver/base.py` | `SolveResult` + `SolverBase` 抽象基类 |
| `agent_research/harness/solver/mle.py` | `MLESolver`（propose/evaluate/select 循环）+ `_parse_score` |
| `tests/test_solver.py` | 7 个单测（收敛、迭代限制、Blackboard 写入、历史追加、parse 兜底） |

## 验证方式

```bash
pytest -q           # 60 passed
ruff check .        # All checks passed
mypy agent_research # Success (strict)
```

## 后续里程碑衔接

- 里程碑 5（MessageBus + dialogue）：`MLESolver` 不依赖 MessageBus，可并行开发。
- 里程碑 6（Orchestrator）：`Orchestrator` 将调用 `MLESolver.solve()` 作为实验阶段核心节点。
- `PaperSolver`（里程碑 7）：继承 `SolverBase`，复用相同 propose→evaluate→select 骨架。
