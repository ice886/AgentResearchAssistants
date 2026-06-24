# PaperSolver + Reviewer：LaTeX 改稿闭环

状态：✅ 已实现并通过验证（ruff / mypy strict / 96 个 pytest 全绿）。

## Context

延续 MLESolver（代码迭代），本里程碑实现论文改稿闭环：`PHD/POSTDOC` 作者 agent 反复改进草稿，`REVIEWER` agent 从四个维度（quality / clarity / originality / significance）打分，择优写入 Blackboard，直到平均分 ≥ threshold 或耗尽迭代。

## 关键设计决策

1. **复用 `EditCommand`**：作者 agent 输出 `{"code": "<latex>"}` 与 MLESolver 完全同构，`_propose` 逻辑一致，无需新数据结构。
2. **`_evaluate` 调 Reviewer RoleAgent**：输出 `{"dims": {...}, "comments": "..."}`；`_parse_review` 优先解析 `ReviewDims` 求均值，降级到 `score` 标量，再降级到 `None`。
3. **Blackboard 写入两个 namespace**：`paper.main`（PaperDraft）仅在得分提升时写入；`reviews.main`（ReviewSet）每轮追加，保留全部评审历史。
4. **不依赖 LaTeX 编译**：编译步骤留到 M8 e2e；`compile_status` 字段暂设 `"ok"`，不影响 schema。

## 交付物

| 文件 | 内容 |
|------|------|
| `agent_research/harness/solver/paper.py` | `PaperSolver` + `_parse_review` |
| `agent_research/harness/solver/__init__.py` | 新增 `PaperSolver` 导出 |
| `tests/test_paper_solver.py` | 9 个单测 |

## 验证方式

```bash
pytest -q           # 96 passed
ruff check .        # All checks passed
mypy agent_research # Success (strict)
```

## 后续里程碑衔接

- 里程碑 8（e2e 冒烟）：将 `PaperSolver.solve()` 作为 StateGraph paper 阶段的 handler 注入 `Orchestrator`，串通三阶段端到端。
