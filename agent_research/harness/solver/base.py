"""SolverBase：求解闭环抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict


class SolveResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    best_code: str
    best_score: float | None = None
    iters: int
    converged: bool
    artifact_id: str | None = None


class SolverBase(ABC):
    @abstractmethod
    def solve(self, initial_code: str) -> SolveResult: ...
