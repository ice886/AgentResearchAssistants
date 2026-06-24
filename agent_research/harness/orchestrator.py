"""Orchestrator：StateGraph 驱动 + CheckpointGate + resume-safe 决议跳过。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..config import RunPaths
from ..workflow.pipeline import StateGraph
from .blackboard import Blackboard
from .checkpoint import CheckpointGate
from .enums import RoleName, Verdict
from .models import Artifact, Decision, DecisionLog

_DECISIONS_ID = "decisions.main"
log = logging.getLogger(__name__)


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    completed_nodes: list[str]
    decisions: list[Decision]
    aborted: bool = False


class Orchestrator:
    """线性 StateGraph 驱动器，checkpoint 节点请人审批，其余节点直接执行。"""

    def __init__(
        self,
        blackboard: Blackboard,
        gate: CheckpointGate,
        *,
        run_paths: RunPaths | None = None,
    ) -> None:
        self._bb = blackboard
        self._gate = gate
        self._run_paths = run_paths

    @property
    def _phases_file(self) -> Path | None:
        if self._run_paths is None:
            return None
        return self._run_paths.logs_dir / "phases.json"

    def _load_completed_phases(self) -> set[str]:
        f = self._phases_file
        if f is None or not f.exists():
            return set()
        try:
            return set(json.loads(f.read_text()))
        except Exception:
            return set()

    def _save_completed_phases(self, phases: set[str]) -> None:
        f = self._phases_file
        if f is None:
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(sorted(phases)))

    def run(self, graph: StateGraph) -> RunResult:
        approved = self._approved_checkpoints()
        done_phases = self._load_completed_phases()
        completed: list[str] = []
        decisions: list[Decision] = []

        for node in graph.nodes:
            if node.is_checkpoint:
                if node.id in approved:
                    log.info("[checkpoint] %s — skipped (already approved)", node.id)
                    continue
                log.info("[checkpoint] %s — waiting for decision...", node.id)
                decision = self._gate.gate(node.id)
                self._record_decision(decision)
                decisions.append(decision)
                log.info("[checkpoint] %s — verdict: %s", node.id, decision.verdict)
                if decision.verdict == Verdict.REJECT:
                    return RunResult(
                        completed_nodes=completed, decisions=decisions, aborted=True
                    )
            else:
                if node.id in done_phases:
                    log.info("[phase] %s — skipped (already completed)", node.id)
                    completed.append(node.id)
                    continue
                log.info("[phase] %s — starting", node.id)
                if node.handler is not None:
                    node.handler()
                completed.append(node.id)
                done_phases.add(node.id)
                self._bb.snapshot()
                self._save_completed_phases(done_phases)
                log.info("[phase] %s — done", node.id)

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
