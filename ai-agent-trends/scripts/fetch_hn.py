from __future__ import annotations

from typing import Any, Dict, List, Optional

MOCK_ITEMS: List[Dict[str, Any]] = [
    {
        "title": "Teams are using AI agents for internal security review checklists",
        "url": "https://example.com/hn-security-review-agents",
        "source": "Hacker News",
        "summary": "Discussion highlights practical guardrails for agent-assisted architecture reviews in production.",
        "score": 0,
        "created_at": "2026-04-15T06:40:00+09:00",
        "topic_tags": ["AI Agent & Automation", "AI Security"],
    },
    {
        "title": "What breaks first in tool-using coding agents?",
        "url": "https://example.com/hn-tool-using-agents",
        "source": "Hacker News",
        "summary": "Practitioners compare failure modes around tool permissions, memory, and evaluation loops.",
        "score": 0,
        "created_at": "2026-04-15T05:55:00+09:00",
        "topic_tags": ["AI Agent & Automation", "MCP / tool use / skills"],
    },
]


def fetch_items(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or {}
    url = config.get(
        "api_url",
        "https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=20",
    )
    limit = int(config.get("limit", 15))

    try:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": "ai-agent-trends/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()

        items: List[Dict[str, Any]] = []
        for hit in payload.get("hits", [])[:limit]:
            title = hit.get("title") or hit.get("story_title")
            target_url = hit.get("url") or hit.get("story_url")
            if not title or not target_url:
                continue
            items.append(
                {
                    "title": title,
                    "url": target_url,
                    "source": "Hacker News",
                    "summary": "",
                    "score": int(hit.get("points") or 0),
                    "created_at": hit.get("created_at") or "",
                    "topic_tags": [],
                }
            )

        return items or MOCK_ITEMS[:]
    except Exception:
        return MOCK_ITEMS[:]


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
