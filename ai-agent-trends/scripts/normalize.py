from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT_DIR = Path(__file__).resolve().parent.parent
CLASSIFY_PROMPT_PATH = ROOT_DIR / "prompts" / "classify.md"


def load_config(path: Path) -> Dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw_text)
        return data or {}
    except Exception:
        # The config files are valid JSON as well, so this keeps the project runnable without PyYAML.
        return json.loads(raw_text)


def normalize_items(items: Iterable[Dict[str, Any]], topics_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in items:
        normalized_item = {
            "title": clean_text(item.get("title", "")),
            "url": canonicalize_url(item.get("url", "")),
            "source": clean_text(item.get("source", "")),
            "summary": clean_text(item.get("summary", "")),
            "score": safe_int(item.get("score", 0)),
            "source_reliability_score": safe_int(item.get("source_reliability_score", 0)),
            "created_at": normalize_datetime(item.get("created_at")),
            "topic_tags": classify_item(item, topics_config),
        }
        if normalized_item["title"] and normalized_item["url"]:
            normalized.append(normalized_item)
    return normalized


def classify_item(item: Dict[str, Any], topics_config: Dict[str, Any]) -> List[str]:
    # Keyword classification keeps the v1 pipeline deterministic and offline-friendly.
    classify_rules = load_classify_prompt()
    allowed_topics = set(classify_rules["allowed_topics"])
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("summary", "")),
        ]
    ).lower()
    matches: List[str] = []
    min_keyword_matches = int(topics_config.get("min_keyword_matches", classify_rules["min_keyword_matches"]))
    for topic in topics_config.get("topics", []):
        name = topic.get("name", "")
        keywords = topic.get("keywords", [])
        if not name or name not in allowed_topics:
            continue
        match_count = sum(1 for keyword in keywords if keyword.lower() in haystack)
        if match_count >= min_keyword_matches:
            matches.append(name)
    return matches


def load_classify_prompt() -> Dict[str, Any]:
    try:
        prompt = CLASSIFY_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return {"allowed_topics": [], "min_keyword_matches": 1}

    allowed_topics = [
        line[2:].strip()
        for line in prompt.splitlines()
        if line.startswith("- ") and "Rules:" not in line
    ]
    min_keyword_matches = 2 if "Prefer high precision over high recall." in prompt else 1
    return {
        "allowed_topics": allowed_topics,
        "min_keyword_matches": min_keyword_matches,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def normalize_datetime(value: Any) -> str:
    if value is None or value == "":
        return datetime.now(timezone.utc).isoformat()

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()

    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(float(text), tz=timezone.utc).isoformat()

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except Exception:
        pass

    known_formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in known_formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except Exception:
            continue

    return datetime.now(timezone.utc).isoformat()


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        query_pairs = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            # Strip common tracking parameters so URL-based deduplication is more effective.
            if not key.lower().startswith("utm_") and key.lower() not in {"ref", "source"}
        ]
        cleaned = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            query=urlencode(query_pairs),
            fragment="",
        )
        return urlunparse(cleaned)
    except Exception:
        return url.strip()
