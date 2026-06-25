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

## 快速开始

**安装依赖**

```bash
pip install -e .
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
```

**启动新实验**

```bash
# 交互模式（每个检查点暂停等待人工确认）
python -m agent_research run --idea "Compare CoT vs ReAct on GSM8K"

# 全自动模式（跳过所有检查点）
python -m agent_research run --idea "Compare CoT vs ReAct on GSM8K" --auto

# 指定 run_id
python -m agent_research run --idea "..." --run-id my-exp-01
```

**恢复中断的实验**

```bash
python -m agent_research resume --run-id <run_id>
python -m agent_research resume --run-id <run_id> --auto
```

**制品输出**

```
runs/<run_id>/
├── blackboard.json      # 全量共享状态快照
├── budget.json          # token 用量报告
├── code/main.py         # 生成的实验代码
├── paper/main.tex       # 生成的 LaTeX 论文
└── logs/phases.json     # 阶段执行日志
```

编译论文：

```bash
pdflatex runs/<run_id>/paper/main.tex
```

## 验证

```bash
ruff check .
mypy agent_research
pytest -q
```
