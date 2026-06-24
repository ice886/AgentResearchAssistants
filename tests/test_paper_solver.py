"""PaperSolver 单测：收敛、迭代限制、Blackboard 写入、评分解析。"""

from __future__ import annotations

from typing import Any

import pytest

from agent_research.agents.base import AgentResult, RoleAgent, SDKInvocation
from agent_research.config import RunPaths
from agent_research.harness.blackboard import Blackboard
from agent_research.harness.enums import RoleName
from agent_research.harness.models import PaperDraft, ReviewSet
from agent_research.harness.solver.paper import PaperSolver, _parse_review
from agent_research.harness.tools import ToolRegistry


class _FakeSDK:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self._outputs = outputs
        self._idx = 0

    def run(self, inv: SDKInvocation) -> AgentResult:
        data = self._outputs[self._idx % len(self._outputs)]
        self._idx += 1
        return AgentResult(content="", output=data)


def _agent(role: RoleName, outputs: list[dict[str, Any]]) -> RoleAgent:
    return RoleAgent(role, _FakeSDK(outputs), registry=ToolRegistry())


def _bb(tmp_path: Any) -> Blackboard:
    return Blackboard(RunPaths(root=tmp_path / "run").ensure())


_GOOD_DIMS = {
    "dims": {"quality": 0.9, "clarity": 0.9, "originality": 0.9, "significance": 0.9}
}
_LOW_DIMS = {
    "dims": {"quality": 0.5, "clarity": 0.5, "originality": 0.5, "significance": 0.5}
}


def _make(
    tmp_path: Any,
    author_outputs: list[dict[str, Any]],
    reviewer_outputs: list[dict[str, Any]],
    *,
    max_iters: int = 5,
    threshold: float = 0.8,
) -> tuple[PaperSolver, Blackboard]:
    bb = _bb(tmp_path)
    author = _agent(RoleName.PHD, author_outputs)
    reviewer = _agent(RoleName.REVIEWER, reviewer_outputs)
    solver = PaperSolver(
        author, reviewer, bb, max_iters=max_iters, score_threshold=threshold
    )
    return solver, bb


# ─── convergence ──────────────────────────────────────────────────────────────


def test_converges_when_score_above_threshold(tmp_path: Any) -> None:
    solver, _ = _make(tmp_path, [{"code": "v2"}], [_GOOD_DIMS])
    result = solver.solve("v1")
    assert result.converged
    assert result.best_score == pytest.approx(0.9)
    assert result.iters == 1


def test_runs_max_iters_without_convergence(tmp_path: Any) -> None:
    solver, _ = _make(
        tmp_path, [{"code": "x"}], [_LOW_DIMS], max_iters=3, threshold=0.9
    )
    result = solver.solve("init")
    assert not result.converged
    assert result.iters == 3


# ─── blackboard writes ────────────────────────────────────────────────────────


def test_paper_written_to_blackboard(tmp_path: Any) -> None:
    solver, bb = _make(tmp_path, [{"code": "improved draft"}], [_GOOD_DIMS])
    solver.solve("initial")
    art = bb.get("paper.main")
    assert isinstance(art.payload, PaperDraft)
    assert art.payload.sections["main"] == "improved draft"


def test_reviews_accumulated(tmp_path: Any) -> None:
    solver, bb = _make(
        tmp_path, [{"code": "x"}], [_LOW_DIMS], max_iters=3, threshold=0.99
    )
    solver.solve("init")
    art = bb.get("reviews.main")
    assert isinstance(art.payload, ReviewSet)
    assert len(art.payload.reviews) == 3


# ─── _parse_review ────────────────────────────────────────────────────────────


def test_parse_review_from_dims() -> None:
    dims = {"quality": 1.0, "clarity": 0.8, "originality": 0.6, "significance": 0.8}
    score, _ = _parse_review({"dims": dims})
    assert score == pytest.approx(0.8)


def test_parse_review_fallback_to_score() -> None:
    score, _ = _parse_review({"score": 0.75})
    assert score == pytest.approx(0.75)


def test_parse_review_returns_none_on_garbage() -> None:
    score, _ = _parse_review({"comment": "no score here"})
    assert score is None


def test_parse_error_falls_back_to_original(tmp_path: Any) -> None:
    solver, _ = _make(tmp_path, [{"not_code": "oops"}], [_GOOD_DIMS])
    result = solver.solve("fallback")
    assert result.converged
    assert result.best_score == pytest.approx(0.9)
