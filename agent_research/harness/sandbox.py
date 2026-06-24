"""Docker 沙箱管理器：起停、资源限额、断网与超时。

SandboxManager 是系统唯一代码执行入口。Docker SDK 被隔离在可注入 client 协议后面，
因此核心生命周期与超时逻辑可用 fake client 独立单测，不依赖真实 Docker daemon。
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..config import DockerConfig, ResourceLimits, Settings, get_settings
from .enums import RunStatus

Command = str | Sequence[str]


class SandboxError(Exception):
    """Sandbox 相关错误基类。"""


class SandboxUnavailableError(SandboxError):
    """Docker client 不可用或 daemon 调用失败。"""


class SandboxCapacityError(SandboxError):
    """超过最大并发容器数。"""


class SandboxConfigError(SandboxError):
    """不安全或不支持的沙箱配置。"""


@runtime_checkable
class ExecRunResult(Protocol):
    """Docker SDK ``exec_run`` 返回值的最小协议。"""

    exit_code: int | None
    output: bytes | str | tuple[bytes | str | None, bytes | str | None] | None


@runtime_checkable
class SandboxContainer(Protocol):
    """SandboxManager 需要的容器最小协议。"""

    id: str

    def exec_run(
        self,
        cmd: Command,
        *,
        demux: bool = True,
        workdir: str | None = None,
    ) -> ExecRunResult | tuple[int | None, Any]:
        """在容器内执行命令。"""

    def kill(self) -> None:
        """强制停止容器。"""

    def remove(self, *, force: bool = True) -> None:
        """删除容器。"""

    def reload(self) -> None:
        """刷新容器属性。"""

    @property
    def attrs(self) -> Mapping[str, Any]:
        """容器属性，兼容 Docker SDK。"""


@runtime_checkable
class ContainerCollection(Protocol):
    def run(self, image: str, command: Command, **kwargs: Any) -> SandboxContainer:
        """创建并启动容器。"""


@runtime_checkable
class DockerClient(Protocol):
    containers: ContainerCollection


class ExecResult(BaseModel):
    """一次沙箱命令执行结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    status: RunStatus
    elapsed_s: float = Field(ge=0)
    timed_out: bool = False
    oom_killed: bool = False


@dataclass(frozen=True)
class Mount:
    """宿主目录到容器目录的挂载。"""

    host_path: Path
    container_path: str
    mode: str = "rw"


@dataclass(frozen=True)
class SandboxSpec:
    """创建沙箱容器所需的输入。"""

    image_tag: str | None = None
    mounts: tuple[Mount, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)


@dataclass
class SandboxHandle:
    """已启动的沙箱容器句柄。"""

    container: SandboxContainer
    spec: SandboxSpec
    _slot_released: bool = False

    @property
    def id(self) -> str:
        return self.container.id


