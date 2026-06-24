"""BudgetController：token 计费、预算检查与成本报告。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .enums import RoleName


class CostBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_budget: int
    spent: int
    remaining: int
    by_role: dict[str, int]
    by_phase: dict[str, int]


class BudgetExceededError(Exception):
    """已超出 token 预算。"""


class BudgetController:
    """按 (role, phase) 粒度计费，支持预算检查与成本报告。"""

    def __init__(self, total_tokens: int) -> None:
        self._total = total_tokens
        self._by_role: dict[str, int] = {}
        self._by_phase: dict[str, int] = {}

    def charge(self, tokens: int, role: RoleName | str, phase: str) -> None:
        key = str(role)
        self._by_role[key] = self._by_role.get(key, 0) + tokens
        self._by_phase[phase] = self._by_phase.get(phase, 0) + tokens

    def spent(self) -> int:
        return sum(self._by_role.values())

    def remaining(self) -> int:
        return max(0, self._total - self.spent())

    def check(self, scope: str | None = None) -> bool:
        """True = 仍在预算内；scope 为 None 时检查全局。"""
        if scope is not None:
            used = self._by_phase.get(scope, 0)
            return used < self._total
        return self.spent() < self._total

    def assert_budget(self) -> None:
        if not self.check():
            raise BudgetExceededError(
                f"token 预算已耗尽 (spent={self.spent()} / total={self._total})"
            )

    def report(self) -> CostBreakdown:
        return CostBreakdown(
            total_budget=self._total,
            spent=self.spent(),
            remaining=self.remaining(),
            by_role=dict(self._by_role),
            by_phase=dict(self._by_phase),
        )
