from __future__ import annotations

from typing import Any, Dict, List, Optional


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

        return items
    except Exception as exc:
        print(f"[fetch][hacker_news] failed: {type(exc).__name__}: {exc}")
        return []


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
