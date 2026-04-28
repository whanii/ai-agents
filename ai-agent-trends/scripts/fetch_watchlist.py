from __future__ import annotations

from typing import Any, Dict, List, Optional
from xml.etree import ElementTree


def fetch_items(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or {}
    feeds = config.get("feeds", [])
    limit_per_feed = int(config.get("limit_per_feed", 4))
    items: List[Dict[str, Any]] = []

    try:
        import requests
    except Exception as exc:
        print(f"[fetch][watchlist] failed: {type(exc).__name__}: {exc}")
        return []

    for feed in feeds:
        feed_name = str(feed.get("name", "Watchlist")) if isinstance(feed, dict) else "Watchlist"
        feed_url = str(feed.get("url", "")) if isinstance(feed, dict) else str(feed)
        if not feed_url:
            continue
        try:
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
                        "source": f"Watchlist: {feed_name}",
                        "source_reliability_score": 12,
                        "summary": entry.get("summary", ""),
                        "score": 0,
                        "created_at": entry.get("created_at", ""),
                        "topic_tags": [],
                    }
                )
        except Exception as exc:
            print(f"[fetch][watchlist] feed failed: {feed_name} | {type(exc).__name__}: {exc}")

    return [item for item in items if item.get("title") and item.get("url")]


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
