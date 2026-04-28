from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

SOURCE_WEIGHTS = {
    "GitHub Trending": 24,
    "Hacker News": 22,
    "Reddit": 18,
    "RSS News": 20,
    "Discovery": 16,
    "Watchlist": 21,
}

PRACTICAL_KEYWORDS = {
    "automation": 8,
    "workflow": 7,
    "template": 6,
    "starter": 6,
    "review": 7,
    "checklist": 6,
    "guardrail": 7,
    "tool": 5,
    "mcp": 5,
    "policy": 5,
    "production": 7,
    "inference": 7,
    "benchmark": 5,
    "security": 6,
    "vulnerability": 7,
    "agent": 5,
    "agents": 5,
    "llm": 5,
    "local": 4,
}

NOVELTY_KEYWORDS = {
    "new": 5,
    "emerging": 5,
    "gains traction": 7,
    "expands": 6,
    "first": 5,
    "local agents": 4,
    "agent workflows": 5,
    "threat modeling": 4,
    "release": 5,
    "update": 4,
    "benchmark": 4,
    "weights": 5,
    "open source": 4,
}


def rank_items(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    ranked: List[Dict[str, object]] = []
    now = datetime.now(timezone.utc)

    for item in items:
        ranked_item = dict(item)
        source_field = str(item.get("source", ""))
        base_source = source_field.split(" | ")[0].split(":")[0] if source_field else ""
        raw_score = int(item.get("score", 0))
        source_reliability_score = int(item.get("source_reliability_score", 0))
        discovery_penalty = _discovery_penalty(item)
        topic_tags = list(item.get("topic_tags", []))
        practicality_score = _practicality_points(item)
        novelty_score = _novelty_points(item)
        cross_source_score = _cross_source_points(source_field)
        source_bonus = SOURCE_WEIGHTS.get(base_source, 10)
        topical_bonus = len(topic_tags) * 6
        recency_bonus = _recency_points(str(item.get("created_at", "")), now)
        popularity_bonus = min(raw_score, 100) // 5
        ranked_item["practicality_score"] = practicality_score
        ranked_item["novelty_score"] = novelty_score
        ranked_item["cross_source_score"] = cross_source_score
        ranked_item["source_reliability_score"] = source_reliability_score
        ranked_item["discovery_penalty"] = discovery_penalty
        ranked_item["score"] = (
            source_bonus
            + cross_source_score
            + topical_bonus
            + recency_bonus
            + popularity_bonus
            + source_reliability_score
            + practicality_score
            + novelty_score
            - discovery_penalty
        )
        ranked.append(ranked_item)

    return sorted(ranked, key=lambda item: int(item.get("score", 0)), reverse=True)


def _recency_points(created_at: str, now: datetime) -> int:
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except Exception:
        return 8

    age_hours = max((now - created).total_seconds() / 3600.0, 0)
    if age_hours <= 6:
        return 20
    if age_hours <= 24:
        return 14
    if age_hours <= 72:
        return 8
    return 3


def _practicality_points(item: Dict[str, object]) -> int:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("summary", "")),
            " ".join(str(tag) for tag in item.get("topic_tags", [])),
        ]
    ).lower()
    score = 0
    for keyword, points in PRACTICAL_KEYWORDS.items():
        if keyword in haystack:
            score += points
    return min(score, 24)


def _novelty_points(item: Dict[str, object]) -> int:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("summary", "")),
        ]
    ).lower()
    score = 0
    for keyword, points in NOVELTY_KEYWORDS.items():
        if keyword in haystack:
            score += points
    return min(score, 16)


def _cross_source_points(source_field: str) -> int:
    sources = [source.strip() for source in source_field.split(" | ") if source.strip()]
    if len(sources) >= 3:
        return 18
    if len(sources) == 2:
        return 12
    return 0


def _discovery_penalty(item: Dict[str, object]) -> int:
    source = str(item.get("source", ""))
    if not source.startswith("Discovery:"):
        return 0

    penalty = 6
    reliability = int(item.get("source_reliability_score", 0))
    if reliability >= 8:
        penalty -= 2

    summary = str(item.get("summary", "")).strip()
    if len(summary) >= 40 and not summary.lower().startswith("discovered from"):
        penalty -= 2

    return max(penalty, 0)
