"""共享 fixtures 与样例制品工厂。"""

from __future__ import annotations

import pytest

from agent_research.config import RunPaths
from agent_research.harness.blackboard import Blackboard
from agent_research.harness.enums import RoleName, RunStatus
from agent_research.harness.models import (
    Artifact,
    CodeArtifact,
    ExperimentPlan,
    LitEntry,
    LitReview,
    ResearchIdea,
    RunHistory,
    RunRecord,
)


@pytest.fixture
def run_paths(tmp_path) -> RunPaths:
    return RunPaths(root=tmp_path / "run-001").ensure()


@pytest.fixture
def bb(run_paths: RunPaths) -> Blackboard:
    return Blackboard(run_paths)


def make_idea(title: str = "Toy classification") -> Artifact:
    return Artifact(
        id="idea.main",
        created_by=RoleName.PHD,
        payload=ResearchIdea(title=title, motivation="测试动机"),
    )


def make_code(entrypoint: str = "main.py") -> Artifact:
    return Artifact(
        id="code.main",
        created_by=RoleName.ML_ENGINEER,
        payload=CodeArtifact(
            files={"main.py": "print('hi')"}, entrypoint=entrypoint, deps=["numpy"]
        ),
    )


def make_plan() -> Artifact:
    return Artifact(
        id="plan.main",
        created_by=RoleName.POSTDOC,
        payload=ExperimentPlan(
            hypotheses=["H1"],
            methodology="CV",
            metrics=["acc"],
            success_criteria=">0.9",
        ),
    )


def make_lit_review() -> Artifact:
    return Artifact(
        id="lit_review.main",
        created_by=RoleName.PHD,
        payload=LitReview(
            entries=[
                LitEntry(
                    arxiv_id="2501.00001",
                    title="A paper",
                    summary="摘要",
                    relevance=0.8,
                    citation_key="paper2025",
                )
            ]
        ),
    )


def make_runs() -> Artifact:
    return Artifact(
        id="runs.main",
        created_by=RoleName.ML_ENGINEER,
        score=0.91,
        payload=RunHistory(
            records=[
                RunRecord(
                    code_version=1,
                    metrics={"acc": 0.91},
                    stdout_ref="experiments/run1/stdout.txt",
                    status=RunStatus.SUCCESS,
                    seed=42,
                )
            ]
        ),
    )
