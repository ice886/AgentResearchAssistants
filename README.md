# AgentResearchAssistants

研究 Agent 系统（Agent Laboratory 风格）：自动写实验代码、跑实验、撰写论文的多智能体系统。

## 当前模块

- `agent_research.config`：集中配置路径、资源限额、Docker 与模型配置。
- `agent_research.agents.base`：`RoleAgent` 封装，按角色注入模型、prompt 与授权工具。
- `agent_research.harness.blackboard`：版本化 Blackboard，提供 CAS、snapshot/restore 与上下文切片。
- `agent_research.harness.sandbox`：Docker `SandboxManager`，提供沙箱起停、CPU/内存限额、默认断网、非 root、命令超时与 OOM 结果映射。
- `agent_research.harness.tools`：`ToolRegistry` 工具注册与按角色授权，`run_code` 强制路由到 SandboxManager。
- `agent_research.harness.solver.paper`：`PaperSolver` 作者/reviewer 迭代改稿，生成带完整 `\documentclass` 结构的合法 LaTeX。
- `agent_research.harness.solver.mle`：`MLESolver` 代码迭代求解，在沙箱内运行并评分。
- `agent_research.workflow`：三阶段四检查点 pipeline（lit_review → plan → experiment → paper）。

## 验证

```bash
ruff check .
mypy agent_research
pytest -q
```
