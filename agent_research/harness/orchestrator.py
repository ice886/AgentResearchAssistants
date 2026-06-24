"""Orchestrator：StateGraph 驱动 + CheckpointGate + resume-safe 决议跳过。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..workflow.pipeline import StateGraph
from .blackboard import Blackboard
from .checkpoint import CheckpointGate
from .enums import RoleName, Verdict
from .models import Artifact, Decision, DecisionLog

_DECISIONS_ID = "decisions.main"


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    completed_nodes: list[str]
    decisions: list[Decision]
    aborted: bool = False


class Orchestrator:
    """线性 StateGraph 驱动器，checkpoint 节点请人审批，其余节点直接执行。"""

    def __init__(self, blackboard: Blackboard, gate: CheckpointGate) -> None:
        self._bb = blackboard
        self._gate = gate

    def run(self, graph: StateGraph) -> RunResult:
        approved = self._approved_checkpoints()
        completed: list[str] = []
        decisions: list[Decision] = []

        for node in graph.nodes:
            if node.is_checkpoint:
                if node.id in approved:
                    continue
                decision = self._gate.gate(node.id)
                self._record_decision(decision)
                decisions.append(decision)
                if decision.verdict == Verdict.REJECT:
                    return RunResult(
                        completed_nodes=completed, decisions=decisions, aborted=True
                    )
            else:
                if node.handler is not None:
                    node.handler()
                completed.append(node.id)
                self._bb.snapshot()

        return RunResult(completed_nodes=completed, decisions=decisions)

    def _approved_checkpoints(self) -> set[str]:
        if not self._bb.exists(_DECISIONS_ID):
            return set()
        art = self._bb.get(_DECISIONS_ID)
        assert isinstance(art.payload, DecisionLog)
        return {
            d.checkpoint_id
            for d in art.payload.decisions
            if d.verdict == Verdict.APPROVE
        }

    def _record_decision(self, decision: Decision) -> None:
        if self._bb.exists(_DECISIONS_ID):
            existing = self._bb.get(_DECISIONS_ID)
            assert isinstance(existing.payload, DecisionLog)
            new_log = DecisionLog(
                decisions=[*existing.payload.decisions, decision]
            )
            art = Artifact(
                id=_DECISIONS_ID,
                created_by=RoleName.PROFESSOR,
                payload=new_log,
            )
            self._bb.set(art, expected_version=existing.version)
        else:
            self._bb.set(
                Artifact(
                    id=_DECISIONS_ID,
                    created_by=RoleName.PROFESSOR,
                    payload=DecisionLog(decisions=[decision]),
                ),
                expected_version=0,
            )
