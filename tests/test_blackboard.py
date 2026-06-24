"""blackboard.py 单测：CAS、版本链、get、订阅、slice。"""

from __future__ import annotations

import pytest
from conftest import make_code, make_idea, make_runs

from agent_research.harness.blackboard import (
    ArtifactNotFoundError,
    Blackboard,
    VersionConflictError,
)
from agent_research.harness.enums import Namespace


def test_first_write_ev0_gives_v1_parent_none(bb: Blackboard):
    v = bb.set(make_code(), expected_version=0)
    assert v == 1
    art = bb.get("code.main")
    assert art.version == 1
    assert art.parent_version is None


def test_first_write_nonzero_ev_conflicts(bb: Blackboard):
    with pytest.raises(VersionConflictError):
        bb.set(make_code(), expected_version=1)
    assert not bb.exists("code.main")


def test_sequential_versions_monotonic_with_parent_chain(bb: Blackboard):
    assert bb.set(make_code("a.py"), expected_version=0) == 1
    assert bb.set(make_code("b.py"), expected_version=1) == 2
    assert bb.set(make_code("c.py"), expected_version=2) == 3
    assert bb.history("code.main") == [1, 2, 3]
    assert bb.get("code.main", 2).parent_version == 1
    assert bb.get("code.main").version == 3


def test_stale_expected_version_conflicts_and_store_unchanged(bb: Blackboard):
    bb.set(make_code("a.py"), expected_version=0)
    bb.set(make_code("b.py"), expected_version=1)
    with pytest.raises(VersionConflictError) as exc:
        bb.set(make_code("stale.py"), expected_version=1)
    assert exc.value.expected == 1
    assert exc.value.actual == 2
    assert bb.history("code.main") == [1, 2]
    assert bb.get("code.main").payload.entrypoint == "b.py"


def test_get_latest_pinned_and_missing(bb: Blackboard):
    bb.set(make_code("a.py"), expected_version=0)
    bb.set(make_code("b.py"), expected_version=1)
    assert bb.get("code.main", "latest").payload.entrypoint == "b.py"
    assert bb.get("code.main", 1).payload.entrypoint == "a.py"
    with pytest.raises(ArtifactNotFoundError):
        bb.get("code.main", 99)
    with pytest.raises(ArtifactNotFoundError):
        bb.get("nope.x")


def test_history_missing_raises(bb: Blackboard):
    with pytest.raises(ArtifactNotFoundError):
        bb.history("nope.x")


def test_subscribe_fires_only_matching_namespace(bb: Blackboard):
    seen: list[str] = []
    bb.subscribe(Namespace.CODE, lambda a: seen.append(a.id))
    bb.set(make_idea(), expected_version=0)  # 不应触发
    bb.set(make_code(), expected_version=0)  # 应触发
    assert seen == ["code.main"]


def test_bad_subscriber_does_not_break_set(bb: Blackboard):
    def boom(_a):
        raise RuntimeError("boom")

    bb.subscribe(Namespace.CODE, boom)
    v = bb.set(make_code(), expected_version=0)
    assert v == 1  # 写入仍成功


def test_ref_stores_path_not_blob(bb: Blackboard):
    bb.set(make_runs(), expected_version=0)
    rec = bb.get("runs.main").payload.records[0]
    assert rec.stdout_ref == "experiments/run1/stdout.txt"


def test_slice_budget_cutoff_and_unknown_and_pinned(bb: Blackboard):
    bb.set(make_idea(), expected_version=0)
    bb.set(make_code(), expected_version=0)
    # 极小预算 → 第一个就放不下
    tiny = bb.slice(["idea.main", "code.main"], budget_tokens=1)
    assert tiny.items == []
    assert set(tiny.dropped) == {"idea.main", "code.main"}
    # 充足预算 + 未知 ref + pinned 版本
    big = bb.slice(["idea.main@1", "code.main", "missing.x"], budget_tokens=10_000)
    assert {it.ref for it in big.items} == {"idea.main@1", "code.main"}
    assert big.dropped == ["missing.x"]
    assert big.total_tokens == sum(it.est_tokens for it in big.items)
