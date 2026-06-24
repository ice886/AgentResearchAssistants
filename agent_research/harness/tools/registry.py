"""ToolRegistry：工具注册、按角色授权与安全执行路由。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..enums import RoleName
from ..sandbox import Command, ExecResult, SandboxManager, SandboxSpec

ToolHandler = Callable[[Mapping[str, Any]], Any]


class ToolRegistryError(Exception):
    """ToolRegistry 相关错误基类。"""


class ToolAuthorizationError(ToolRegistryError):
    """角色无权访问工具。"""


class ToolValidationError(ToolRegistryError):
    """工具定义或调用参数不合法。"""


@dataclass(frozen=True)
class ToolSpec:
    """注册到 harness 的工具定义。"""

    name: str
    description: str
    handler: ToolHandler
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ToolValidationError(f"工具名不合法: {self.name!r}")


class ToolRegistry:
    """统一注册工具，并按 RoleName 暴露最小权限子集。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._allowed_roles: dict[str, frozenset[RoleName]] = {}

    def register(
        self,
        tool: ToolSpec,
        allowed_roles: set[RoleName] | frozenset[RoleName],
    ) -> None:
        if not allowed_roles:
            raise ToolValidationError(f"工具 {tool.name!r} 必须至少授权一个角色")
        if tool.name in self._tools:
            raise ToolValidationError(f"工具已注册: {tool.name!r}")
        self._tools[tool.name] = tool
        self._allowed_roles[tool.name] = frozenset(allowed_roles)

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolValidationError(f"工具不存在: {name!r}") from None

    def tools_for(self, role: RoleName) -> list[ToolSpec]:
        return [
            tool
            for name, tool in self._tools.items()
            if role in self._allowed_roles[name]
        ]

    def assert_allowed(self, role: RoleName, tool_name: str) -> None:
        if role not in self._allowed_roles.get(tool_name, frozenset()):
            raise ToolAuthorizationError(
                f"角色 {role.value!r} 无权访问工具 {tool_name!r}"
            )

    def call(self, role: RoleName, tool_name: str, payload: Mapping[str, Any]) -> Any:
        self.assert_allowed(role, tool_name)
        return self.get(tool_name).handler(payload)


def make_run_code_tool(sandbox: SandboxManager) -> ToolSpec:
    """创建唯一通过 SandboxManager 执行代码的工具。"""

    def _run_code(payload: Mapping[str, Any]) -> ExecResult:
        cmd = _require_command(payload)
        timeout_s = payload.get("timeout_s")
        spec = payload.get("sandbox")
        if spec is not None and not isinstance(spec, SandboxSpec):
            raise ToolValidationError("sandbox 必须是 SandboxSpec")
        if timeout_s is not None and not isinstance(timeout_s, int | float):
            raise ToolValidationError("timeout_s 必须是数字")

        handle = sandbox.spawn(spec)
        try:
            return sandbox.run(handle, cmd, timeout_s=timeout_s)
        finally:
            sandbox.teardown(handle)

    return ToolSpec(
        name="run_code",
        description="在 Docker SandboxManager 内执行命令；不得直接触达宿主机。",
        handler=_run_code,
        input_schema={
            "type": "object",
            "required": ["cmd"],
            "properties": {
                "cmd": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
                "timeout_s": {"type": "number"},
            },
        },
        metadata={"category": "execution", "sandboxed": True},
    )


def _require_command(payload: Mapping[str, Any]) -> Command:
    cmd = payload.get("cmd")
    if isinstance(cmd, str):
        return cmd
    if isinstance(cmd, list | tuple) and all(isinstance(part, str) for part in cmd):
        return tuple(cmd)
    raise ToolValidationError("cmd 必须是字符串或字符串列表")
