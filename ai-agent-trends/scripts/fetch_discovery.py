from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def fetch_items(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    config = config or {}
    queries = [str(query).strip() for query in config.get("queries", []) if str(query).strip()]
    limit = int(config.get("limit_per_query", 4))
    items: List[Dict[str, Any]] = []

    try:
        import requests
    except Exception as exc:
        print(f"[fetch][discovery] failed: {type(exc).__name__}: {exc}")
        return []

    max_items = int(config.get("max_items_per_query", limit))
    for query in queries:
        items.extend(_fetch_hn_query(requests, query, limit, config)[:max_items])
        items.extend(_fetch_github_query(requests, query, limit, config)[:max_items])

    return [item for item in items if item.get("title") and item.get("url")]


def _fetch_hn_query(requests: Any, query: str, limit: int, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    api_url = str(config.get("hacker_news_api_url", "https://hn.algolia.com/api/v1/search_by_date"))
    try:
        response = requests.get(
            api_url,
            params={"query": query, "tags": "story", "hitsPerPage": limit},
            headers={"User-Agent": "ai-agent-trends/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[fetch][discovery][hn] query failed: {query} | {type(exc).__name__}: {exc}")
        return []

    items: List[Dict[str, Any]] = []
    for hit in payload.get("hits", [])[:limit]:
        title = hit.get("title") or hit.get("story_title")
        target_url = hit.get("url") or hit.get("story_url")
        points = int(hit.get("points") or 0)
        if not title or not target_url:
            continue
        if not _passes_discovery_filter(title, points, "hn", config):
            continue
        items.append(
            {
                "title": title,
                "url": target_url,
                "source": "Discovery: Hacker News",
                "summary": f"Discovered from Hacker News search query: {query}",
                "score": points,
                "source_reliability_score": _source_reliability_score("hn", points),
                "created_at": hit.get("created_at") or "",
                "topic_tags": [],
            }
        )
    return items


def _fetch_github_query(requests: Any, query: str, limit: int, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    api_url = str(config.get("github_search_api_url", "https://api.github.com/search/repositories"))
    try:
        response = requests.get(
            api_url,
            params={"q": query, "sort": "updated", "order": "desc", "per_page": limit},
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ai-agent-trends/1.0",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"[fetch][discovery][github] query failed: {query} | {type(exc).__name__}: {exc}")
        return []

    now = datetime.now(timezone.utc).isoformat()
    items: List[Dict[str, Any]] = []
    for repo in payload.get("items", [])[:limit]:
        title = repo.get("full_name", "")
        target_url = repo.get("html_url", "")
        stars = int(repo.get("stargazers_count") or 0)
        if not title or not target_url:
            continue
        if not _passes_discovery_filter(title, stars, "github", config):
            continue
        items.append(
            {
                "title": title,
                "url": target_url,
                "source": "Discovery: GitHub Search",
                "summary": repo.get("description", "") or f"Discovered from GitHub search query: {query}",
                "score": stars,
                "source_reliability_score": _source_reliability_score("github", stars),
                "created_at": repo.get("updated_at") or now,
                "topic_tags": [],
            }
        )
    return items


def _passes_discovery_filter(title: str, score: int, source_kind: str, config: Dict[str, Any]) -> bool:
    normalized = title.lower()
    for pattern in config.get("exclude_title_patterns", []):
        if str(pattern).lower() in normalized:
            return False

    if source_kind == "hn":
        return score >= int(config.get("min_hn_points", 3))
    if source_kind == "github":
        return score >= int(config.get("min_github_stars", 20))
    return True


def _source_reliability_score(source_kind: str, score: int) -> int:
    if source_kind == "hn":
        if score >= 50:
            return 12
        if score >= 10:
            return 8
        return 4
    if source_kind == "github":
        if score >= 1000:
            return 12
        if score >= 100:
            return 8
        return 4
    return 0


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_items(), indent=2, ensure_ascii=False))
