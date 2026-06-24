"""Orchestrator + CheckpointGate + StateGraph 单测。"""

from __future__ import annotations

from typing import Any

import pytest

from agent_research.config import RunPaths
from agent_research.harness.blackboard import Blackboard
from agent_research.harness.checkpoint import CheckpointGate
from agent_research.harness.enums import Verdict
from agent_research.harness.models import Decision, DecisionLog
from agent_research.harness.orchestrator import Orchestrator
from agent_research.workflow.pipeline import Node, StateGraph


def _bb(tmp_path: Any) -> Blackboard:
    return Blackboard(RunPaths(root=tmp_path / "run").ensure())


def _approve(cid: str) -> Decision:
    return Decision(checkpoint_id=cid, verdict=Verdict.APPROVE)


def _reject(cid: str) -> Decision:
    return Decision(checkpoint_id=cid, verdict=Verdict.REJECT)


# ─── StateGraph ───────────────────────────────────────────────────────────────


def test_graph_get_node() -> None:
    g = StateGraph([Node("a"), Node("b")])
    assert g.get("a").id == "a"


def test_graph_next_node() -> None:
    g = StateGraph([Node("a"), Node("b"), Node("c")])
    assert g.next_node("a").id == "b"  # type: ignore[union-attr]
    assert g.next_node("c") is None


def test_graph_unknown_node_raises() -> None:
    g = StateGraph([Node("a")])
    with pytest.raises(KeyError):
        g.get("z")


# ─── CheckpointGate ───────────────────────────────────────────────────────────


def test_gate_disabled_auto_approves() -> None:
    gate = CheckpointGate(enabled=False)
    d = gate.gate("cp1")
    assert d.verdict == Verdict.APPROVE


def test_gate_uses_custom_fn() -> None:
    gate = CheckpointGate(decision_fn=_reject)
    d = gate.gate("cp1")
    assert d.verdict == Verdict.REJECT


# ─── Orchestrator ─────────────────────────────────────────────────────────────


def test_all_non_checkpoint_nodes_run_in_order(tmp_path: Any) -> None:
    order: list[str] = []
    g = StateGraph([
        Node("a", handler=lambda: order.append("a")),
        Node("b", handler=lambda: order.append("b")),
        Node("c", handler=lambda: order.append("c")),
    ])
    orch = Orchestrator(_bb(tmp_path), CheckpointGate(enabled=False))
    result = orch.run(g)
    assert order == ["a", "b", "c"]
    assert result.completed_nodes == ["a", "b", "c"]
    assert not result.aborted


def test_checkpoint_approve_continues(tmp_path: Any) -> None:
    ran: list[str] = []
    g = StateGraph([
        Node("phase1", handler=lambda: ran.append("phase1")),
        Node("cp1", is_checkpoint=True),
        Node("phase2", handler=lambda: ran.append("phase2")),
    ])
    orch = Orchestrator(_bb(tmp_path), CheckpointGate(decision_fn=_approve))
    result = orch.run(g)
    assert ran == ["phase1", "phase2"]
    assert not result.aborted
    assert result.decisions[0].verdict == Verdict.APPROVE


def test_checkpoint_reject_aborts(tmp_path: Any) -> None:
    ran: list[str] = []
    g = StateGraph([
        Node("phase1", handler=lambda: ran.append("phase1")),
        Node("cp1", is_checkpoint=True),
        Node("phase2", handler=lambda: ran.append("phase2")),
    ])
    orch = Orchestrator(_bb(tmp_path), CheckpointGate(decision_fn=_reject))
    result = orch.run(g)
    assert ran == ["phase1"]
    assert result.aborted
    assert "phase2" not in result.completed_nodes


def test_resume_skips_approved_checkpoints(tmp_path: Any) -> None:
    bb = _bb(tmp_path)
    ran: list[str] = []
    g = StateGraph([
        Node("phase1", handler=lambda: ran.append("phase1")),
        Node("cp1", is_checkpoint=True),
        Node("phase2", handler=lambda: ran.append("phase2")),
    ])
    # First run: approve cp1
    orch = Orchestrator(bb, CheckpointGate(decision_fn=_approve))
    orch.run(g)
    ran.clear()

    # Second run: cp1 already approved → skipped
    gate_calls: list[str] = []
    def _tracking(cid: str) -> Decision:
        gate_calls.append(cid)
        return _approve(cid)

    orch2 = Orchestrator(bb, CheckpointGate(decision_fn=_tracking))
    orch2.run(g)
    assert "cp1" not in gate_calls
    assert ran == ["phase1", "phase2"]


def test_decisions_written_to_blackboard(tmp_path: Any) -> None:
    bb = _bb(tmp_path)
    g = StateGraph([Node("cp1", is_checkpoint=True)])
    Orchestrator(bb, CheckpointGate(decision_fn=_approve)).run(g)
    art = bb.get("decisions.main")
    assert isinstance(art.payload, DecisionLog)
    assert art.payload.decisions[0].checkpoint_id == "cp1"


def test_node_without_handler_still_completes(tmp_path: Any) -> None:
    g = StateGraph([Node("noop")])
    result = Orchestrator(_bb(tmp_path), CheckpointGate(enabled=False)).run(g)
    assert result.completed_nodes == ["noop"]
