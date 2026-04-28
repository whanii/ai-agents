from __future__ import annotations

from typing import Any, Dict, List, Optional


def fetch_items(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or {}
    subreddits = config.get("subreddits", ["LocalLLaMA", "MachineLearning"])
    limit = int(config.get("limit_per_subreddit", 5))
    items: List[Dict[str, Any]] = []

    try:
        import requests

        for subreddit in subreddits:
            url = f"https://www.reddit.com/r/{subreddit}/top.json?limit={limit}&t=day"
            response = requests.get(
                url,
                headers={"User-Agent": "ai-agent-trends/1.0"},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()

            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                permalink = post.get("permalink", "")
                target_url = post.get("url_overridden_by_dest") or f"https://www.reddit.com{permalink}"
                items.append(
                    {
                        "title": post.get("title", ""),
                        "url": target_url,
                        "source": "Reddit",
                        "summary": post.get("selftext", "")[:280],
                        "score": int(post.get("score") or 0),
                        "created_at": post.get("created_utc", ""),
                        "topic_tags": [],
                    }
                )

        return [item for item in items if item.get("title") and item.get("url")]
    except Exception as exc:
        print(f"[fetch][reddit] failed: {type(exc).__name__}: {exc}")
        return []


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
