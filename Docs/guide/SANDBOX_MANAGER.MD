# SandboxManager 现状总结

## 模块定位

`SandboxManager` 位于 Harness 层，是系统代码执行的唯一入口。执行类工具、MLE Solver 或后续 ToolRegistry 不应直接调用宿主机命令，而应通过 `SandboxManager.spawn()` / `run()` / `teardown()` 路由到 Docker 沙箱。

## 核心文件

| 文件 | 职责 |
|---|---|
| `agent_research/harness/sandbox.py` | 沙箱生命周期、资源限额、断网、非 root、超时、OOM 结果归类 |
| `agent_research/config.py` | `ResourceLimits` 与 `DockerConfig` 集中配置 |
| `tests/test_sandbox.py` | fake Docker client 单测，不依赖真实 Docker daemon |

## 公开接口

- `SandboxSpec`：创建容器的输入，包含镜像 tag、挂载、环境变量。
- `Mount`：宿主路径到容器路径的挂载描述。
- `SandboxHandle`：已启动容器句柄，封装容器对象与并发槽释放状态。
- `ExecResult`：单次命令执行结果，包含 stdout、stderr、exit_code、`RunStatus`、耗时、timeout/OOM 标记。
- `SandboxManager.spawn()`：启动长驻容器，占用最大并发槽。
- `SandboxManager.run()`：容器内执行命令，超时/OOM/非零退出转为结构化结果。
- `SandboxManager.teardown()`：幂等清理容器并释放并发槽。

## 安全默认值

- 默认 `AR_DOCKER__NETWORK_POLICY=none`，创建容器时传入 `network_disabled=True`。
- 默认 `AR_DOCKER__RUN_AS_NON_ROOT=true`，使用 `AR_DOCKER__NON_ROOT_USER=1000:1000`。
- 默认传入 `mem_limit` 与 `nano_cpus`，来源于 `ResourceLimits`。
- `run()` 默认超时来自 `AR_LIMITS__CONTAINER_TIMEOUT_S`，超时后 kill 容器并返回 `RunStatus.TIMEOUT`。
- 容器 `State.OOMKilled=true` 时返回 `RunStatus.OOM`，作为 solver 可恢复错误。

## 测试策略

Docker SDK 隔离在 `DockerClient` / `SandboxContainer` Protocol 后面。单测注入 fake client，验证 Docker 参数、并发槽、输出解析、超时 kill、OOM 映射与清理重试，不要求本机运行 Docker daemon。
