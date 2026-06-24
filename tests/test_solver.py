"""MLESolver 单测：收敛、迭代限制、Blackboard 写入、parse 兜底。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agent_research.agents.base import AgentResult, RoleAgent, SDKInvocation
from agent_research.config import RunPaths
from agent_research.harness.blackboard import Blackboard
from agent_research.harness.enums import RoleName
from agent_research.harness.models import CodeArtifact, RunHistory
from agent_research.harness.sandbox import SandboxManager
from agent_research.harness.solver.mle import MLESolver, _parse_score
from agent_research.harness.tools import ToolRegistry

# ─── fakes ────────────────────────────────────────────────────────────────────


class _FakeSDK:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self._outputs = outputs
        self._idx = 0

    def run(self, inv: SDKInvocation) -> AgentResult:
        data = self._outputs[self._idx % len(self._outputs)]
        self._idx += 1
        return AgentResult(content="", output=data)


@dataclass
class _FakeExec:
    exit_code: int | None
    output: bytes | str | tuple[bytes | str | None, bytes | str | None] | None


class _FakeContainer:
    id = "c1"

    def __init__(self, stdout: bytes = b'{"score": 0.85}') -> None:
        self._stdout = stdout

    def exec_run(self, cmd: Any, **kwargs: Any) -> _FakeExec:
        return _FakeExec(0, (self._stdout, b""))

    def kill(self) -> None: ...
    def remove(self, *, force: bool = True) -> None: ...
    def reload(self) -> None: ...

    @property
    def attrs(self) -> dict[str, Any]:
        return {}


class _FakeDockerClient:
    def __init__(self, stdout: bytes = b'{"score": 0.85}') -> None:
        self.containers = _Containers(stdout)


class _Containers:
    def __init__(self, stdout: bytes) -> None:
        self._stdout = stdout

    def run(self, image: str, command: Any, **kwargs: Any) -> _FakeContainer:
        return _FakeContainer(self._stdout)


# ─── helper ───────────────────────────────────────────────────────────────────


def _make(
    tmp_path: Any,
    sdk_outputs: list[dict[str, Any]],
    *,
    stdout: bytes = b'{"score": 0.85}',
    max_iters: int = 5,
    threshold: float = 0.9,
) -> tuple[MLESolver, Blackboard]:
    paths = RunPaths(root=tmp_path / "run").ensure()
    bb = Blackboard(paths)
    agent = RoleAgent(
        RoleName.ML_ENGINEER, _FakeSDK(sdk_outputs), registry=ToolRegistry()
    )
    sandbox = SandboxManager(client=_FakeDockerClient(stdout))
    solver = MLESolver(
        agent, sandbox, bb, max_iters=max_iters, score_threshold=threshold
    )
    return solver, bb


# ─── tests ────────────────────────────────────────────────────────────────────


def test_converges_at_threshold(tmp_path: Any) -> None:
    solver, _ = _make(tmp_path, [{"code": "v2"}], stdout=b'{"score": 0.95}', threshold=0.9)  # noqa: E501
    result = solver.solve("v1")
    assert result.converged
    assert result.best_score == pytest.approx(0.95)
    assert result.iters == 1


def test_runs_full_max_iters_when_below_threshold(tmp_path: Any) -> None:
    solver, _ = _make(
        tmp_path, [{"code": "x"}], stdout=b'{"score": 0.5}', max_iters=3, threshold=0.9
    )
    result = solver.solve("init")
    assert not result.converged
    assert result.iters == 3


def test_blackboard_code_written_on_improvement(tmp_path: Any) -> None:
    solver, bb = _make(
        tmp_path, [{"code": "improved"}], stdout=b'{"score": 0.95}', threshold=0.9
    )
    solver.solve("initial")
    art = bb.get("code.main")
    assert isinstance(art.payload, CodeArtifact)
    assert art.payload.files["main.py"] == "improved"


def test_run_history_accumulated(tmp_path: Any) -> None:
    solver, bb = _make(tmp_path, [{"code": "x"}], max_iters=3, threshold=0.99)
    solver.solve("init")
    hist = bb.get("runs.history")
    assert isinstance(hist.payload, RunHistory)
    assert len(hist.payload.records) == 3


def test_parse_error_falls_back_to_original_code(tmp_path: Any) -> None:
    # SDK returns dict without "code" key → EditCommand validation fails → fallback
    solver, _ = _make(
        tmp_path, [{"not_code": "oops"}], stdout=b'{"score": 0.95}', threshold=0.9
    )
    result = solver.solve("fallback")
    assert result.converged
    assert result.best_score == pytest.approx(0.95)


def test_parse_score_extracts_last_json_line() -> None:
    assert _parse_score('noise\n{"score": 0.77}') == pytest.approx(0.77)


def test_parse_score_returns_none_on_no_json() -> None:
    assert _parse_score("error: traceback...") is None
