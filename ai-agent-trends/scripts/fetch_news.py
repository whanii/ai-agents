from __future__ import annotations

from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

MOCK_ITEMS: List[Dict[str, Any]] = [
    {
        "title": "Why security teams are threat modeling agent workflows",
        "url": "https://example.com/news-threat-modeling-agent-workflows",
        "source": "RSS News",
        "summary": "Coverage describes how organizations are adapting classic threat modeling to AI copilots and autonomous tasks.",
        "score": 0,
        "created_at": "2026-04-15T08:30:00+09:00",
        "topic_tags": ["threat modeling", "AI Agent & Automation"],
    },
    {
        "title": "Enterprise AI automation expands into architecture review",
        "url": "https://example.com/news-architecture-review-automation",
        "source": "RSS News",
        "summary": "Analysts note growing demand for workflow automation that assists design reviews and policy checks.",
        "score": 0,
        "created_at": "2026-04-15T08:50:00+09:00",
        "topic_tags": ["AI Agent & Automation", "AI Security"],
    },
]


def fetch_items(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or {}
    feeds = config.get("feeds", [])
    limit_per_feed = int(config.get("limit_per_feed", 8))
    items: List[Dict[str, Any]] = []

    try:
        import requests

        for feed_url in feeds:
            response = requests.get(
                feed_url,
                headers={"User-Agent": "ai-agent-trends/1.0"},
                timeout=20,
            )
            response.raise_for_status()

            root = ElementTree.fromstring(response.content)
            for entry in _extract_entries(root)[:limit_per_feed]:
                items.append(
                    {
                        "title": entry.get("title", ""),
                        "url": entry.get("url", ""),
                        "source": "RSS News",
                        "summary": entry.get("summary", ""),
                        "score": 0,
                        "created_at": entry.get("created_at", ""),
                        "topic_tags": [],
                    }
                )

        filtered = [item for item in items if item.get("title") and item.get("url")]
        return filtered or MOCK_ITEMS[:]
    except Exception:
        return MOCK_ITEMS[:]


def _extract_entries(root: ElementTree.Element) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    namespace = "{http://www.w3.org/2005/Atom}"

    if root.tag.endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item"):
            items.append(
                {
                    "title": _text_or_empty(item.find("title")),
                    "url": _text_or_empty(item.find("link")),
                    "summary": _text_or_empty(item.find("description")),
                    "created_at": _text_or_empty(item.find("pubDate")),
                }
            )
        return items

    for entry in root.findall(f"{namespace}entry"):
        link = entry.find(f"{namespace}link")
        url = link.attrib.get("href", "") if link is not None else ""
        items.append(
            {
                "title": _text_or_empty(entry.find(f"{namespace}title")),
                "url": url,
                "summary": _text_or_empty(entry.find(f"{namespace}summary"))
                or _text_or_empty(entry.find(f"{namespace}content")),
                "created_at": _text_or_empty(entry.find(f"{namespace}updated"))
                or _text_or_empty(entry.find(f"{namespace}published")),
            }
        )
    return items


def _text_or_empty(node: Optional[ElementTree.Element]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
