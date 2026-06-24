"""三阶段 ResearchPipeline：lit_review → plan → experiment → paper + 四个检查点。

每个 phase handler 是零参数 callable，由 build_research_pipeline 工厂注入依赖后返回。
"""

from __future__ import annotations

from collections.abc import Callable

from ..agents.base import AgentTask, RoleAgent
from ..harness.blackboard import Blackboard
from ..harness.enums import RoleName
from ..harness.messagebus import MessageBus, approve_on_intent
from ..harness.models import (
    Artifact,
    LitEntry,
    LitReview,
)
from ..harness.sandbox import SandboxManager
from ..harness.solver.mle import MLESolver
from ..harness.solver.paper import PaperSolver
from .pipeline import Node, StateGraph


def build_research_pipeline(
    *,
    phd: RoleAgent,
    postdoc: RoleAgent,
    ml_engineer: RoleAgent,
    reviewer: RoleAgent,
    sandbox: SandboxManager,
    blackboard: Blackboard,
    bus: MessageBus,
    idea: str = "",
) -> StateGraph:
    """返回三阶段四检查点的 StateGraph，handler 已完全注入依赖。"""
    return StateGraph([
        Node("lit_review", handler=_lit_review_handler(phd, blackboard, idea)),
        Node("cp1", is_checkpoint=True),
        Node("plan", handler=_plan_handler(phd, postdoc, bus, blackboard)),
        Node("cp2", is_checkpoint=True),
        Node("experiment", handler=_experiment_handler(
            ml_engineer, sandbox, blackboard
        )),
        Node("cp3", is_checkpoint=True),
        Node("paper", handler=_paper_handler(phd, reviewer, blackboard)),
        Node("cp4", is_checkpoint=True),
    ])


# ─── phase handlers ───────────────────────────────────────────────────────────


def _lit_review_handler(
    phd: RoleAgent, bb: Blackboard, idea: str
) -> Callable[[], None]:
    def _run() -> None:
        result = phd.run(AgentTask(
            goal=f"Search and summarize relevant literature for: {idea}",
            instructions=(
                "Return output as JSON with key 'entries' (list of paper objects)."
            ),
        ))
        entries: list[LitEntry] = []
        raw_entries = result.output.get("entries") if result.output else []
        if isinstance(raw_entries, list):
            for e in raw_entries[:10]:
                if isinstance(e, dict):
                    try:
                        entries.append(LitEntry.model_validate(e))
                    except Exception:
                        pass

        art = Artifact(
            id="lit_review.main",
            created_by=RoleName.PHD,
            payload=LitReview(entries=entries),
        )
        version = (
            bb.history("lit_review.main")[-1] if bb.exists("lit_review.main") else 0
        )
        bb.set(art, expected_version=version)

    return _run


def _plan_handler(
    phd: RoleAgent, postdoc: RoleAgent, bus: MessageBus, bb: Blackboard
) -> Callable[[], None]:
    def _run() -> None:
        bus.dialogue(
            [phd, postdoc],
            topic="experiment_plan",
            max_turns=8,
            converge_fn=approve_on_intent,
        )

    return _run


def _experiment_handler(
    ml_engineer: RoleAgent, sandbox: SandboxManager, bb: Blackboard
) -> Callable[[], None]:
    def _run() -> None:
        solver = MLESolver(
            ml_engineer, sandbox, bb, max_iters=10, score_threshold=0.9
        )
        solver.solve("# baseline\nprint('{\"score\": 0.0}')")

    return _run


def _paper_handler(
    phd: RoleAgent, reviewer: RoleAgent, bb: Blackboard
) -> Callable[[], None]:
    def _run() -> None:
        solver = PaperSolver(
            phd, reviewer, bb, max_iters=5, score_threshold=0.8
        )
        solver.solve("\\section{Introduction}\nTBD.")

    return _run
