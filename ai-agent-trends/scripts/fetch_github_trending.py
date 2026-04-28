from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def fetch_items(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or {}
    url = config.get("url", "https://github.com/trending?since=daily")
    limit = int(config.get("limit", 10))

    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(
            url,
            headers={"User-Agent": "ai-agent-trends/1.0"},
            timeout=20,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()

        for article in soup.select("article.Box-row")[:limit]:
            link = article.select_one("h2 a")
            if not link:
                continue
            repo_path = " ".join(link.get_text(" ", strip=True).split())
            repo_path = repo_path.replace(" / ", "/")
            description = article.select_one("p")
            items.append(
                {
                    "title": repo_path,
                    "url": f"https://github.com{link.get('href', '').strip()}",
                    "source": "GitHub Trending",
                    "summary": description.get_text(" ", strip=True) if description else "",
                    "score": 0,
                    "created_at": now,
                    "topic_tags": [],
                }
            )

        return items
    except Exception as exc:
        print(f"[fetch][github_trending] failed: {type(exc).__name__}: {exc}")
        return []


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
