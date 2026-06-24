"""CheckpointGate：人工检查点，支持注入决策函数或全局禁用（纯自动模式）。"""

from __future__ import annotations

from collections.abc import Callable

from .enums import Verdict
from .models import Decision

DecisionFn = Callable[[str], Decision]


def _auto_approve(checkpoint_id: str) -> Decision:
    return Decision(checkpoint_id=checkpoint_id, verdict=Verdict.APPROVE)


class CheckpointGate:
    """gate() 阻塞直到人工决议；disabled 时直接 auto-approve。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        decision_fn: DecisionFn | None = None,
    ) -> None:
        self._enabled = enabled
        self._fn = decision_fn or _auto_approve

    def gate(self, checkpoint_id: str) -> Decision:
        if not self._enabled:
            return _auto_approve(checkpoint_id)
        return self._fn(checkpoint_id)