class SandboxManager:
    """Docker 沙箱生命周期管理器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: DockerClient | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._executor = executor or ThreadPoolExecutor(
            max_workers=max(1, self._settings.limits.max_concurrent_containers)
        )
        self._owns_executor = executor is None
        self._slots = BoundedSemaphore(self._settings.limits.max_concurrent_containers)

    def spawn(self, spec: SandboxSpec | None = None) -> SandboxHandle:
        """启动一个长驻容器并返回句柄。"""
        spec = spec or SandboxSpec()
        if not self._slots.acquire(blocking=False):
            raise SandboxCapacityError("已达到最大并发沙箱容器数")

        docker = self._settings.docker
        limits = self._settings.limits
        try:
            security_kwargs = self._security_kwargs(docker, limits)
            container = self._docker_client().containers.run(
                spec.image_tag or docker.base_image_tag,
                docker.idle_command,
                detach=True,
                tty=False,
                working_dir=docker.workdir,
                environment=dict(spec.environment),
                volumes=self._volumes(spec.mounts),
                **security_kwargs,
            )
        except SandboxConfigError:
            self._slots.release()
            raise
        except Exception as e:
            self._slots.release()
            raise SandboxUnavailableError(f"启动沙箱失败: {e}") from e
        return SandboxHandle(container=container, spec=spec)

    def run(
        self,
        handle: SandboxHandle,
        cmd: Command,
        *,
        timeout_s: float | None = None,
    ) -> ExecResult:
        """在容器中执行命令；超时/OOM 作为可恢复结果返回。"""
        deadline = timeout_s or self._settings.limits.container_timeout_s
        started = time.monotonic()
        future = self._executor.submit(
            handle.container.exec_run,
            cmd,
            demux=True,
            workdir=self._settings.docker.workdir,
        )
        try:
            raw = future.result(timeout=deadline)
        except TimeoutError:
            self._kill_quietly(handle.container)
            return ExecResult(
                stdout="",
                stderr=f"command timed out after {deadline}s",
                exit_code=None,
                status=RunStatus.TIMEOUT,
                elapsed_s=time.monotonic() - started,
                timed_out=True,
            )
        except Exception as e:
            return ExecResult(
                stdout="",
                stderr=f"沙箱执行失败: {e}",
                exit_code=None,
                status=RunStatus.FAILED,
                elapsed_s=time.monotonic() - started,
            )

        exit_code, stdout, stderr = self._parse_exec_result(raw)
        oom_killed = self._oom_killed(handle.container)
        status = self._status(exit_code, oom_killed)
        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            status=status,
            elapsed_s=time.monotonic() - started,
            oom_killed=oom_killed,
        )

    def teardown(self, handle: SandboxHandle) -> None:
        """幂等回收容器与并发槽。"""
        try:
            handle.container.remove(force=True)
        except Exception:
            self._kill_quietly(handle.container)
            try:
                handle.container.remove(force=True)
            except Exception:
                pass
        finally:
            if not handle._slot_released:
                self._slots.release()
                handle._slot_released = True

    def close(self) -> None:
        """释放 manager 自有线程池。"""
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _docker_client(self) -> DockerClient:
        if self._client is not None:
            return self._client
        try:
            import docker  # type: ignore[import-untyped]
        except ImportError as e:
            raise SandboxUnavailableError(
                "未安装 Docker SDK；请安装 docker 包或注入 DockerClient"
            ) from e
        self._client = docker.from_env()
        return self._client

    @staticmethod
    def _volumes(mounts: tuple[Mount, ...]) -> dict[str, dict[str, str]]:
        return {
            str(m.host_path.resolve()): {"bind": m.container_path, "mode": m.mode}
            for m in mounts
        }

    @staticmethod
    def _security_kwargs(
        docker: DockerConfig,
        limits: ResourceLimits,
    ) -> dict[str, Any]:
        if docker.network_policy not in {"none", "whitelist"}:
            raise SandboxConfigError(
                f"不支持的 network_policy={docker.network_policy!r}"
            )
        kwargs: dict[str, Any] = {
            "network_disabled": docker.network_policy == "none",
            "mem_limit": f"{limits.container_mem_mb}m",
            "nano_cpus": int(limits.container_cpus * 1_000_000_000),
        }
        if docker.run_as_non_root:
            kwargs["user"] = docker.non_root_user
        return kwargs

    @staticmethod
    def _parse_exec_result(
        raw: ExecRunResult | tuple[int | None, Any],
    ) -> tuple[int | None, str, str]:
        if isinstance(raw, tuple):
            exit_code, output = raw
        else:
            exit_code, output = raw.exit_code, raw.output

        if isinstance(output, tuple):
            stdout_raw, stderr_raw = output
        else:
            stdout_raw, stderr_raw = output, None
        return exit_code, _decode(stdout_raw), _decode(stderr_raw)

    @staticmethod
    def _status(exit_code: int | None, oom_killed: bool) -> RunStatus:
        if oom_killed:
            return RunStatus.OOM
        if exit_code == 0:
            return RunStatus.SUCCESS
        return RunStatus.FAILED

    @staticmethod
    def _oom_killed(container: SandboxContainer) -> bool:
        try:
            container.reload()
            state = container.attrs.get("State", {})
            return bool(state.get("OOMKilled"))
        except Exception:
            return False

    @staticmethod
    def _kill_quietly(container: SandboxContainer) -> None:
        try:
            container.kill()
        except Exception:
            pass


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
