"""models.py 单测：payload 校验、判别联合往返、Artifact 校验、Message。"""

from __future__ import annotations

import math

import pytest
from conftest import (
    make_code,
    make_idea,
    make_lit_review,
    make_plan,
    make_runs,
)
from pydantic import ValidationError

from agent_research.harness.enums import Intent, Namespace, RoleName
from agent_research.harness.models import (
    Artifact,
    ArtifactAdapter,
    DatasetSpec,
    Message,
    ResearchIdea,
)


def test_payload_extra_forbidden():
    with pytest.raises(ValidationError):
        ResearchIdea(title="t", motivation="m", bogus="x")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "factory",
    [make_idea, make_code, make_plan, make_lit_review, make_runs],
)
def test_artifact_roundtrip_all_namespaces(factory):
    art = factory()
    dumped = art.model_dump(mode="json")
    restored = ArtifactAdapter.validate_python(dumped)
    assert restored == art
    assert type(restored.payload) is type(art.payload)
    # kind 与 namespace 一致
    assert restored.namespace == restored.payload.kind


def test_every_namespace_has_a_payload_in_union():
    """判别联合应覆盖全部命名空间（防漏注册）。"""
    art_factories = {
        Namespace.IDEA: make_idea,
        Namespace.CODE: make_code,
        Namespace.PLAN: make_plan,
        Namespace.LIT_REVIEW: make_lit_review,
        Namespace.RUNS: make_runs,
    }
    for ns, factory in art_factories.items():
        assert factory().namespace == ns


def _idea_payload() -> ResearchIdea:
    return ResearchIdea(title="t", motivation="m")


def test_id_validator_rejects_bad_format():
    with pytest.raises(ValidationError):
        Artifact(id="badformat", created_by=RoleName.PHD, payload=_idea_payload())


def test_id_validator_rejects_unknown_namespace():
    with pytest.raises(ValidationError):
        Artifact(id="foo.x", created_by=RoleName.PHD, payload=_idea_payload())


def test_namespace_payload_mismatch_rejected():
    with pytest.raises(ValidationError):
        # paper.* 命名空间却塞 idea payload
        Artifact(id="paper.main", created_by=RoleName.PHD, payload=_idea_payload())


def test_non_finite_score_rejected():
    for bad in (math.inf, math.nan, -math.inf):
        with pytest.raises(ValidationError):
            Artifact(
                id="idea.main",
                created_by=RoleName.PHD,
                score=bad,
                payload=ResearchIdea(title="t", motivation="m"),
            )


def test_dataset_schema_alias_roundtrip():
    art = Artifact(
        id="dataset.main",
        created_by=RoleName.SW_ENGINEER,
        payload=DatasetSpec(source="hf", schema="image->label"),
    )
    dumped = art.model_dump(mode="json", by_alias=True)
    assert dumped["payload"]["schema"] == "image->label"
    restored = ArtifactAdapter.validate_python(dumped)
    assert restored.payload == art.payload


def test_message_all_intents_and_broadcast():
    for intent in Intent:
        msg = Message(
            from_role=RoleName.PHD,
            to=[RoleName.POSTDOC, RoleName.PROFESSOR],
            intent=intent,
            blackboard_refs=["plan.main@1"],
        )
        assert msg.intent == intent
    single = Message(from_role=RoleName.PHD, to=RoleName.POSTDOC, intent=Intent.PROPOSE)
    assert single.to == RoleName.POSTDOC
