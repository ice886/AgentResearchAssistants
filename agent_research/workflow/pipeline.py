"""StateGraph：节点序列 + 线性转移（数据驱动，不依赖 SDK）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    """工作流节点。is_checkpoint=True 时为人工检查点，否则 handler 为执行逻辑。"""

    id: str
    is_checkpoint: bool = False
    handler: Callable[[], Any] | None = field(default=None, compare=False)


class StateGraph:
    """有序节点序列 + O(1) id→index 查找。"""

    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = list(nodes)
        self._index: dict[str, int] = {n.id: i for i, n in enumerate(self._nodes)}

    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes)

    def get(self, node_id: str) -> Node:
        try:
            return self._nodes[self._index[node_id]]
        except KeyError:
            raise KeyError(f"节点不存在: {node_id!r}") from None

    def next_node(self, node_id: str) -> Node | None:
        i = self._index.get(node_id)
        if i is None:
            raise KeyError(f"节点不存在: {node_id!r}")
        nxt = i + 1
        return self._nodes[nxt] if nxt < len(self._nodes) else None
