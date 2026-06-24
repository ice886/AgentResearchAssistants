"""Blackboard：版本化共享状态 + CAS 乐观锁 + 持久化。

系统的"单一事实来源"。所有 agent 通过 id/版本引用读写制品，避免直接传大段文本。

- 版本权威在 Blackboard：``set`` 忽略入参 artifact 的 ``version``，自行单调赋号。
- CAS：``set(artifact, expected_version)`` 当 ``expected_version`` 与当前 latest 不符时
  拒写（抛 ``VersionConflictError``），调用方需重读再写。
- 旧版本全部保留，支持 solver 回滚（``code@v3 → code@v2``）。
- 持久化为单一 ``blackboard.json``，原子写（tmp + os.replace），断点可恢复。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from ..config import RunPaths
from .enums import Namespace
from .models import Artifact, ArtifactAdapter, BundleItem, ContextBundle

LATEST = "latest"

SCHEMA_VERSION = 1

Subscriber = Callable[[Artifact], None]
TokenEstimator = Callable[[str], int]


class BlackboardError(Exception):
    """Blackboard 相关错误基类。"""


class ArtifactNotFoundError(BlackboardError):
    def __init__(self, id: str, version: object = LATEST) -> None:
        super().__init__(f"制品不存在: id={id!r} version={version!r}")
        self.id = id
        self.version = version


class VersionConflictError(BlackboardError):
    """CAS 失败：expected_version 与当前 latest 不一致。"""

    def __init__(self, id: str, expected: int, actual: int) -> None:
        super().__init__(
            f"版本冲突 id={id!r}: expected={expected} actual={actual}，请重读后再写"
        )
        self.id = id
        self.expected = expected
        self.actual = actual


def _default_estimator(text: str) -> int:
    """粗略估词：约 4 字符/词。"""
    return max(1, len(text) // 4)


class Blackboard:
    """版本化制品存储。同步方法，单 asyncio 事件循环下原子。"""

    def __init__(
        self,
        paths: RunPaths,
        token_estimator: TokenEstimator | None = None,
    ) -> None:
        self._paths = paths
        self._store: dict[str, list[Artifact]] = {}
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._estimate = token_estimator or _default_estimator

    # ----------------------------------------------------------------- 读 --- #
    def exists(self, id: str) -> bool:
        return id in self._store

    def ids(self) -> list[str]:
        return list(self._store.keys())

    def history(self, id: str) -> list[int]:
        if id not in self._store:
            raise ArtifactNotFoundError(id)
        return [a.version for a in self._store[id]]

    def get(self, id: str, version: int | str = LATEST) -> Artifact:
        versions = self._store.get(id)
        if not versions:
            raise ArtifactNotFoundError(id, version)
        if version == LATEST:
            return versions[-1]
        for a in versions:
            if a.version == version:
                return a
        raise ArtifactNotFoundError(id, version)

    # ----------------------------------------------------------------- 写 --- #
    def set(self, artifact: Artifact, expected_version: int) -> int:
        """CAS 写入，返回新版本号。版本权威在 Blackboard。

        - 新 id：要求 ``expected_version == 0``，否则冲突；赋 version=1。
        - 既有 id：``expected_version`` 必须等于当前 latest，否则冲突且 store 不变。
        """
        versions = self._store.get(artifact.id)
        current = versions[-1].version if versions else 0
        if expected_version != current:
            raise VersionConflictError(artifact.id, expected_version, current)

        new_version = current + 1
        parent = current if current > 0 else None
        stored = artifact.model_copy(
            update={"version": new_version, "parent_version": parent}
        )
        if versions is None:
            self._store[artifact.id] = [stored]
        else:
            versions.append(stored)

        self._notify(stored)
        return new_version

    # --------------------------------------------------------------- 订阅 --- #
    def subscribe(self, namespace: Namespace | str, callback: Subscriber) -> None:
        key = namespace.value if isinstance(namespace, Namespace) else namespace
        self._subscribers.setdefault(key, []).append(callback)

    def _notify(self, artifact: Artifact) -> None:
        targets = self._subscribers.get(artifact.namespace.value, [])
        wildcard = self._subscribers.get("*", [])
        for cb in (*targets, *wildcard):
            try:
                cb(artifact)
            except Exception:  # noqa: BLE001 - 坏订阅者不得影响写入
                pass

    # ----------------------------------------------------------- 上下文裁剪 --- #
    def slice(self, refs: list[str], budget_tokens: int) -> ContextBundle:
        """按 ref 顺序累加到 token 预算上限。

        TODO 里程碑6：替换为按相关性裁剪 + 摘要。当前为确定性桩实现。
        ref 形如 ``id`` 或 ``id@version``；未知 ref 进 ``dropped``。
        """
        bundle = ContextBundle()
        for ref in refs:
            id_, version = self._parse_ref(ref)
            try:
                artifact = self.get(id_, version)
            except ArtifactNotFoundError:
                bundle.dropped.append(ref)
                continue
            est = self._estimate(artifact.payload.model_dump_json())
            if bundle.total_tokens + est > budget_tokens:
                bundle.dropped.append(ref)
                continue
            bundle.items.append(BundleItem(ref=ref, artifact=artifact, est_tokens=est))
            bundle.total_tokens += est
        return bundle

    @staticmethod
    def _parse_ref(ref: str) -> tuple[str, int | str]:
        if "@" in ref:
            id_, ver = ref.rsplit("@", 1)
            if ver != LATEST:
                try:
                    return id_, int(ver)
                except ValueError:
                    return id_, ver
            return id_, LATEST
        return ref, LATEST

    # ------------------------------------------------------------- 持久化 --- #
    def snapshot(self) -> Path:
        """原子写 ``blackboard.json``，返回路径。"""
        path = self._paths.blackboard_json
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": SCHEMA_VERSION,
            "artifacts": {
                id_: [a.model_dump(mode="json") for a in versions]
                for id_, versions in self._store.items()
            },
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return path

    @classmethod
    def restore(
        cls,
        paths: RunPaths,
        token_estimator: TokenEstimator | None = None,
    ) -> Blackboard:
        """从 ``blackboard.json`` 恢复；文件缺失则返回空 Blackboard。"""
        bb = cls(paths, token_estimator=token_estimator)
        path = paths.blackboard_json
        if not path.exists():
            return bb
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise BlackboardError(f"blackboard.json 损坏，无法解析: {e}") from e
        for id_, versions in data.get("artifacts", {}).items():
            bb._store[id_] = [ArtifactAdapter.validate_python(v) for v in versions]
        return bb
