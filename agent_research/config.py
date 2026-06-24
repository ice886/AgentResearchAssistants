"""集中配置：路径、资源限额、模型、Docker。

- 用 pydantic-settings ``BaseSettings``：内置 ``.env``、``AR_`` 前缀、嵌套覆盖。
- API key 用 ``SecretStr`` 屏蔽，在 repr/log/``model_dump`` 中不泄漏明文。
- ``RunPaths`` 是按 run_id 派生的目录助手，承载 ``runs/<run_id>/`` 布局。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .harness.enums import RoleName


class ResourceLimits(BaseModel):
    """沙箱容器与全局预算限额。"""

    container_cpus: float = 2.0
    container_mem_mb: int = 4096
    container_timeout_s: int = 600
    max_concurrent_containers: int = 2
    token_budget: int = 2_000_000


class DockerConfig(BaseModel):
    """沙箱镜像与安全策略。"""

    base_image_tag: str = "agent-research/base:latest"
    network_policy: str = "none"  # none | whitelist
    run_as_non_root: bool = True


class ModelConfig(BaseModel):
    """各角色使用的 Claude 模型 id。"""

    default_model: str = "claude-opus-4-8"
    per_role: dict[RoleName, str] = Field(default_factory=dict)

    def for_role(self, role: RoleName) -> str:
        """返回角色专属模型，缺省回退到 ``default_model``。"""
        return self.per_role.get(role, self.default_model)


@dataclass(frozen=True)
class RunPaths:
    """``runs/<run_id>/`` 目录布局助手（见架构设计 §5）。"""

    root: Path

    @property
    def blackboard_json(self) -> Path:
        return self.root / "blackboard.json"

    @property
    def decisions_json(self) -> Path:
        return self.root / "decisions.json"

    @property
    def budget_json(self) -> Path:
        return self.root / "budget.json"

    @property
    def code_dir(self) -> Path:
        return self.root / "code"

    @property
    def experiments_dir(self) -> Path:
        return self.root / "experiments"

    @property
    def paper_dir(self) -> Path:
        return self.root / "paper"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def lit_review_dir(self) -> Path:
        return self.root / "lit_review"

    def ensure(self) -> RunPaths:
        """幂等创建 run 根目录与全部子目录。"""
        for d in (
            self.root,
            self.code_dir,
            self.experiments_dir,
            self.paper_dir,
            self.logs_dir,
            self.lit_review_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self


class Settings(BaseSettings):
    """全局配置单例。环境变量前缀 ``AR_``，嵌套用 ``__``。"""

    model_config = SettingsConfigDict(
        env_prefix="AR_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    runs_dir: Path = Path("runs")
    limits: ResourceLimits = Field(default_factory=ResourceLimits)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    anthropic_api_key: SecretStr | None = None

    def run_paths(self, run_id: str) -> RunPaths:
        return RunPaths(root=self.runs_dir / run_id)


@lru_cache
def get_settings() -> Settings:
    """进程级配置单例。"""
    return Settings()
