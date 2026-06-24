"""Blackboard 制品（artifact）与 MessageBus 消息的 Pydantic schema。

设计要点：
- ``Artifact`` 是统一信封，``payload`` 为按 ``kind`` 字段判别的联合（discriminated
  union）。单一具体类型 + 一个 ``TypeAdapter`` 即可异构存储、JSON 往返免注册表。
- 集合类命名空间（lit_review/runs/figures/reviews/decisions）用 wrapper payload
  包一个 list，使每个命名空间恰好映射一个 payload 模型；CAS 对整个集合版本化。
- 大文件（数据/figure/stdout）只存相对路径引用（``*_ref`` / ``path``），不存 blob。
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from .enums import Intent, Namespace, RoleName, RunStatus, Verdict


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PayloadBase(BaseModel):
    """所有 payload 的基类：禁止未知字段、不可变。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- #
# 单体 payload
# --------------------------------------------------------------------------- #
class ResearchIdea(PayloadBase):
    kind: Literal[Namespace.IDEA] = Namespace.IDEA
    title: str
    motivation: str
    constraints: list[str] = Field(default_factory=list)
    dataset_hint: str | None = None


class ExperimentPlan(PayloadBase):
    kind: Literal[Namespace.PLAN] = Namespace.PLAN
    hypotheses: list[str] = Field(default_factory=list)
    methodology: str = ""
    metrics: list[str] = Field(default_factory=list)
    success_criteria: str = ""


class DatasetSpec(PayloadBase):
    kind: Literal[Namespace.DATASET] = Namespace.DATASET
    source: str
    # ``schema`` 与 BaseModel.schema 冲突，用 alias 暴露 "schema" 字段名。
    schema_: str = Field(alias="schema")
    split: str | None = None
    prep_script_ref: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class CodeArtifact(PayloadBase):
    kind: Literal[Namespace.CODE] = Namespace.CODE
    files: dict[str, str] = Field(default_factory=dict)
    entrypoint: str
    deps: list[str] = Field(default_factory=list)


class PaperDraft(PayloadBase):
    kind: Literal[Namespace.PAPER] = Namespace.PAPER
    sections: dict[str, str] = Field(default_factory=dict)
    bib_refs: list[str] = Field(default_factory=list)
    compile_status: str | None = None


# --------------------------------------------------------------------------- #
# 集合元素 + wrapper payload
# --------------------------------------------------------------------------- #
class LitEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    arxiv_id: str
    title: str
    summary: str
    relevance: float
    citation_key: str


class LitReview(PayloadBase):
    kind: Literal[Namespace.LIT_REVIEW] = Namespace.LIT_REVIEW
    entries: list[LitEntry] = Field(default_factory=list)


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code_version: int
    metrics: dict[str, float] = Field(default_factory=dict)
    stdout_ref: str | None = None
    status: RunStatus
    seed: int
    analysis: str | None = None


class RunHistory(PayloadBase):
    kind: Literal[Namespace.RUNS] = Namespace.RUNS
    records: list[RunRecord] = Field(default_factory=list)


class Figure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    caption: str
    source_run: int


class FigureSet(PayloadBase):
    kind: Literal[Namespace.FIGURES] = Namespace.FIGURES
    figures: list[Figure] = Field(default_factory=list)


class ReviewDims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    quality: float
    clarity: float
    originality: float
    significance: float


class ReviewScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reviewer_id: str
    dims: ReviewDims
    comments: str = ""


class ReviewSet(PayloadBase):
    kind: Literal[Namespace.REVIEWS] = Namespace.REVIEWS
    reviews: list[ReviewScore] = Field(default_factory=list)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    checkpoint_id: str
    verdict: Verdict
    human_note: str | None = None
    ts: datetime = Field(default_factory=_utcnow)


class DecisionLog(PayloadBase):
    kind: Literal[Namespace.DECISIONS] = Namespace.DECISIONS
    decisions: list[Decision] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 判别联合 + Artifact 信封
# --------------------------------------------------------------------------- #
Payload = Annotated[
    ResearchIdea
    | LitReview
    | ExperimentPlan
    | DatasetSpec
    | CodeArtifact
    | RunHistory
    | FigureSet
    | PaperDraft
    | ReviewSet
    | DecisionLog,
    Field(discriminator="kind"),
]


class Artifact(BaseModel):
    """Blackboard 制品信封。版本权威在 Blackboard，构造时 ``version`` 仅为占位。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int = 0
    created_by: RoleName
    created_at: datetime = Field(default_factory=_utcnow)
    parent_version: int | None = None
    score: float | None = None
    payload: Payload

    @property
    def namespace(self) -> Namespace:
        return Namespace(self.id.split(".", 1)[0])

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if "." not in v:
            raise ValueError(f"artifact id 必须形如 '<namespace>.<key>'，得到 {v!r}")
        ns, key = v.split(".", 1)
        if not key:
            raise ValueError(f"artifact id 缺少 key 部分: {v!r}")
        try:
            Namespace(ns)
        except ValueError:
            raise ValueError(f"未知命名空间 {ns!r} (id={v!r})") from None
        return v

    @field_validator("score")
    @classmethod
    def _check_score(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("score 必须是有限数（JSON 不支持 NaN/Inf）")
        return v

    @model_validator(mode="after")
    def _check_ns_matches_payload(self) -> Artifact:
        if self.namespace != self.payload.kind:
            raise ValueError(
                f"id 命名空间 {self.namespace.value!r} 与 payload.kind "
                f"{self.payload.kind.value!r} 不一致"
            )
        return self


#: 复用的校验/序列化适配器（snapshot/restore 与测试共用）。
ArtifactAdapter: TypeAdapter[Artifact] = TypeAdapter(Artifact)


# --------------------------------------------------------------------------- #
# MessageBus 消息（不落 Blackboard）
# --------------------------------------------------------------------------- #
class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_role: RoleName
    to: RoleName | list[RoleName]
    intent: Intent
    blackboard_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_ack: bool = False


# --------------------------------------------------------------------------- #
# 上下文裁剪结果（slice 的返回类型）
# --------------------------------------------------------------------------- #
class BundleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    artifact: Artifact
    est_tokens: int


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BundleItem] = Field(default_factory=list)
    total_tokens: int = 0
    dropped: list[str] = Field(default_factory=list)
