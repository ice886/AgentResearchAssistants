"""本地 subprocess 执行客户端，无需 Docker daemon，用于开发/演示。

实现 DockerClient / SandboxContainer 协议，将容器操作转为本地 subprocess + tmpdir。
安全性：无隔离，仅用于开发环境，不得在生产中使用。
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any


@dataclass
class _LocalExecResult:
    exit_code: int
    output: tuple[bytes, bytes]


class _LocalContainer:
    def __init__(self, workdir: str) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="ar_local_")
        self.id = f"local-{id(self)}"
        self._workdir_hint = workdir
        self._killed = False

    def exec_run(
        self,
        cmd: Any,
        *,
        demux: bool = True,
        workdir: str | None = None,
    ) -> _LocalExecResult:
        if self._killed:
            return _LocalExecResult(-1, (b"", b"container killed"))
        cwd = self._tmpdir
        if isinstance(cmd, (list, tuple)):
            result = subprocess.run(list(cmd), capture_output=True, cwd=cwd, timeout=60)
        else:
            result = subprocess.run(
                str(cmd), shell=True, capture_output=True, cwd=cwd, timeout=60
            )
        return _LocalExecResult(result.returncode, (result.stdout, result.stderr))

    def kill(self) -> None:
        self._killed = True

    def remove(self, *, force: bool = True) -> None:
        pass

    def reload(self) -> None:
        pass

    @property
    def attrs(self) -> dict[str, Any]:
        return {}


class _LocalContainers:
    def run(self, image: str, command: Any, **kwargs: Any) -> _LocalContainer:
        workdir = str(kwargs.get("working_dir", "/workspace"))
        return _LocalContainer(workdir)


class LocalDockerClient:
    """无 Docker 的本地执行客户端（仅开发/演示用，无安全隔离）。"""

    containers: _LocalContainers = _LocalContainers()
