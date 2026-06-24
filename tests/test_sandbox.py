"""sandbox.py 单测：生命周期、限额、断网、超时、OOM 与幂等清理。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agent_research.config import DockerConfig, ResourceLimits, Settings
from agent_research.harness.enums import RunStatus
from agent_research.harness.sandbox import (
    Mount,
    SandboxCapacityError,
    SandboxConfigError,
    SandboxManager,
    SandboxSpec,
)


@dataclass
class FakeExecRunResult:
    exit_code: int | None
    output: bytes | str | tuple[bytes | str | None, bytes | str | None] | None


class FakeContainer:
    def __init__(
        self,
        *,
        result: FakeExecRunResult | None = None,
        delay_s: float = 0,
        oom_killed: bool = False,
        fail_remove_once: bool = False,
    ) -> None:
        self.id = "container-1"
        self.result = result or FakeExecRunResult(0, (b"ok", b""))
        self.delay_s = delay_s
        self.killed = False
        self.removed = False
        self.remove_calls = 0
        self.exec_calls: list[tuple[Any, dict[str, Any]]] = []
        self.attrs: dict[str, Any] = {"State": {"OOMKilled": oom_killed}}
        self._fail_remove_once = fail_remove_once

    def exec_run(self, cmd: Any, **kwargs: Any) -> FakeExecRunResult:
        self.exec_calls.append((cmd, kwargs))
        if self.delay_s:
            time.sleep(self.delay_s)
        return self.result

    def kill(self) -> None:
        self.killed = True

    def remove(self, *, force: bool = True) -> None:
        self.remove_calls += 1
        if self._fail_remove_once and self.remove_calls == 1:
            raise RuntimeError("remove failed")
        self.removed = force

    def reload(self) -> None:
        return None


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self.container = container
        self.run_calls: list[tuple[str, Any, dict[str, Any]]] = []

    def run(self, image: str, command: Any, **kwargs: Any) -> FakeContainer:
        self.run_calls.append((image, command, kwargs))
        return self.container


class FakeDockerClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainers(container)


def _settings(**kwargs: Any) -> Settings:
    return Settings(
        limits=ResourceLimits(
            container_cpus=1.5,
            container_mem_mb=256,
            container_timeout_s=10,
            max_concurrent_containers=1,
        ),
        docker=DockerConfig(**kwargs),
    )


def test_spawn_passes_security_limits_network_and_mounts(tmp_path: Path):
    container = FakeContainer()
    client = FakeDockerClient(container)
    manager = SandboxManager(settings=_settings(), client=client)

    handle = manager.spawn(
        SandboxSpec(
            image_tag="custom:image",
            mounts=(Mount(tmp_path, "/workspace/project", "ro"),),
            environment={"A": "B"},
        )
    )

    assert handle.id == "container-1"
    image, command, kwargs = client.containers.run_calls[0]
    assert image == "custom:image"
    assert command == "sleep infinity"
    assert kwargs["detach"] is True
    assert kwargs["network_disabled"] is True
    assert kwargs["user"] == "1000:1000"
    assert kwargs["mem_limit"] == "256m"
    assert kwargs["nano_cpus"] == 1_500_000_000
    assert kwargs["environment"] == {"A": "B"}
    assert kwargs["volumes"] == {
        str(tmp_path.resolve()): {"bind": "/workspace/project", "mode": "ro"}
    }
    manager.teardown(handle)


def test_spawn_capacity_released_after_teardown():
    container = FakeContainer()
    manager = SandboxManager(settings=_settings(), client=FakeDockerClient(container))

    first = manager.spawn()
    with pytest.raises(SandboxCapacityError):
        manager.spawn()

    manager.teardown(first)
    second = manager.spawn()
    manager.teardown(second)


def test_run_success_decodes_demuxed_output_and_uses_workdir():
    container = FakeContainer(result=FakeExecRunResult(0, (b"hello", b"")))
    manager = SandboxManager(
        settings=_settings(workdir="/safe"),
        client=FakeDockerClient(container),
    )
    handle = manager.spawn()

    result = manager.run(handle, ["python", "main.py"])

    assert result.status == RunStatus.SUCCESS
    assert result.stdout == "hello"
    assert result.stderr == ""
    assert result.exit_code == 0
    cmd, kwargs = container.exec_calls[0]
    assert cmd == ["python", "main.py"]
    assert kwargs["demux"] is True
    assert kwargs["workdir"] == "/safe"
    manager.teardown(handle)


def test_run_nonzero_exit_is_failed():
    container = FakeContainer(result=FakeExecRunResult(2, (b"", b"boom")))
    manager = SandboxManager(settings=_settings(), client=FakeDockerClient(container))
    handle = manager.spawn()

    result = manager.run(handle, "pytest")

    assert result.status == RunStatus.FAILED
    assert result.stderr == "boom"
    assert result.exit_code == 2
    manager.teardown(handle)


def test_run_timeout_kills_container_and_returns_recoverable_result():
    container = FakeContainer(delay_s=0.05)
    manager = SandboxManager(settings=_settings(), client=FakeDockerClient(container))
    handle = manager.spawn()

    result = manager.run(handle, "sleep 10", timeout_s=0.001)

    assert result.status == RunStatus.TIMEOUT
    assert result.timed_out is True
    assert result.exit_code is None
    assert container.killed is True
    manager.teardown(handle)


def test_run_oom_maps_to_oom_status():
    container = FakeContainer(
        result=FakeExecRunResult(137, (b"", b"killed")),
        oom_killed=True,
    )
    manager = SandboxManager(settings=_settings(), client=FakeDockerClient(container))
    handle = manager.spawn()

    result = manager.run(handle, "python main.py")

    assert result.status == RunStatus.OOM
    assert result.oom_killed is True
    manager.teardown(handle)


def test_teardown_is_idempotent_and_retries_after_remove_failure():
    container = FakeContainer(fail_remove_once=True)
    manager = SandboxManager(settings=_settings(), client=FakeDockerClient(container))
    handle = manager.spawn()

    manager.teardown(handle)
    manager.teardown(handle)

    assert container.killed is True
    assert container.removed is True
    assert container.remove_calls == 3


def test_invalid_network_policy_releases_capacity():
    container = FakeContainer()
    settings = _settings(network_policy="bridge")
    manager = SandboxManager(settings=settings, client=FakeDockerClient(container))

    with pytest.raises(SandboxConfigError):
        manager.spawn()

    settings.docker.network_policy = "none"
    handle = manager.spawn(SandboxSpec(image_tag="ok:image"))
    manager.teardown(handle)
