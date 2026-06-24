# SandboxManager：起停 / 限额 / 断网 / 超时

状态：已批准，待实现。

## 目标

在 Harness 层新增 `SandboxManager`，作为系统唯一代码执行入口，负责 Docker 沙箱的生命周期、安全隔离、资源限额、断网策略与超时控制。模块需独立可测，单测不依赖真实 Docker daemon。

## 执行计划

1. 设计 `agent_research/harness/sandbox.py`：定义 `SandboxManager`、`SandboxSpec`、`SandboxHandle`、`ExecResult`、错误类型，保持 Harness 独立、无 Workflow/Agent 反向依赖。
2. 接入配置：复用并必要扩展 `ResourceLimits` / `DockerConfig`，覆盖 CPU、内存、超时、最大并发、网络策略、非 root 用户。
3. 实现生命周期：`spawn()` 创建 Docker 容器，`run()` 执行命令并收集 stdout/stderr/exit/耗时/状态，`teardown()` 幂等清理。
4. 实现安全默认值：默认断网、非 root、资源限额、工作目录挂载白名单、超时后终止执行并返回可恢复错误。
5. 保证独立可测：抽象 Docker client/protocol，单测用 fake client，不依赖本机 Docker daemon；覆盖起停、限额参数、断网参数、超时、清理失败兜底。
6. 更新文档：开发后检查 `README.md`、`Docs/guide/` / `Docs/technical/` / `Docs/feature/`、`Docs/dailylog/` 是否需要更新。

## 关键影响点

- `harness`：新增核心执行隔离模块。
- `sandbox`：引入 Docker 生命周期、安全策略、超时语义。
- `config`：可能新增/细化 Docker 与资源配置字段。
- `tests`：新增无需真实 Docker 的独立单测。
- `docs`：沉淀 SandboxManager 设计与使用契约。

## 风险与依赖

- Docker SDK 若加入硬依赖会影响安装包；优先通过 client 协议隔离，让单测与核心逻辑不依赖真实 Docker。
- Python 层强制超时与 Docker exec 超时需要谨慎处理，避免容器残留。
- 非 root 用户策略依赖镜像内用户是否存在，默认使用可配置 user，后续可随基础镜像调整。
