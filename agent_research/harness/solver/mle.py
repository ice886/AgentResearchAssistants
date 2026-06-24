"""MLESolver：propose → evaluate → select 闭环，接 RoleAgent + SandboxManager。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from ...agents.base import AgentTask, RoleAgent
from ..blackboard import Blackboard
from ..enums import RunStatus
from ..models import Artifact, CodeArtifact, RunHistory, RunRecord
from ..sandbox import SandboxManager
from .base import SolverBase, SolveResult

_CODE_ID = "code.main"
_RUNS_ID = "runs.history"


class EditCommand(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    code: str
    description: str = ""


class MLESolver(SolverBase):
    """propose → evaluate → select 迭代，直到 score ≥ threshold 或用尽 max_iters。"""

    def __init__(
        self,
        agent: RoleAgent,
        sandbox: SandboxManager,
        blackboard: Blackboard,
        *,
        max_iters: int = 10,
        score_threshold: float = 0.9,
    ) -> None:
        self._agent = agent
        self._sandbox = sandbox
        self._bb = blackboard
        self.max_iters = max_iters
        self.score_threshold = score_threshold

    def solve(self, initial_code: str) -> SolveResult:
        best_code = initial_code
        best_score: float | None = None
        feedback = ""
        art_id: str | None = None

        for i in range(1, self.max_iters + 1):
            edit = self._propose(best_code, feedback)
            score, stdout, stderr = self._evaluate(edit.code)

            if score is not None and (best_score is None or score > best_score):
                best_code = edit.code
                best_score = score
                art_id = self._write_code(best_code, best_score)

            self._append_run(i, score)
            if stderr:
                feedback = stderr
            elif best_score is not None:
                feedback = f"score={best_score}"
            else:
                feedback = ""

            if best_score is not None and best_score >= self.score_threshold:
                return SolveResult(
                    best_code=best_code,
                    best_score=best_score,
                    iters=i,
                    converged=True,
                    artifact_id=art_id,
                )

        return SolveResult(
            best_code=best_code,
            best_score=best_score,
            iters=self.max_iters,
            converged=False,
            artifact_id=art_id,
        )

    # ----------------------------------------------------------------- 内部 -- #

    def _propose(self, code: str, feedback: str) -> EditCommand:
        result = self._agent.run(
            AgentTask(
                goal="Improve the ML code to increase the score metric.",
                context={"current_code": code, "feedback": feedback},
            )
        )
        data: dict[str, Any] = dict(result.output) if result.output else {}
        if not data:
            try:
                data = json.loads(result.content)
            except (json.JSONDecodeError, ValueError):
                return EditCommand(code=code, description="parse_error")
        try:
            return EditCommand.model_validate(data)
        except Exception:
            return EditCommand(code=code, description="parse_error")

    def _evaluate(self, code: str) -> tuple[float | None, str, str]:
        handle = self._sandbox.spawn()
        try:
            res = self._sandbox.run(handle, ["python3", "-c", code])
        finally:
            self._sandbox.teardown(handle)
        return _parse_score(res.stdout), res.stdout, res.stderr

    def _write_code(self, code: str, score: float) -> str:
        art = Artifact(
            id=_CODE_ID,
            created_by=self._agent.role,
            score=score,
            payload=CodeArtifact(files={"main.py": code}, entrypoint="main.py"),
        )
        version = self._bb.history(_CODE_ID)[-1] if self._bb.exists(_CODE_ID) else 0
        self._bb.set(art, expected_version=version)
        return _CODE_ID

    def _append_run(self, iteration: int, score: float | None) -> None:
        record = RunRecord(
            code_version=iteration,
            metrics={"score": score} if score is not None else {},
            status=RunStatus.SUCCESS if score is not None else RunStatus.FAILED,
            seed=iteration,
        )
        if self._bb.exists(_RUNS_ID):
            existing = self._bb.get(_RUNS_ID)
            assert isinstance(existing.payload, RunHistory)
            new_payload = RunHistory(records=[*existing.payload.records, record])
            new_art = Artifact(
                id=_RUNS_ID, created_by=self._agent.role, payload=new_payload
            )
            self._bb.set(new_art, expected_version=existing.version)
        else:
            self._bb.set(
                Artifact(
                    id=_RUNS_ID,
                    created_by=self._agent.role,
                    payload=RunHistory(records=[record]),
                ),
                expected_version=0,
            )


def _parse_score(stdout: str) -> float | None:
    """从 stdout 末尾 JSON 行提取 score 字段。"""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return float(json.loads(line)["score"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return None
