"""ToolRegistry 单测：注册、授权、越权拒绝与 run_code 沙箱路由。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from agent_research.harness.enums import RoleName, RunStatus
from agent_research.harness.sandbox import ExecResult, SandboxSpec
from agent_research.harness.tools import (
    ToolAuthorizationError,
    ToolRegistry,
    ToolSpec,
    ToolValidationError,
    make_run_code_tool,
)


def _echo(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"payload": dict(payload)}


def test_register_and_tools_for_role_returns_minimum_subset():
    registry = ToolRegistry()
    registry.register(
        ToolSpec("lit_search", "search literature", _echo),
        {RoleName.PHD, RoleName.POSTDOC},
    )
    registry.register(
        ToolSpec("run_code", "run code", _echo),
        {RoleName.ML_ENGINEER, RoleName.SW_ENGINEER},
    )

    assert [tool.name for tool in registry.tools_for(RoleName.PHD)] == ["lit_search"]
    assert [tool.name for tool in registry.tools_for(RoleName.ML_ENGINEER)] == [
        "run_code"
    ]


def test_call_denies_unauthorized_role():
    registry = ToolRegistry()
    registry.register(ToolSpec("run_code", "run code", _echo), {RoleName.ML_ENGINEER})

    with pytest.raises(ToolAuthorizationError):
        registry.call(RoleName.REVIEWER, "run_code", {"cmd": "python main.py"})


def test_duplicate_and_empty_role_registration_rejected():
    registry = ToolRegistry()
    tool = ToolSpec("safe_tool", "safe", _echo)
    registry.register(tool, {RoleName.PHD})

    with pytest.raises(ToolValidationError):
        registry.register(tool, {RoleName.POSTDOC})
    with pytest.raises(ToolValidationError):
        registry.register(ToolSpec("no_roles", "bad", _echo), set())


class FakeSandbox:
    def __init__(self) -> None:
        self.spawned: list[SandboxSpec | None] = []
        self.runs: list[tuple[object, Any, float | None]] = []
        self.torn_down: list[object] = []
        self.handle = object()

    def spawn(self, spec: SandboxSpec | None = None) -> object:
        self.spawned.append(spec)
        return self.handle

    def run(
        self,
        handle: object,
        cmd: Any,
        *,
        timeout_s: float | None = None,
    ) -> ExecResult:
        self.runs.append((handle, cmd, timeout_s))
        return ExecResult(
            stdout="ok",
            stderr="",
            exit_code=0,
            status=RunStatus.SUCCESS,
            elapsed_s=0.01,
        )

    def teardown(self, handle: object) -> None:
        self.torn_down.append(handle)


def test_run_code_tool_routes_through_sandbox_and_tears_down():
    sandbox = FakeSandbox()
    tool = make_run_code_tool(sandbox)  # type: ignore[arg-type]
    spec = SandboxSpec(image_tag="test:image")

    result = tool.handler(
        {"cmd": ["python", "main.py"], "timeout_s": 5, "sandbox": spec}
    )

    assert result.status == RunStatus.SUCCESS
    assert sandbox.spawned == [spec]
    assert sandbox.runs == [(sandbox.handle, ("python", "main.py"), 5)]
    assert sandbox.torn_down == [sandbox.handle]


def test_run_code_tool_rejects_invalid_payload():
    tool = make_run_code_tool(FakeSandbox())  # type: ignore[arg-type]

    with pytest.raises(ToolValidationError):
        tool.handler({"cmd": ["python", 1]})
    with pytest.raises(ToolValidationError):
        tool.handler({"cmd": "python main.py", "timeout_s": "slow"})
