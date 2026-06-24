"""config.py 单测：默认值、环境覆盖、SecretStr 屏蔽、RunPaths、ModelConfig。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_research.config import ModelConfig, RunPaths, Settings
from agent_research.harness.enums import RoleName


def test_defaults():
    s = Settings()
    assert s.runs_dir == Path("runs")
    assert s.limits.container_cpus == 2.0
    assert s.docker.network_policy == "none"
    assert s.docker.run_as_non_root is True


def test_env_override_scalar_and_nested(monkeypatch):
    monkeypatch.setenv("AR_RUNS_DIR", "/tmp/myruns")
    monkeypatch.setenv("AR_LIMITS__CONTAINER_CPUS", "8")
    s = Settings()
    assert s.runs_dir == Path("/tmp/myruns")
    assert s.limits.container_cpus == 8.0


def test_resource_limits_must_be_positive(monkeypatch):
    monkeypatch.setenv("AR_LIMITS__MAX_CONCURRENT_CONTAINERS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_env_file_loaded(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AR_RUNS_DIR=from_env_file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.runs_dir == Path("from_env_file")


def test_secret_masked_in_repr_and_dump(monkeypatch):
    monkeypatch.setenv("AR_ANTHROPIC_API_KEY", "sk-secret-123")
    s = Settings()
    assert "sk-secret-123" not in repr(s)
    assert "sk-secret-123" not in str(s.model_dump())
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value() == "sk-secret-123"


def test_run_paths_properties_and_ensure(tmp_path):
    rp = RunPaths(root=tmp_path / "run-x")
    assert rp.blackboard_json == tmp_path / "run-x" / "blackboard.json"
    assert rp.code_dir == tmp_path / "run-x" / "code"
    rp.ensure()
    rp.ensure()  # 幂等
    for d in (
        rp.code_dir,
        rp.experiments_dir,
        rp.paper_dir,
        rp.logs_dir,
        rp.lit_review_dir,
    ):
        assert d.is_dir()


def test_settings_run_paths():
    s = Settings(runs_dir=Path("/data/runs"))
    rp = s.run_paths("run-42")
    assert rp.root == Path("/data/runs/run-42")


def test_model_config_for_role_fallback_and_override():
    mc = ModelConfig(
        default_model="claude-default",
        per_role={RoleName.REVIEWER: "claude-reviewer"},
    )
    assert mc.for_role(RoleName.REVIEWER) == "claude-reviewer"
    assert mc.for_role(RoleName.PHD) == "claude-default"
