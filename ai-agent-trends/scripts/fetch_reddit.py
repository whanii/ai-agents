from __future__ import annotations

from typing import Any, Dict, List, Optional

MOCK_ITEMS: List[Dict[str, Any]] = [
    {
        "title": "Practitioners share MCP-style tool use patterns for local agents",
        "url": "https://example.com/reddit-mcp-tool-patterns",
        "source": "Reddit",
        "summary": "A community thread compares tool registries, permission models, and prompt contracts for agent systems.",
        "score": 0,
        "created_at": "2026-04-15T02:20:00+09:00",
        "topic_tags": ["MCP / tool use / skills", "AI Agent & Automation"],
    },
    {
        "title": "Automation case: triaging security alerts with LLM workflows",
        "url": "https://example.com/reddit-security-alert-automation",
        "source": "Reddit",
        "summary": "Operators discuss where AI automation helps alert triage and where human review is still mandatory.",
        "score": 0,
        "created_at": "2026-04-14T23:50:00+09:00",
        "topic_tags": ["AI Agent & Automation", "AI Security"],
    },
]


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

        filtered = [item for item in items if item.get("title") and item.get("url")]
        return filtered or MOCK_ITEMS[:]
    except Exception:
        return MOCK_ITEMS[:]


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
