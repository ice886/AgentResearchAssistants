"""MessageBus：消息路由 + 审计日志 + 多回合磋商收敛。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..agents.base import AgentTask, RoleAgent
from .enums import Intent, RoleName
from .models import Message


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: list[Message] = Field(default_factory=list)
    converged: bool = False
    turns: int = 0


ConvergeFn = Callable[[Message], bool]


class MessageBus:
    """消息中转与多回合 dialogue 控制器。"""

    def __init__(self) -> None:
        self._log: list[Message] = []

    def send(self, message: Message) -> int:
        """记录消息到审计日志，返回消息索引。"""
        self._log.append(message)
        return len(self._log) - 1

    @property
    def audit_log(self) -> list[Message]:
        return list(self._log)

    def dialogue(
        self,
        participants: list[RoleAgent],
        topic: str,
        max_turns: int,
        converge_fn: ConvergeFn,
    ) -> Transcript:
        """交替驱动 participants，直到 converge_fn 返回 True 或耗尽 max_turns。"""
        if not participants:
            raise ValueError("participants 不能为空")

        n = len(participants)
        messages: list[Message] = []
        last_msg: Message | None = None

        for turn in range(max_turns):
            agent = participants[turn % n]
            next_role = participants[(turn + 1) % n].role
            context: dict[str, Any] = {"topic": topic}
            if last_msg is not None:
                context["last_message"] = last_msg.model_dump(mode="json")

            result = agent.run(
                AgentTask(goal=f"Discuss topic: {topic}", context=context)
            )
            msg = _to_message(dict(result.output), agent.role, next_role)
            self.send(msg)
            messages.append(msg)
            last_msg = msg

            if converge_fn(msg):
                return Transcript(messages=messages, converged=True, turns=turn + 1)

        return Transcript(messages=messages, converged=False, turns=max_turns)


def approve_on_intent(msg: Message) -> bool:
    """标准收敛函数：任意参与者发出 intent=approve 即收敛。"""
    return msg.intent == Intent.APPROVE


def _to_message(
    output: dict[str, Any], from_role: RoleName, to_role: RoleName
) -> Message:
    raw = output.get("intent", Intent.REPORT)
    try:
        intent = Intent(raw)
    except ValueError:
        intent = Intent.REPORT
    refs = output.get("blackboard_refs") or []
    skip = {"intent", "blackboard_refs"}
    payload = {k: v for k, v in output.items() if k not in skip}
    return Message(
        from_role=from_role, to=to_role, intent=intent,
        blackboard_refs=refs, payload=payload,
    )
