from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, List, Optional


def deduplicate_items(items: List[Dict[str, object]], similarity_threshold: float = 0.90) -> List[Dict[str, object]]:
    deduped: List[Dict[str, object]] = []
    seen_urls = set()

    for item in items:
        url = str(item.get("url", ""))
        title = str(item.get("title", ""))
        if url in seen_urls:
            continue

        duplicate_index = _find_similar_index(title, deduped, similarity_threshold)
        if duplicate_index is None:
            seen_urls.add(url)
            deduped.append(item)
            continue

        # Merge near-duplicate titles so repeated themes can still be tracked across sources.
        existing = deduped[duplicate_index]
        merged = dict(existing)
        merged["score"] = max(int(existing.get("score", 0)), int(item.get("score", 0)))
        merged["topic_tags"] = sorted(
            set(list(existing.get("topic_tags", [])) + list(item.get("topic_tags", [])))
        )
        existing_sources = set(str(existing.get("source", "")).split(" | "))
        existing_sources.add(str(item.get("source", "")))
        merged["source"] = " | ".join(sorted(source for source in existing_sources if source))
        if len(str(item.get("summary", ""))) > len(str(existing.get("summary", ""))):
            merged["summary"] = item.get("summary", "")
        deduped[duplicate_index] = merged
        seen_urls.add(url)

    return deduped


def _find_similar_index(title: str, deduped: List[Dict[str, object]], threshold: float) -> Optional[int]:
    normalized_title = _normalize_title(title)
    for index, item in enumerate(deduped):
        other_title = _normalize_title(str(item.get("title", "")))
        if not normalized_title or not other_title:
            continue
        if SequenceMatcher(None, normalized_title, other_title).ratio() >= threshold:
            return index
    return None


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().split())
