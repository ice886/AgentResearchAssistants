# CLAUDE.md

研究 Agent 系统（Agent Laboratory 风格）：自动写实验代码、跑实验、撰写论文的多智能体系统。
三层架构 = Workflow（阶段编排）· Harness（多智能体运行时）· Agent（角色化 SDK subagent）。
底层取向：Claude Agent SDK 编排 · 全自动 + 关键检查点 · Docker 沙箱执行。

详见 [Docs/architecture/设计方案.md](Docs/architecture/设计方案.md) 与 [Docs/architecture/架构设计.md](Docs/architecture/架构设计.md)。

## Key Protocols

### Task Type Classification

- **Plan**：新功能、设计、优化 → 输出 3-7 步，编码前先获批准，计划写入 `Docs/plan/`。
- **Fix**：bug、回归、报错 → 说明根因与修复范围，必要时记录到 `Docs/issue/fix/`。

### Knowledge Cache Protocol

为任务扫描代码前，先查：
- `Docs/guide/` —— 模块结构、调用链、机制等结构性知识缓存
- `Docs/technical/` —— 深度技术设计文档
- `Docs/feature/` —— 功能级描述

仅当上述不足时才扫描代码；扫描后更新这些文档。

### Git Commit Format

```
<type>(<scope>): <subject>
```

Types：`feat | fix | docs | style | refactor | test | chore`
Scopes：`harness | workflow | agents | solver | sandbox | blackboard | config`

## Critical Rules

- **代码执行只能经 SandboxManager** —— agent 不得直接触达宿主机；所有 `run_code` 类工具强制路由到 Docker 沙箱。
- **沙箱默认隔离** —— 非 root、`--network none`（或白名单）、CPU/内存/超时受限。执行 LLM 生成的代码前不得放宽这些约束，除非显式授权。
- **Blackboard 是唯一共享状态** —— agent 间不传明文长文本，一律走结构化消息 + Blackboard 引用；写入用乐观锁（CAS + 版本号）。
- **编排/求解/检查点不依赖 SDK** —— 保持 Harness 自研层与 Claude Agent SDK 解耦，便于替换底层。
- **全程制品落盘（resume-safe）** —— 每个节点结束即 snapshot；恢复时按 `decisions` 跳过已确认阶段，不重跑已完成阶段。

## Documentation Map

| Directory | Purpose |
|-----------|---------|
| `Docs/architecture/` | 系统设计与技术架构文档 |
| `Docs/guide/` | Agent 发现的结构性知识缓存 |
| `Docs/technical/` | Agent 撰写的深度技术设计文档 |
| `Docs/feature/` | 功能级描述 |
| `Docs/plan/` | 已批准的实现计划 |
| `Docs/issue/fix/` | 修复记录 |

## Environment & Configuration

- 集中配置在 `config.py`（路径、资源限额、模型、Docker 镜像 tag）。
- 实验在 Docker 沙箱内运行；基础镜像预装常用 ML 依赖，按 run 起停并清理中间产物。
- 制品输出到 `runs/<run_id>/`（blackboard / code / experiments / paper / logs / budget）。
- API key 等敏感信息走环境变量或 `.env`，不入库、不写入日志或 prompt。
