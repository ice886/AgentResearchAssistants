"""端到端冒烟测试：三阶段 StateGraph 从 lit_review → paper 全程跑通。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_research.agents.base import AgentResult, RoleAgent, SDKInvocation
from agent_research.config import RunPaths
from agent_research.harness.blackboard import Blackboard
from agent_research.harness.budget import BudgetController
from agent_research.harness.checkpoint import CheckpointGate
from agent_research.harness.enums import RoleName
from agent_research.harness.messagebus import MessageBus, approve_on_intent
from agent_research.harness.models import (
    Artifact,
    DecisionLog,
    LitEntry,
    LitReview,
)
from agent_research.harness.orchestrator import Orchestrator
from agent_research.harness.sandbox import SandboxManager
from agent_research.harness.solver.mle import MLESolver
from agent_research.harness.solver.paper import PaperSolver
from agent_research.harness.tools import ToolRegistry
from agent_research.workflow.pipeline import Node, StateGraph

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

    def exec_run(self, cmd: Any, **kw: Any) -> _FakeExec:
        return _FakeExec(0, (b'{"score": 0.95}', b""))

    def kill(self) -> None: ...
    def remove(self, *, force: bool = True) -> None: ...
    def reload(self) -> None: ...

    @property
    def attrs(self) -> dict[str, Any]:
        return {}


class _FakeContainers:
    def run(self, image: str, command: Any, **kw: Any) -> _FakeContainer:
        return _FakeContainer()


class _FakeDockerClient:
    containers = _FakeContainers()


def _agent(role: RoleName, outputs: list[dict[str, Any]]) -> RoleAgent:
    return RoleAgent(role, _FakeSDK(outputs), registry=ToolRegistry())


# ─── smoke test ───────────────────────────────────────────────────────────────


def test_e2e_three_phase_pipeline(tmp_path: Any) -> None:
    """三阶段流水线端到端：lit_review → plan → experiment → paper，四个检查点全通。"""
    bb = Blackboard(RunPaths(root=tmp_path / "run").ensure())
    budget = BudgetController(total_tokens=1_000_000)

    # agents
    phd = _agent(RoleName.PHD, [{"intent": "propose"}, {"intent": "approve"}])
    postdoc = _agent(RoleName.POSTDOC, [{"intent": "approve"}])
    ml_eng = _agent(RoleName.ML_ENGINEER, [{"code": "print('hi')"}])
    dims09 = {"quality": 0.9, "clarity": 0.9, "originality": 0.9, "significance": 0.9}
    reviewer = _agent(RoleName.REVIEWER, [{"dims": dims09}])
    sandbox = SandboxManager(client=_FakeDockerClient())
    bus = MessageBus()

    def phase_lit_review() -> None:
        art = Artifact(
            id="lit_review.main",
            created_by=RoleName.PHD,
            payload=LitReview(
                entries=[LitEntry(
                    arxiv_id="2501.00001", title="T", summary="S",
                    relevance=0.9, citation_key="k1",
                )]
            ),
        )
        bb.set(art, expected_version=0)
        budget.charge(500, RoleName.PHD, "lit_review")

    def phase_plan() -> None:
        bus.dialogue(
            [phd, postdoc], topic="plan", max_turns=4,
            converge_fn=approve_on_intent,
        )
        budget.charge(1000, RoleName.PHD, "plan")

    def phase_experiment() -> None:
        solver = MLESolver(ml_eng, sandbox, bb, max_iters=2, score_threshold=0.9)
        solver.solve("print('baseline')")
        budget.charge(2000, RoleName.ML_ENGINEER, "experiment")

    def phase_paper() -> None:
        solver = PaperSolver(phd, reviewer, bb, max_iters=1, score_threshold=0.8)
        solver.solve("\\section{intro}")
        budget.charge(3000, RoleName.PHD, "paper")

    graph = StateGraph([
        Node("lit_review", handler=phase_lit_review),
        Node("cp1", is_checkpoint=True),
        Node("plan", handler=phase_plan),
        Node("cp2", is_checkpoint=True),
        Node("experiment", handler=phase_experiment),
        Node("cp3", is_checkpoint=True),
        Node("paper", handler=phase_paper),
    ])

    orch = Orchestrator(bb, CheckpointGate(enabled=False))
    result = orch.run(graph)

    # pipeline completed without abort
    assert not result.aborted
    assert result.completed_nodes == ["lit_review", "plan", "experiment", "paper"]

    # three checkpoints auto-approved and recorded
    assert len(result.decisions) == 3
    assert all(d.verdict.value == "approve" for d in result.decisions)

    # decisions persisted in Blackboard
    dec_art = bb.get("decisions.main")
    assert isinstance(dec_art.payload, DecisionLog)
    assert len(dec_art.payload.decisions) == 3

    # phase artifacts exist
    assert bb.exists("lit_review.main")
    assert bb.exists("code.main")
    assert bb.exists("paper.main")

    # budget consumed
    assert budget.spent() == 500 + 1000 + 2000 + 3000
    assert budget.check()
    report = budget.report()
    assert report.by_phase["experiment"] == 2000
