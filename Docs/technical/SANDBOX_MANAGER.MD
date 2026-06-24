# SandboxManager 技术设计

## 设计目标

为 AgentResearchAssistants 提供一个可独立测试的 Docker 沙箱执行层，满足起停、限额、断网与超时要求，并为后续 `run_code` 工具、`MLESolver._evaluate()`、ToolRegistry 权限控制提供稳定契约。

## 架构决策

1. **Protocol 隔离 Docker SDK**：`DockerClient`、`ContainerCollection`、`SandboxContainer` 只描述最小调用面。生产路径延迟导入 `docker.from_env()`；测试路径注入 fake client。
2. **spawn 占用并发槽，teardown 释放**：`BoundedSemaphore` 以 `ResourceLimits.max_concurrent_containers` 控制同时存在的容器数量，避免评估阶段无限扩容。
3. **结构化执行结果**：`run()` 不把超时、OOM、非零退出直接抛给上层，而是返回 `ExecResult`，由 solver 把错误反馈给下一轮修复。
4. **安全默认值集中配置**：网络、用户、工作目录、idle command、CPU/内存限额来自 `Settings`，通过环境变量覆盖。
5. **超时由 Harness 管控**：Docker exec 是阻塞调用，manager 使用线程池 + `future.result(timeout=...)` 控制等待时间，超时后 kill 容器并返回 `RunStatus.TIMEOUT`。

## 接口契约

```python
manager = SandboxManager()
handle = manager.spawn(SandboxSpec(mounts=(Mount(host, "/workspace/project"),)))
try:
    result = manager.run(handle, ["python", "main.py"], timeout_s=60)
finally:
    manager.teardown(handle)
```

`ExecResult.status` 语义：

| status | 触发条件 | 上层处理 |
|---|---|---|
| `success` | exit_code 为 0 且未 OOM | 解析指标或制品 |
| `failed` | 非零退出或 exec 调用异常 | 反馈 stderr/stdout 给 solver |
| `timeout` | 超过命令超时 | 作为可恢复错误反馈 |
| `oom` | Docker state 标记 OOMKilled | 作为可恢复错误反馈，可调低资源或修代码 |

## Docker 参数映射

| 配置 | Docker run 参数 |
|---|---|
| `limits.container_mem_mb` | `mem_limit="{mb}m"` |
| `limits.container_cpus` | `nano_cpus=int(cpus * 1e9)` |
| `docker.network_policy == "none"` | `network_disabled=True` |
| `docker.run_as_non_root` | `user=docker.non_root_user` |
| `docker.workdir` | `working_dir` 与 exec `workdir` |
| `SandboxSpec.mounts` | `volumes={host: {bind, mode}}` |

## 后续扩展点

- `network_policy="whitelist"` 当前仅保留配置入口，后续可接入专用 Docker network 或 egress proxy。
- 后续 ToolRegistry 的 `run_code` 工具应只暴露 `SandboxManager.run()` 能力，不暴露宿主机 shell。
- 可增加真实 Docker 集成测试，并用 pytest marker 与 fake 单测分离。
