"""snapshot/restore 单测：往返深相等、原子写、缺失/损坏处理。"""

from __future__ import annotations

import json

import pytest
from conftest import make_code, make_idea, make_runs

from agent_research.config import RunPaths
from agent_research.harness.blackboard import Blackboard, BlackboardError


def _populate(bb: Blackboard) -> None:
    bb.set(make_idea(), expected_version=0)
    bb.set(make_code("a.py"), expected_version=0)
    bb.set(make_code("b.py"), expected_version=1)
    bb.set(make_runs(), expected_version=0)


def test_snapshot_has_schema_version(bb: Blackboard, run_paths: RunPaths):
    _populate(bb)
    path = bb.snapshot()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert set(data["artifacts"]) == {"idea.main", "code.main", "runs.main"}


def test_restore_deep_equals_original(bb: Blackboard, run_paths: RunPaths):
    _populate(bb)
    bb.snapshot()
    restored = Blackboard.restore(run_paths)
    assert restored._store == bb._store
    assert restored.history("code.main") == [1, 2]
    assert restored.get("code.main", 2).parent_version == 1


def test_no_tmp_file_left(bb: Blackboard, run_paths: RunPaths):
    _populate(bb)
    bb.snapshot()
    leftovers = list(run_paths.root.glob("*.tmp"))
    assert leftovers == []


def test_restore_missing_file_is_empty(run_paths: RunPaths):
    bb = Blackboard.restore(run_paths)
    assert bb.ids() == []


def test_restore_corrupted_json_raises(bb: Blackboard, run_paths: RunPaths):
    run_paths.blackboard_json.write_text("{ not json", encoding="utf-8")
    with pytest.raises(BlackboardError):
        Blackboard.restore(run_paths)
