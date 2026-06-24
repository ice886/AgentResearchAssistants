"""arXiv API 客户端：按查询检索论文，返回 LitEntry 列表。"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ..models import LitEntry

_BASE = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def search_arxiv(query: str, max_results: int = 5) -> list[LitEntry]:
    """调用 arXiv API，返回至多 max_results 个 LitEntry。"""
    params = urllib.parse.urlencode({
        "search_query": query,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{_BASE}?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        data = resp.read().decode("utf-8")
    return _parse(data)


def _parse(xml_text: str) -> list[LitEntry]:
    root = ET.fromstring(xml_text)
    entries: list[LitEntry] = []
    for entry in root.findall("atom:entry", _NS):
        arxiv_id = _text(entry, "atom:id", "")
        if "/" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("/", 1)[-1]
        title = _text(entry, "atom:title", "").replace("\n", " ").strip()
        summary = _text(entry, "atom:summary", "").replace("\n", " ").strip()
        citation_key = arxiv_id.replace(".", "_").replace("/", "_")
        entries.append(LitEntry(
            arxiv_id=arxiv_id,
            title=title,
            summary=summary[:500],
            relevance=1.0,
            citation_key=citation_key,
        ))
    return entries


def _text(elem: ET.Element, tag: str, default: str) -> str:
    child = elem.find(tag, _NS)
    return (child.text or default) if child is not None else default
