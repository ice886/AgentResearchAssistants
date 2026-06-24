"""MessageBus 单测：send、audit_log、dialogue 收敛、迭代限制、intent 解析。"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agent_research.agents.base import AgentResult, RoleAgent, SDKInvocation
from agent_research.harness.enums import Intent, RoleName
from agent_research.harness.messagebus import MessageBus, Transcript, approve_on_intent
from agent_research.harness.models import Message
from agent_research.harness.tools import ToolRegistry

# ─── fakes ────────────────────────────────────────────────────────────────────


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


def _msg(from_role: RoleName, to: RoleName, intent: Intent) -> Message:
    return Message(from_role=from_role, to=to, intent=intent)


# ─── send / audit_log ─────────────────────────────────────────────────────────


def test_send_returns_sequential_ids() -> None:
    bus = MessageBus()
    msg = _msg(RoleName.PHD, RoleName.POSTDOC, Intent.PROPOSE)
    assert bus.send(msg) == 0
    assert bus.send(msg) == 1


def test_audit_log_is_copy() -> None:
    bus = MessageBus()
    msg = _msg(RoleName.PHD, RoleName.POSTDOC, Intent.PROPOSE)
    bus.send(msg)
    log = bus.audit_log
    log.clear()
    assert len(bus.audit_log) == 1


# ─── dialogue ─────────────────────────────────────────────────────────────────


def test_dialogue_converges_on_approve() -> None:
    phd = _agent(RoleName.PHD, [{"intent": "propose"}])
    postdoc = _agent(RoleName.POSTDOC, [{"intent": "approve"}])
    bus = MessageBus()
    result = bus.dialogue([phd, postdoc], topic="plan", max_turns=10,
                          converge_fn=approve_on_intent)
    assert result.converged
    assert result.turns == 2
    assert result.messages[-1].intent == Intent.APPROVE


def test_dialogue_runs_full_turns_without_convergence() -> None:
    phd = _agent(RoleName.PHD, [{"intent": "propose"}])
    postdoc = _agent(RoleName.POSTDOC, [{"intent": "critique"}])
    bus = MessageBus()
    result = bus.dialogue([phd, postdoc], topic="plan", max_turns=4,
                          converge_fn=approve_on_intent)
    assert not result.converged
    assert result.turns == 4
    assert len(result.messages) == 4


def test_dialogue_alternates_participants() -> None:
    phd = _agent(RoleName.PHD, [{"intent": "propose"}])
    postdoc = _agent(RoleName.POSTDOC, [{"intent": "critique"}])
    bus = MessageBus()
    result = bus.dialogue([phd, postdoc], topic="plan", max_turns=4,
                          converge_fn=lambda m: False)
    roles = [m.from_role for m in result.messages]
    assert roles == [RoleName.PHD, RoleName.POSTDOC, RoleName.PHD, RoleName.POSTDOC]


def test_dialogue_messages_logged_to_audit() -> None:
    phd = _agent(RoleName.PHD, [{"intent": "propose"}])
    postdoc = _agent(RoleName.POSTDOC, [{"intent": "approve"}])
    bus = MessageBus()
    bus.dialogue([phd, postdoc], topic="plan", max_turns=10,
                 converge_fn=approve_on_intent)
    assert len(bus.audit_log) == 2


def test_dialogue_unknown_intent_defaults_to_report() -> None:
    phd = _agent(RoleName.PHD, [{"intent": "unknown_xyz"}])
    postdoc = _agent(RoleName.POSTDOC, [{"intent": "approve"}])
    bus = MessageBus()
    result = bus.dialogue([phd, postdoc], topic="plan", max_turns=4,
                          converge_fn=approve_on_intent)
    assert result.messages[0].intent == Intent.REPORT


def test_dialogue_empty_participants_raises() -> None:
    bus = MessageBus()
    with pytest.raises(ValueError):
        bus.dialogue([], topic="plan", max_turns=3, converge_fn=approve_on_intent)


def test_transcript_is_immutable() -> None:
    t = Transcript(messages=[], converged=True, turns=1)
    with pytest.raises((TypeError, ValidationError)):
        t.converged = False  # type: ignore[misc]
