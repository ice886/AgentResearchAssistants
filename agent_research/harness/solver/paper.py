"""PaperSolver：propose(草稿改进) → evaluate(Reviewer 打分) → select 闭环。"""

from __future__ import annotations

import json
from typing import Any

from ...agents.base import AgentTask, RoleAgent
from ..blackboard import Blackboard
from ..models import (
    Artifact,
    PaperDraft,
    ReviewDims,
    ReviewScore,
    ReviewSet,
)
from .base import SolverBase, SolveResult
from .mle import EditCommand

_PAPER_ID = "paper.main"
_REVIEWS_ID = "reviews.main"


class PaperSolver(SolverBase):
    """作者 agent 反复改稿，Reviewer agent 打分，择优写入 Blackboard。"""

    def __init__(
        self,
        author: RoleAgent,
        reviewer: RoleAgent,
        blackboard: Blackboard,
        *,
        max_iters: int = 5,
        score_threshold: float = 0.8,
    ) -> None:
        self._author = author
        self._reviewer = reviewer
        self._bb = blackboard
        self.max_iters = max_iters
        self.score_threshold = score_threshold

    def solve(self, initial_latex: str) -> SolveResult:
        best_draft = initial_latex
        best_score: float | None = None
        feedback = ""
        art_id: str | None = None

        for i in range(1, self.max_iters + 1):
            edit = self._propose(best_draft, feedback)
            score, comments = self._evaluate(edit.code)

            if score is not None and (best_score is None or score > best_score):
                best_draft = edit.code
                best_score = score
                art_id = self._write_paper(best_draft)

            feedback = comments
            self._append_review(i, score, comments)

            if best_score is not None and best_score >= self.score_threshold:
                return SolveResult(
                    best_code=best_draft,
                    best_score=best_score,
                    iters=i,
                    converged=True,
                    artifact_id=art_id,
                )

        return SolveResult(
            best_code=best_draft,
            best_score=best_score,
            iters=self.max_iters,
            converged=False,
            artifact_id=art_id,
        )

    def _propose(self, draft: str, feedback: str) -> EditCommand:
        result = self._author.run(
            AgentTask(
                goal="Improve the paper draft based on reviewer feedback.",
                context={"current_draft": draft, "feedback": feedback},
            )
        )
        data: dict[str, Any] = dict(result.output) if result.output else {}
        if not data:
            try:
                data = json.loads(result.content)
            except (json.JSONDecodeError, ValueError):
                return EditCommand(code=draft, description="parse_error")
        try:
            return EditCommand.model_validate(data)
        except Exception:
            return EditCommand(code=draft, description="parse_error")

    def _evaluate(self, draft: str) -> tuple[float | None, str]:
        result = self._reviewer.run(
            AgentTask(
                goal="Score the paper draft on quality, clarity, originality, significance.",  # noqa: E501
                context={"draft": draft},
            )
        )
        return _parse_review(dict(result.output))

    def _write_paper(self, latex: str) -> str:
        art = Artifact(
            id=_PAPER_ID,
            created_by=self._author.role,
            payload=PaperDraft(
                sections={"main": latex},
                compile_status="ok",
            ),
        )
        version = self._bb.history(_PAPER_ID)[-1] if self._bb.exists(_PAPER_ID) else 0
        self._bb.set(art, expected_version=version)
        return _PAPER_ID

    def _append_review(
        self, iteration: int, score: float | None, comments: str
    ) -> None:
        review = ReviewScore(
            reviewer_id=f"reviewer-{self._reviewer.role}",
            dims=ReviewDims(
                quality=score or 0.0,
                clarity=score or 0.0,
                originality=score or 0.0,
                significance=score or 0.0,
            ),
            comments=comments,
        )
        if self._bb.exists(_REVIEWS_ID):
            existing = self._bb.get(_REVIEWS_ID)
            assert isinstance(existing.payload, ReviewSet)
            new_set = ReviewSet(reviews=[*existing.payload.reviews, review])
            self._bb.set(
                Artifact(
                    id=_REVIEWS_ID, created_by=self._reviewer.role, payload=new_set
                ),
                expected_version=existing.version,
            )
        else:
            self._bb.set(
                Artifact(
                    id=_REVIEWS_ID,
                    created_by=self._reviewer.role,
                    payload=ReviewSet(reviews=[review]),
                ),
                expected_version=0,
            )


def _parse_review(output: dict[str, Any]) -> tuple[float | None, str]:
    """从 reviewer output 提取平均分与评语。"""
    comments = str(output.get("comments", ""))
    dims_raw = output.get("dims")
    if isinstance(dims_raw, dict):
        try:
            dims = ReviewDims.model_validate(dims_raw)
            avg = (
                dims.quality + dims.clarity + dims.originality + dims.significance
            ) / 4
            return avg, comments
        except Exception:
            pass
    score = output.get("score")
    if score is not None:
        try:
            return float(score), comments
        except (TypeError, ValueError):
            pass
    return None, comments
