from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT_DIR / "prompts" / "summarize.md"
COMPARE_PROMPT_PATH = ROOT_DIR / "prompts" / "compare.md"
REPORT_ANALYSIS_PROMPT_PATH = ROOT_DIR / "prompts" / "report_sections.md"
OPENAI_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
REPORT_ITEM_LIMIT = 6
REPORT_SCORE_THRESHOLD = 50
REPORT_PERCENTILE_CUTOFF = 0.75
REPORT_MIN_ITEMS_BEFORE_PERCENTILE = 12
REPORT_TOPIC_MAX_ITEMS = 2
TOPIC_PRIORITY = [
    "AI Model",
    "AI Agent",
    "Security",
    "Threat Modeling",
]
SUMMARY_PROVIDER_LABELS = {
    "openai": "OpenAI API",
    "codex_cli": "Codex CLI",
    "unavailable": "LLM Unavailable",
}


def _load_environment() -> None:
    if load_dotenv is not None:
        load_dotenv(ROOT_DIR / ".env")


def enrich_summaries(items: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    _load_environment()
    item_list = list(items)
    enriched: List[Dict[str, object]] = []
    total_items = len(item_list)
    for index, item in enumerate(item_list, start=1):
        updated = dict(item)
        source_summary = str(item.get("summary", "")).strip()
        if source_summary:
            updated["source_summary"] = source_summary

        generated_summary, provider, provider_detail, attempts = _generate_summary(
            updated,
            item_index=index,
            item_total=total_items,
        )
        updated["summary"] = generated_summary
        updated["summary_provider"] = provider
        updated["summary_provider_detail"] = provider_detail
        updated["openai_attempt_detail"] = attempts["openai"]
        updated["codex_cli_attempt_detail"] = attempts["codex_cli"]
        enriched.append(updated)
    return enriched


def enrich_report_candidates(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    _load_environment()
    selected_items = _select_report_items(items)
    if not selected_items:
        return [dict(item) for item in items]

    print(
        f"Enriching summaries for {len(selected_items)} report candidates "
        f"out of {len(items)} ranked items..."
    )
    enriched_selected = enrich_summaries(selected_items)
    enriched_by_key = {
        _normalize_key(str(item.get("title", "")) or str(item.get("url", ""))): item
        for item in enriched_selected
    }

    merged_items: List[Dict[str, object]] = []
    for item in items:
        item_key = _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        if item_key and item_key in enriched_by_key:
            merged_items.append(enriched_by_key[item_key])
        else:
            merged_items.append(dict(item))
    return merged_items


def build_report_markdown(items: List[Dict[str, object]]) -> str:
    selected_items = _select_report_items(items)
    grouped = _group_by_primary_topic(selected_items)
    related_by_topic = _group_related_items_by_topic(items, selected_items, grouped)
    report_sections, report_analysis = _generate_report_sections(
        selected_items,
        grouped,
    )
    debug_lines = _build_debug_lines(selected_items, report_analysis)

    lines: List[str] = ["# AI Trend Report", ""]
    lines.extend(["", "## 요약 생성 방식"])
    lines.extend(_build_summary_provider_lines(selected_items))
    if report_analysis.get("provider") == "unavailable":
        lines.append("- 리포트 분석 생성: LLM Unavailable")

    lines.extend(["", "## 오늘의 핵심 3가지"])
    if report_sections["top_takeaways"]:
        for takeaway in report_sections["top_takeaways"]:
            lines.append(f"- **{takeaway}**")
    else:
        lines.append("- LLM이 핵심 요약을 생성하지 못했습니다.")

    lines.extend(["", "## 핵심 요약"])
    key_insights = report_sections["key_insights"]
    for insight in key_insights:
        lines.append(f"- {insight}")
    if not key_insights:
        lines.append("- LLM이 핵심 요약 섹션을 생성하지 못했습니다.")

    lines.extend(["", "## 실무 적용 포인트"])
    if report_sections["action_points"]:
        for action_point in report_sections["action_points"]:
            lines.append(f"- {action_point}")
    else:
        lines.append("- LLM이 실무 적용 포인트를 생성하지 못했습니다.")

    lines.extend(["", "## 트렌드 분류"])
    display_topics = TOPIC_PRIORITY + [topic for topic in grouped if topic not in TOPIC_PRIORITY]
    for topic in display_topics:
        lines.extend(["", f"### {topic}"])
        topic_items = grouped.get(topic, [])
        related_items = related_by_topic.get(topic, [])
        if not topic_items and not related_items:
            lines.append("- 이번 상위 항목에는 포함되지 않았습니다.")
            continue
        for item in topic_items:
            badge = _importance_badge(item)
            lines.append(
                f"- {badge} [{item.get('title')}]({item.get('url')}) - {_report_topic_line(item)}"
            )
        if related_items:
            lines.append("- 관련 항목:")
            for item in related_items:
                lines.append(
                    f"- [{item.get('title')}]({item.get('url')}) - "
                    f"{item.get('source', 'Unknown')} · 총점 {int(item.get('score', 0))}"
                )

    lines.extend(["", "## 비교"])
    if report_sections["comparisons"]:
        for comparison in report_sections["comparisons"]:
            lines.append(f"- {comparison}")
    else:
        lines.append("- LLM이 비교 섹션을 생성하지 못했습니다.")

    lines.extend(["", "## 의미 분석"])
    if report_sections["implications"]:
        for implication in report_sections["implications"]:
            lines.append(f"- {implication}")
    else:
        lines.append("- LLM이 의미 분석 섹션을 생성하지 못했습니다.")

    lines.extend(["", "## 점수 현황"])
    lines.extend(_build_score_lines(items, selected_items))

    notable_excluded_lines = _build_notable_excluded_lines(items, selected_items)
    if notable_excluded_lines:
        lines.extend(["", "## 주목할 만한 제외 항목"])
        lines.extend(notable_excluded_lines)

    lines.extend(["", "## 링크"])
    for item in selected_items:
        lines.append(f"- [{item.get('title')}]({item.get('url')})")

    if debug_lines:
        lines.extend(["", "## 디버깅 정보"])
        lines.append("<details>")
        lines.append("<summary>디버깅 정보 펼치기</summary>")
        lines.append("")
        lines.extend(debug_lines)
        lines.append("")
        lines.append("</details>")

    lines.extend(["", f"_Generated at {datetime.now().isoformat()}._", ""])
    return "\n".join(lines)


def report_filename(now: datetime) -> str:
    return f"{now:%Y-%m-%d}.md"


def write_report(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def _group_by_topic(items: Iterable[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for item in items:
        tags = list(item.get("topic_tags", []))
        if not tags:
            grouped["Uncategorized"].append(item)
            continue
        for tag in tags:
            grouped[str(tag)].append(item)
    return dict(grouped)


def _select_report_items(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    unique_by_title: Dict[str, Dict[str, object]] = {}
    for item in items:
        key = _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        if key and key not in unique_by_title:
            unique_by_title[key] = item

    percentile_threshold = _score_percentile_threshold(list(unique_by_title.values()))
    threshold = max(REPORT_SCORE_THRESHOLD, percentile_threshold)
    filtered_items: List[Dict[str, object]] = []
    for item in unique_by_title.values():
        score = int(item.get("score", 0))
        if score >= threshold:
            filtered_items.append(item)

    if not filtered_items:
        threshold = REPORT_SCORE_THRESHOLD
        filtered_items = [
            item for item in unique_by_title.values() if int(item.get("score", 0)) >= threshold
        ]

    sorted_items = sorted(
        filtered_items,
        key=lambda item: (
            int(item.get("score", 0)),
            int(item.get("practicality_score", 0)),
            int(item.get("novelty_score", 0)),
            int(item.get("cross_source_score", 0)),
        ),
        reverse=True,
    )
    selected: List[Dict[str, object]] = []
    selected_keys: set[str] = set()
    topic_counts: Dict[str, int] = defaultdict(int)

    for topic in TOPIC_PRIORITY:
        topic_candidate = next(
            (
                item
                for item in sorted_items
                if _select_primary_topic(item) == topic
                and _normalize_key(str(item.get("title", "")) or str(item.get("url", ""))) not in selected_keys
            ),
            None,
        )
        if topic_candidate is None:
            continue
        selected.append(topic_candidate)
        selected_keys.add(
            _normalize_key(str(topic_candidate.get("title", "")) or str(topic_candidate.get("url", "")))
        )
        topic_counts[topic] += 1
        if len(selected) >= REPORT_ITEM_LIMIT:
            return selected

    for item in sorted_items:
        item_key = _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        if item_key in selected_keys:
            continue
        topic = _select_primary_topic(item)
        if topic_counts[topic] >= REPORT_TOPIC_MAX_ITEMS:
            continue
        selected.append(item)
        selected_keys.add(item_key)
        topic_counts[topic] += 1
        if len(selected) >= REPORT_ITEM_LIMIT:
            break

    if len(selected) < REPORT_ITEM_LIMIT:
        for item in sorted_items:
            item_key = _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
            if item_key in selected_keys:
                continue
            selected.append(item)
            selected_keys.add(item_key)
            if len(selected) >= REPORT_ITEM_LIMIT:
                break

    return selected


def _score_percentile_threshold(items: List[Dict[str, object]]) -> int:
    if len(items) < REPORT_MIN_ITEMS_BEFORE_PERCENTILE:
        return REPORT_SCORE_THRESHOLD

    scores = sorted(int(item.get("score", 0)) for item in items)
    if not scores:
        return REPORT_SCORE_THRESHOLD

    index = int((len(scores) - 1) * REPORT_PERCENTILE_CUTOFF)
    return scores[index]


def _group_by_primary_topic(items: Iterable[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for item in items:
        primary_topic = _select_primary_topic(item)
        grouped[primary_topic].append(item)

    ordered: Dict[str, List[Dict[str, object]]] = {}
    for topic in TOPIC_PRIORITY:
        if topic in grouped:
            ordered[topic] = grouped[topic]
    for topic, topic_items in grouped.items():
        if topic not in ordered:
            ordered[topic] = topic_items
    return ordered


def _group_related_items_by_topic(
    items: Iterable[Dict[str, object]],
    selected_items: Iterable[Dict[str, object]],
    primary_grouped: Dict[str, List[Dict[str, object]]],
) -> Dict[str, List[Dict[str, object]]]:
    primary_keys_by_topic = {
        topic: {
            _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
            for item in topic_items
        }
        for topic, topic_items in primary_grouped.items()
    }
    selected_keys = {
        _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        for item in selected_items
    }
    related: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for item in items:
        item_key = _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        for tag in [str(tag) for tag in item.get("topic_tags", [])]:
            if item_key in primary_keys_by_topic.get(tag, set()):
                continue
            if item_key in selected_keys and tag not in primary_keys_by_topic:
                continue
            related[tag].append(item)
    return {topic: topic_items[:4] for topic, topic_items in related.items()}


def _select_primary_topic(item: Dict[str, object]) -> str:
    tags = [str(tag) for tag in item.get("topic_tags", [])]
    if not tags:
        return "Uncategorized"
    title_summary = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if "AI Agent" in tags and any(
        keyword in title_summary
        for keyword in [
            "agent",
            "agents",
            "mcp",
            "codex",
            "claude code",
            "tool call",
            "automation",
            "에이전트",
            "자동화",
            "도구",
            "워크플로",
        ]
    ):
        return "AI Agent"
    if "AI Model" in tags and any(
        keyword in title_summary
        for keyword in ["model", "llm", "inference", "vllm", "gpu", "token", "qwen", "deepseek", "quantization"]
    ):
        return "AI Model"
    for topic in TOPIC_PRIORITY:
        if topic in tags:
            return topic
    return tags[0]


def _generate_summary(
    item: Dict[str, object],
    item_index: int | None = None,
    item_total: int | None = None,
) -> Tuple[str, str, str, Dict[str, str]]:
    api_summary, api_detail = _summarize_with_openai(item)
    if api_summary:
        return api_summary, "openai", api_detail, {
            "openai": api_detail,
            "codex_cli": "Skipped because OpenAI API succeeded",
        }

    codex_summary, codex_detail = _summarize_with_codex_cli(
        item,
        item_index=item_index,
        item_total=item_total,
    )
    if codex_summary:
        return codex_summary, "codex_cli", codex_detail, {
            "openai": api_detail,
            "codex_cli": codex_detail,
        }

    unavailable_detail = f"LLM unavailable after {api_detail}; {codex_detail}"
    return "", "unavailable", unavailable_detail, {
        "openai": api_detail,
        "codex_cli": codex_detail,
    }


def _generate_report_sections(
    items: List[Dict[str, object]],
    grouped: Dict[str, List[Dict[str, object]]],
) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    if not items:
        return _empty_report_sections(), {
            "provider": "unavailable",
            "detail": "No selected items for LLM report analysis",
            "openai": "Skipped because no selected items were available",
            "codex_cli": "Skipped because no selected items were available",
        }

    openai_sections, openai_detail = _analyze_report_with_openai(items, grouped)
    if openai_sections:
        return openai_sections, {
            "provider": "openai",
            "detail": openai_detail,
            "openai": openai_detail,
            "codex_cli": "Skipped because OpenAI API succeeded",
        }

    codex_sections, codex_detail = _analyze_report_with_codex_cli(items, grouped)
    if codex_sections:
        return codex_sections, {
            "provider": "codex_cli",
            "detail": codex_detail,
            "openai": openai_detail,
            "codex_cli": codex_detail,
        }

    return _empty_report_sections(), {
        "provider": "unavailable",
        "detail": f"LLM report analysis unavailable after {openai_detail}; {codex_detail}",
        "openai": openai_detail,
        "codex_cli": codex_detail,
    }


def _analyze_report_with_openai(
    items: List[Dict[str, object]],
    grouped: Dict[str, List[Dict[str, object]]],
) -> Tuple[Dict[str, List[str]], str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}, "OPENAI_API_KEY missing"

    prompt = _load_report_analysis_prompt()
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    payload = {
        "model": model,
        "instructions": prompt,
        "input": _build_report_analysis_input(items, grouped),
        "max_output_tokens": 900,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    request = Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return {}, _format_openai_http_error(exc)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {}, f"OpenAI report analysis failed: {type(exc).__name__}: {_compact_text(str(exc), 140)}"

    output_text = _extract_output_text(response_payload).strip()
    if not output_text:
        return {}, f"OpenAI report analysis returned empty output with model {model}"

    parsed = _parse_report_sections_output(output_text)
    if not parsed:
        return {}, f"OpenAI report analysis returned invalid JSON with model {model}"
    return parsed, f"OpenAI model {model}"


def _analyze_report_with_codex_cli(
    items: List[Dict[str, object]],
    grouped: Dict[str, List[Dict[str, object]]],
) -> Tuple[Dict[str, List[str]], str]:
    codex_model = os.getenv("CODEX_MODEL", "").strip()
    codex_command, resolution_detail = _resolve_codex_command()
    if not codex_command:
        return {}, resolution_detail

    command = [
        codex_command,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--ephemeral",
    ]
    if codex_model:
        command.extend(["--model", codex_model])

    output_path = None
    try:
        output_dir = Path(tempfile.gettempdir())
        output_path = output_dir / next(tempfile._get_candidate_names())
        output_path = output_path.with_name(f"{output_path.name}-codex-report.txt")
        prompt = _build_codex_report_prompt(items, grouped)
        command.extend(["--output-last-message", str(output_path)])
        _print_codex_progress(
            f"[Codex][report] Starting report analysis with {len(items)} selected items",
            command,
        )
        completed = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_build_codex_subprocess_env(),
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _cleanup_temp_file(output_path)
        return {}, f"Codex CLI unavailable: {type(exc).__name__}: {resolution_detail}"

    stdout_text = completed.stdout.strip()
    stderr_text = completed.stderr.strip()
    codex_output = ""
    if output_path is not None and output_path.exists():
        try:
            codex_output = output_path.read_text(encoding="utf-8").strip()
        except OSError:
            codex_output = ""
    _print_codex_result(
        "[Codex][report] Completed report analysis",
        completed.returncode,
        stdout_text,
        stderr_text,
        codex_output,
    )
    _cleanup_temp_file(output_path)

    if completed.returncode != 0:
        detail = _extract_codex_failure_detail(completed.returncode, stdout_text, stderr_text)
        return {}, f"{detail} | {resolution_detail}"
    if not codex_output:
        return {}, f"Codex CLI report analysis returned empty output | {resolution_detail}"
    if _is_codex_clarification_request(codex_output):
        return {}, f"Codex CLI requested more input instead of returning report sections | {resolution_detail}"

    parsed = _parse_report_sections_output(codex_output)
    if not parsed:
        return {}, f"Codex CLI report analysis returned invalid JSON | {resolution_detail}"

    detail = f"Codex CLI via {codex_command}"
    if codex_model:
        detail = f"Codex CLI model {codex_model} via {codex_command}"
    return parsed, detail


def _empty_report_sections() -> Dict[str, List[str]]:
    return {
        "top_takeaways": [],
        "key_insights": [],
        "action_points": [],
        "comparisons": [],
        "implications": [],
    }


def _summarize_with_openai(item: Dict[str, object]) -> Tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return "", "OPENAI_API_KEY missing"

    prompt = _load_summary_prompt()
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    payload = {
        "model": model,
        "instructions": prompt,
        "input": _build_summary_input(item),
        "max_output_tokens": 120,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    request = Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return "", _format_openai_http_error(exc)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return "", f"OpenAI request failed: {type(exc).__name__}: {_compact_text(str(exc), 140)}"

    output_text = _extract_output_text(response_payload).strip()
    if not output_text:
        return "", f"OpenAI response empty with model {model}"
    return output_text, f"OpenAI model {model}"


def _summarize_with_codex_cli(
    item: Dict[str, object],
    item_index: int | None = None,
    item_total: int | None = None,
) -> Tuple[str, str]:
    prompt = _build_codex_prompt(item)
    codex_model = os.getenv("CODEX_MODEL", "").strip()
    codex_command, resolution_detail = _resolve_codex_command()
    if not codex_command:
        return "", resolution_detail

    command = [
        codex_command,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--ephemeral",
    ]
    if codex_model:
        command.extend(["--model", codex_model])

    output_path = None
    try:
        output_dir = Path(tempfile.gettempdir())
        output_path = output_dir / next(tempfile._get_candidate_names())
        output_path = output_path.with_name(f"{output_path.name}-codex-summary.txt")

        command.extend(["--output-last-message", str(output_path)])
        progress_label = _build_codex_summary_progress_label(item, item_index, item_total)
        _print_codex_progress(progress_label, command)
        completed = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_build_codex_subprocess_env(),
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _cleanup_temp_file(output_path)
        return "", f"Codex CLI unavailable: {type(exc).__name__}: {resolution_detail}"

    stdout_text = completed.stdout.strip()
    stderr_text = completed.stderr.strip()
    codex_output = ""
    if output_path is not None and output_path.exists():
        try:
            codex_output = output_path.read_text(encoding="utf-8").strip()
        except OSError:
            codex_output = ""
    _print_codex_result(
        _build_codex_summary_completion_label(item, item_index, item_total),
        completed.returncode,
        stdout_text,
        stderr_text,
        codex_output,
    )
    _cleanup_temp_file(output_path)

    if completed.returncode != 0:
        detail = _extract_codex_failure_detail(completed.returncode, stdout_text, stderr_text)
        return "", f"{detail} | {resolution_detail}"
    if not codex_output:
        return "", f"Codex CLI returned empty output | {resolution_detail}"
    if _is_codex_clarification_request(codex_output):
        return "", f"Codex CLI requested more input instead of summarizing | {resolution_detail}"
    quality_issue = _codex_summary_quality_issue(codex_output)
    if quality_issue:
        return "", f"Codex CLI returned unusable summary: {quality_issue} | {resolution_detail}"

    detail = f"Codex CLI via {codex_command}"
    if codex_model:
        detail = f"Codex CLI model {codex_model} via {codex_command}"
    return codex_output, detail


def _cleanup_temp_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _build_codex_subprocess_env() -> Dict[str, str]:
    env = os.environ.copy()
    codex_home = _select_codex_home_for_subprocess(env)

    for path in [
        codex_home,
        codex_home / "sessions",
        codex_home / "skills",
        codex_home / "tmp",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    env["CODEX_HOME"] = str(codex_home)

    for proxy_name in [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]:
        env.pop(proxy_name, None)

    return env


def _select_codex_home_for_subprocess(env: Dict[str, str]) -> Path:
    configured_home = env.get("CODEX_HOME", "").strip()
    if configured_home:
        return Path(configured_home)

    default_home = Path.home() / ".codex"
    if _can_write_codex_home(default_home):
        return default_home

    return ROOT_DIR / ".codex-runtime"


def _can_write_codex_home(path: Path) -> bool:
    sessions_dir = path / "sessions"
    try:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        test_path = sessions_dir / ".pipeline-write-test"
        test_path.write_text("test", encoding="utf-8")
        test_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _build_codex_summary_progress_label(
    item: Dict[str, object],
    item_index: int | None,
    item_total: int | None,
) -> str:
    title = _compact_text(str(item.get("title", "")).strip(), 80)
    if item_index is not None and item_total is not None:
        return f"[Codex][summary {item_index}/{item_total}] Starting: {title}"
    return f"[Codex][summary] Starting: {title}"


def _build_codex_summary_completion_label(
    item: Dict[str, object],
    item_index: int | None,
    item_total: int | None,
) -> str:
    title = _compact_text(str(item.get("title", "")).strip(), 80)
    if item_index is not None and item_total is not None:
        return f"[Codex][summary {item_index}/{item_total}] Completed: {title}"
    return f"[Codex][summary] Completed: {title}"


def _print_codex_progress(label: str, command: List[str]) -> None:
    print(label)
    printable_parts = [_compact_text(part, 160) for part in command]
    print(f"[Codex][command] {' '.join(printable_parts)}")


def _print_codex_result(
    label: str,
    returncode: int,
    stdout_text: str,
    stderr_text: str,
    codex_output: str,
) -> None:
    print(f"{label} (returncode={returncode})")
    print("[Codex][stdout]")
    print(stdout_text if stdout_text else "(empty)")
    print("[Codex][stderr]")
    print(_summarize_codex_stderr(stderr_text, returncode) if stderr_text else "(empty)")
    print("[Codex][last-message]")
    print(codex_output if codex_output else "(empty)")


def _summarize_codex_stderr(stderr_text: str, returncode: int) -> str:
    lines = [line.strip() for line in stderr_text.splitlines() if line.strip()]
    if not lines:
        return "(empty)"

    if returncode != 0:
        return _compact_text(_extract_codex_failure_detail(returncode, "", stderr_text), 400)

    warning_count = sum(1 for line in lines if "WARN" in line or "WARNING" in line)
    error_count = sum(1 for line in lines if "ERROR" in line)
    important = [
        line
        for line in lines
        if "failed" in line.lower()
        or "forbidden" in line.lower()
        or "warning" in line.lower()
        or "warn" in line.lower()
        or "error" in line.lower()
    ]
    preview = _compact_text(important[0] if important else lines[0], 220)
    return f"{len(lines)} stderr lines summarized; warnings={warning_count}, errors={error_count}; first={preview}"


def _detect_runtime() -> str:
    system_name = platform.system().lower()
    if system_name == "windows":
        return "windows"
    if system_name == "linux":
        release = platform.release().lower()
        if "microsoft" in release or os.getenv("WSL_DISTRO_NAME"):
            return "wsl"
        return "linux"
    return system_name or "unknown"


def _resolve_codex_command() -> Tuple[str, str]:
    runtime = _detect_runtime()
    configured_path = os.getenv("CODEX_CLI_PATH", "").strip()
    candidates: List[str] = []
    if configured_path:
        candidates.append(configured_path)

    if runtime == "windows":
        # Prefer a native executable on Windows before the npm wrapper because
        # the wrapper has been more prone to session-path permission failures.
        candidates.extend(_windows_native_codex_candidates())
        candidates.extend(["codex.exe", "codex.cmd", "codex"])
    else:
        candidates.append("codex")

    resolution_attempts: List[str] = []
    seen_candidates = set()
    for candidate in candidates:
        if candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)
        resolved = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        resolution_attempts.append(f"{candidate}->{resolved or 'not-found'}")
        if resolved:
            return resolved, f"runtime={runtime} resolved={resolved}"

    tried = ", ".join(resolution_attempts)
    return "", f"Codex CLI unavailable: runtime={runtime} FileNotFoundError while resolving executable. tried={tried}"


def _windows_native_codex_candidates() -> List[str]:
    user_profile = os.getenv("USERPROFILE", "").strip()
    if not user_profile:
        return []

    extension_roots = [
        Path(user_profile) / ".cursor" / "extensions",
        Path(user_profile) / ".vscode" / "extensions",
    ]
    candidates: List[Path] = []
    for root in extension_roots:
        if not root.exists():
            continue
        candidates.extend(root.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"))

    existing_candidates = [path for path in candidates if path.is_file()]
    existing_candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path) for path in existing_candidates]


def _format_openai_http_error(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        body = ""
    compact_body = _compact_text(body, 180)
    if compact_body:
        return f"OpenAI request failed: HTTP {exc.code}: {compact_body}"
    return f"OpenAI request failed: HTTP {exc.code}"


def _extract_codex_failure_detail(returncode: int, stdout_text: str, stderr_text: str) -> str:
    combined_lines = []
    for source_text in [stderr_text, stdout_text]:
        for raw_line in source_text.splitlines():
            line = " ".join(raw_line.split())
            if line:
                combined_lines.append(line)

    priority_patterns = [
        "Error:",
        "thread/start failed",
        "Failed to create session",
        "permission denied",
        "액세스가 거부되었습니다",
        "Failed to create shell snapshot",
        "error sending request",
    ]
    for pattern in priority_patterns:
        for line in combined_lines:
            if pattern.lower() in line.lower():
                return f"Codex CLI failed: {_compact_text(line, 220)}"

    for line in combined_lines:
        if "WARN" not in line:
            return f"Codex CLI failed: {_compact_text(line, 220)}"

    return f"Codex CLI failed with exit code {returncode}"


def _compact_text(text: str, limit: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _load_summary_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "Summarize the item in 1 to 2 sentences. Focus on what happened and why it matters."


def _load_compare_prompt() -> str:
    try:
        return COMPARE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "Compare trends across sources.\n"
            "Focus on differences in perspective and underlying direction.\n"
            "Output: difference, conclusion, implication."
        )


def _load_report_analysis_prompt() -> str:
    try:
        return REPORT_ANALYSIS_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "You are preparing an AI trend report.\n"
            "Return valid JSON with keys top_takeaways, key_insights, action_points, comparisons, implications.\n"
            "Each value must be an array of concise Korean strings.\n"
            "top_takeaways must contain exactly 3 items. Other arrays should contain up to 3 items.\n"
            "Do not use markdown."
        )


def _build_summary_input(item: Dict[str, object]) -> str:
    topic_tags = ", ".join(str(tag) for tag in item.get("topic_tags", []))
    source_summary = str(item.get("source_summary", "")).strip()
    fields = [
        f"title: {str(item.get('title', '')).strip()}",
        f"source: {str(item.get('source', '')).strip()}",
        f"url: {str(item.get('url', '')).strip()}",
        f"created_at: {str(item.get('created_at', '')).strip()}",
        f"topic_tags: {topic_tags}",
    ]
    if source_summary:
        fields.append(f"source_summary: {source_summary}")
    return "\n".join(fields)


def _build_codex_prompt(item: Dict[str, object]) -> str:
    return (
        "You are generating a Korean summary for an automated trend report.\n"
        "This is a closed-input task: use only the fields below and never ask for more information.\n"
        "Do not mention missing article text, missing context, incomplete links, or limitations.\n"
        "If information is limited, infer cautiously from title, source, topic tags, and source summary.\n\n"
        "Output contract:\n"
        "- Return exactly one Korean paragraph.\n"
        "- Use 1 to 2 sentences only.\n"
        "- Do not use markdown, bullets, headings, labels, quotes, source footers, or follow-up offers.\n"
        "- Do not include phrases such as '원하면', '원하시면', '붙여주시면', or '보내주시면'.\n\n"
        "Use the first sentence for what happened and the second sentence for the operational impact.\n"
        "State what happened and why it matters. Be concrete and concise.\n"
        "Avoid repeating the same Korean endings across items, especially '보여준다', '의미가 있다', and '중요하다'.\n\n"
        "Trend item fields:\n"
        f"{_build_summary_input(item)}"
    )


def _build_report_analysis_input(
    items: List[Dict[str, object]],
    grouped: Dict[str, List[Dict[str, object]]],
) -> str:
    payload = {
        "selected_items": [
            {
                "title": str(item.get("title", "")),
                "source": str(item.get("source", "")),
                "summary": str(item.get("summary", "")),
                "score": int(item.get("score", 0)),
                "topic_tags": list(item.get("topic_tags", [])),
                "practicality_score": int(item.get("practicality_score", 0)),
                "novelty_score": int(item.get("novelty_score", 0)),
                "cross_source_score": int(item.get("cross_source_score", 0)),
            }
            for item in items
        ],
        "grouped_topics": {
            topic: [str(item.get("title", "")) for item in topic_items]
            for topic, topic_items in grouped.items()
        },
        "report_requirements": {
            "language": "Korean",
            "top_takeaways_count": 3,
            "max_other_items_per_section": 3,
            "style": [
                "grounded",
                "specific",
                "avoid hype",
                "separate observations from implications",
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_codex_report_prompt(
    items: List[Dict[str, object]],
    grouped: Dict[str, List[Dict[str, object]]],
) -> str:
    return (
        f"{_load_report_analysis_prompt()}\n\n"
        "This is a closed-input task. Use only the JSON below and never ask for more data.\n"
        "Return only the final JSON object. Do not include explanation, markdown, or follow-up offers.\n\n"
        "Input JSON:\n"
        f"{_build_report_analysis_input(items, grouped)}"
    )


def _is_codex_clarification_request(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    clarification_patterns = [
        "please send",
        "send the link",
        "send the article",
        "send the body",
        "provide the link",
        "provide the article",
        "provide the full text",
        "need more information",
        "more information",
        "요약할 트렌드 항목",
        "본문이나 링크를 보내",
        "본문 또는 링크를 보내",
        "링크를 보내",
        "보내주세요",
        "받으면 한국어로",
        "간단히 정리하겠습니다",
        "원하면",
        "원하시면",
        "붙여주시면",
        "보내주시면",
        "톤도 맞출 수",
        "다음 단계로",
        "바로 맞춰 드리겠습니다",
    ]
    return any(pattern in normalized for pattern in clarification_patterns)


def _codex_summary_quality_issue(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "empty output"

    if "```" in stripped:
        return "code fence included"

    normalized = " ".join(stripped.lower().split())
    banned_phrases = [
        "원하면",
        "원하시면",
        "붙여주시면",
        "보내주시면",
        "톤도 맞출 수",
        "다음 단계로",
        "바로 정리하겠습니다",
        "바로 맞춰 드리겠습니다",
        "항목별 1~2문장 요약도",
        "보고서 문체",
        "임원용 3줄 요약",
        "markdown 섹션용 문안",
    ]
    for phrase in banned_phrases:
        if phrase in normalized:
            return f"follow-up offer detected ({phrase})"

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) > 2:
        return "too many non-empty lines"

    markdown_prefixes = ("- ", "* ", "1. ", "2. ", "3. ", "#", "##", "###")
    if any(line.startswith(markdown_prefixes) for line in lines):
        return "markdown-style formatting detected"

    if "출처:" in stripped:
        return "source footer included"

    if len(stripped) > 320:
        return "summary too long"

    sentence_breaks = len(re.findall(r"[.!?](?:\s|$)", stripped))
    if sentence_breaks > 4:
        return "too many sentences"

    return ""


def _parse_report_sections_output(raw_text: str) -> Dict[str, List[str]]:
    candidate_texts = [raw_text.strip()]
    fenced_match = raw_text.strip()
    if fenced_match.startswith("```"):
        stripped = raw_text.strip().strip("`")
        candidate_texts.append(stripped)

    json_start = raw_text.find("{")
    json_end = raw_text.rfind("}")
    if json_start != -1 and json_end != -1 and json_end > json_start:
        candidate_texts.append(raw_text[json_start : json_end + 1].strip())

    for candidate in candidate_texts:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        normalized = _normalize_report_sections(parsed)
        if normalized:
            return normalized
    return {}


def _normalize_report_sections(payload: Any) -> Dict[str, List[str]]:
    if not isinstance(payload, dict):
        return {}

    normalized: Dict[str, List[str]] = {}
    for key in ["top_takeaways", "key_insights", "action_points", "comparisons", "implications"]:
        raw_value = payload.get(key, [])
        if not isinstance(raw_value, list):
            return {}
        cleaned = [_clean_report_line(value) for value in raw_value]
        cleaned = [value for value in cleaned if value]
        normalized[key] = cleaned

    if len(normalized["top_takeaways"]) != 3:
        return {}
    return normalized


def _clean_report_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _extract_output_text(response_payload: Dict[str, object]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    for output_item in response_payload.get("output", []):
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                return text

    return ""


def _normalize_key(value: str) -> str:
    return " ".join(value.lower().split())


def _build_summary_provider_lines(items: List[Dict[str, object]]) -> List[str]:
    if not items:
        return ["- 상위 리포트 항목이 없어 요약 생성 방식 집계를 표시할 수 없습니다."]

    provider_counts: Dict[str, int] = defaultdict(int)
    lines: List[str] = []
    for item in items:
        provider = str(item.get("summary_provider", "unavailable"))
        provider_counts[provider] += 1

    for provider_name in ["openai", "codex_cli", "unavailable"]:
        count = provider_counts.get(provider_name, 0)
        lines.append(f"- {SUMMARY_PROVIDER_LABELS[provider_name]}: {count}개")

    return lines


def _build_score_lines(
    ranked_items: List[Dict[str, object]],
    selected_items: List[Dict[str, object]],
) -> List[str]:
    selected_keys = {
        _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        for item in selected_items
    }

    percentile_threshold = _score_percentile_threshold(ranked_items)
    effective_threshold = max(REPORT_SCORE_THRESHOLD, percentile_threshold)

    lines = [
        f"- 리포트 포함 기준: score >= {effective_threshold}, 최대 {REPORT_ITEM_LIMIT}개",
        f"- 동적 기준: 기본 하한 {REPORT_SCORE_THRESHOLD}점과 당일 후보 상위 {int(REPORT_PERCENTILE_CUTOFF * 100)}퍼센타일 점수 {percentile_threshold}점 중 더 높은 값을 사용합니다.",
        f"- 선정 방식: 기준점 이상 항목 중 토픽별 대표 후보를 먼저 포함하고, 토픽별 최대 {REPORT_TOPIC_MAX_ITEMS}개까지 총점순으로 채웁니다.",
        "- 점수 구성: 출처 가중치, 최신성, 인기도, 토픽 매칭, 실용성, 신규성, 교차출처, Discovery/Watchlist 신뢰도를 합산하고 Discovery 불확실성은 감점합니다.",
    ]
    included_items: List[Dict[str, object]] = []
    excluded_items: List[Dict[str, object]] = []
    for item in ranked_items:
        title = str(item.get("title", "")).strip()
        item_key = _normalize_key(title or str(item.get("url", "")))
        if item_key in selected_keys:
            included_items.append(item)
        else:
            excluded_items.append(item)

    visible_items = included_items + excluded_items[:8]
    for item in visible_items:
        title = str(item.get("title", "")).strip()
        item_key = _normalize_key(title or str(item.get("url", "")))
        included = "포함" if item_key in selected_keys else "제외"
        lines.append(
            "- "
            f"[{included}] {title} | "
            f"총점={int(item.get('score', 0))}, "
            f"실용성={int(item.get('practicality_score', 0))}, "
            f"신규성={int(item.get('novelty_score', 0))}, "
            f"교차출처={int(item.get('cross_source_score', 0))}, "
            f"출처신뢰={int(item.get('source_reliability_score', 0))}, "
            f"Discovery감점={int(item.get('discovery_penalty', 0))}"
        )
    hidden_count = max(len(excluded_items) - 8, 0)
    if hidden_count:
        lines.append(f"- 제외 항목 {hidden_count}개는 점수표에서 생략했습니다. 주요 후보는 아래 '주목할 만한 제외 항목'을 확인하세요.")
    return lines


def _build_notable_excluded_lines(
    ranked_items: List[Dict[str, object]],
    selected_items: List[Dict[str, object]],
) -> List[str]:
    selected_keys = {
        _normalize_key(str(item.get("title", "")) or str(item.get("url", "")))
        for item in selected_items
    }
    candidates = [
        item
        for item in ranked_items
        if _normalize_key(str(item.get("title", "")) or str(item.get("url", ""))) not in selected_keys
        and int(item.get("score", 0)) >= REPORT_SCORE_THRESHOLD - 5
    ]
    lines: List[str] = []
    for item in candidates[:2]:
        title = str(item.get("title", "")).strip()
        score = int(item.get("score", 0))
        reason = _notable_exclusion_reason(item)
        lines.append(f"- [{title}]({item.get('url')}) - 총점 {score}점으로 기준에 근접했습니다. {reason}")
    return lines


def _notable_exclusion_reason(item: Dict[str, object]) -> str:
    tags = [str(tag) for tag in item.get("topic_tags", [])]
    if "AI Agent" in tags:
        return "도구 사용이나 권한 설계 관점에서 별도 추적할 만합니다."
    if "Security" in tags or "Threat Modeling" in tags:
        return "보안 검토 흐름과 이어져 후속 확인 가치가 있습니다."
    if "AI Model" in tags:
        return "모델 성능과 추론 인프라 흐름과 연결돼 다음 리포트에서 재등장할 수 있습니다."
    return "다음 수집 주기에서 재평가할 만합니다."


def _build_debug_lines(items: List[Dict[str, object]], report_analysis: Dict[str, str]) -> List[str]:
    if not items:
        return []

    lines: List[str] = []
    openai_failures = _filter_debug_items(items, "openai_attempt_detail", _is_failure_detail)
    codex_failures = _filter_debug_items(
        items,
        "codex_cli_attempt_detail",
        _is_failure_detail,
    )

    if not openai_failures and not codex_failures:
        if report_analysis.get("provider") != "unavailable":
            return []

    if openai_failures:
        lines.append("- OpenAI API 실패 정보:")
        for detail, count in _count_debug_details(openai_failures, "openai_attempt_detail"):
            lines.append(f"- {detail}: {count}개")

    if codex_failures:
        lines.append("- Codex CLI 실패 정보:")
        for detail, count in _count_debug_details(codex_failures, "codex_cli_attempt_detail"):
            lines.append(f"- {detail}: {count}개")

    if report_analysis.get("provider") == "unavailable":
        lines.append("- 리포트 섹션 생성 실패 정보:")
        if _is_failure_detail(report_analysis.get("openai", "")):
            lines.append(f"- OpenAI={report_analysis.get('openai', '')}")
        if _is_failure_detail(report_analysis.get("codex_cli", "")):
            lines.append(f"- Codex={report_analysis.get('codex_cli', '')}")

    lines.append("- 선택 항목별 실패 정보:")
    for item in items:
        title = str(item.get("title", "")).strip()
        openai_detail = str(item.get("openai_attempt_detail", "")).strip()
        codex_detail = str(item.get("codex_cli_attempt_detail", "")).strip()
        fragments: List[str] = []
        if _is_failure_detail(openai_detail):
            fragments.append(f"OpenAI={openai_detail}")
        if _is_failure_detail(codex_detail):
            fragments.append(f"Codex={codex_detail}")
        if fragments:
            lines.append(f"- {title}: {' | '.join(fragments)}")

    return lines


def _count_debug_details(items: List[Dict[str, object]], field_name: str) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = defaultdict(int)
    for item in items:
        detail = str(item.get(field_name, "")).strip() or "No data"
        counts[detail] += 1
    return sorted(counts.items(), key=lambda entry: (-entry[1], entry[0]))


def _filter_debug_items(
    items: List[Dict[str, object]],
    field_name: str,
    predicate,
) -> List[Dict[str, object]]:
    selected: List[Dict[str, object]] = []
    for item in items:
        detail = str(item.get(field_name, "")).strip()
        if detail and predicate(detail):
            selected.append(item)
    return selected


def _is_failure_detail(detail: str) -> bool:
    normalized = detail.lower()
    failure_keywords = [
        "failed",
        "missing",
        "unavailable",
        "error",
        "denied",
        "timeout",
        "not found",
        "http ",
        "requested more input",
        "unusable summary",
        "invalid json",
        "empty output",
    ]
    return any(keyword in normalized for keyword in failure_keywords)


def _korean_key_insight(item: Dict[str, object]) -> str:
    source = str(item.get("source", ""))
    summary = _koreanized_content(item)
    implication = _practical_implication(item)
    return f"{source}에서는 {summary} {implication}".strip()


def _korean_topic_description(item: Dict[str, object]) -> str:
    perspective = _item_perspective(item)
    source = str(item.get("source", ""))
    return f"{perspective} 출처: {source}."


def _report_topic_line(item: Dict[str, object]) -> str:
    summary = str(item.get("summary", "")).strip()
    source = str(item.get("source", "")).strip()
    if summary:
        return f"{summary} 출처: {source}."
    return f"LLM 요약을 생성하지 못했습니다. 출처: {source}."


def _koreanized_content(item: Dict[str, object]) -> str:
    summary = str(item.get("summary", "")).strip()
    title = str(item.get("title", "")).strip()
    combined = f"{title} {summary}".lower()

    pattern_summary = _pattern_based_summary(combined)
    if pattern_summary:
        return pattern_summary

    return f"'{title}' 이슈를 다뤘습니다"


def _item_perspective(item: Dict[str, object]) -> str:
    title = str(item.get("title", "")).strip()
    title_lower = title.lower()
    source = str(item.get("source", ""))
    if source == "GitHub Trending":
        if "starter" in title_lower or "orchestration" in title_lower:
            return f"구현 관점에서 '{title}'는 바로 붙여 검증할 수 있는 스타터 자산이다. 초기 시행착오를 줄이는 데 바로 쓸 수 있다."
        if "template" in title_lower:
            return f"구현 관점에서 '{title}'는 반복 검토 절차를 템플릿으로 고정하는 자산이다. 팀 단위 재사용에 곧바로 연결된다."
        return f"구현 관점에서 '{title}'는 아이디어보다 먼저 손에 잡히는 작업 단위를 준다. 바로 실험 가능한 레퍼런스다."
    if source == "Hacker News":
        if "what breaks first" in title_lower or "failure" in title_lower:
            return f"문제와 리스크 관점에서 '{title}'는 운영 환경에서 가장 먼저 터지는 실패 지점을 짚는다. 가드레일 없이 확장하면 바로 비용으로 돌아온다."
        if "checklist" in title_lower:
            return f"문제와 리스크 관점에서 '{title}'는 리뷰 절차를 자동화할수록 통제 기준을 더 세밀하게 넣어야 한다는 사실을 못 박는다."
        return f"문제와 리스크 관점에서 '{title}'는 배포 이후 운영 부담이 커지는 지점을 정확히 찌른다."
    if source == "RSS News":
        if "architecture review" in title_lower:
            return f"시장 흐름 관점에서 '{title}'는 자동화 도입 범위가 실행 보조를 넘어 설계 검토 단계로 넓어졌다는 신호다."
        if "threat modeling" in title_lower:
            return f"시장 흐름 관점에서 '{title}'는 조직들이 속도보다 보안 검증 체계를 먼저 요구한다는 사실을 드러낸다."
        return f"시장 흐름 관점에서 '{title}'는 조직 수요가 어디로 옮겨가는지 명확히 찍는다."
    if source == "Reddit":
        return f"실무 체감 관점에서 '{title}'는 현업 사용자가 실제로 막히는 지점과 운영 선택지를 그대로 끌어올린다."
    return f"'{title}'는 지금 팀의 우선순위를 다시 정렬하게 만드는 신호다."


def _practical_implication(item: Dict[str, object]) -> str:
    tags = list(item.get("topic_tags", []))
    if "Security" in tags or "Threat Modeling" in tags:
        return "실제 운영 환경에서 보안 검토 기준을 구체화하는 데 참고할 만합니다."
    if "AI Agent" in tags:
        return "도구 연결 방식과 에이전트 실행 구조를 설계할 때 바로 참고할 수 있습니다."
    if "AI Model" in tags:
        return "모델 성능과 추론 인프라 운영 방향을 가늠하는 데 도움이 됩니다."
    if "AI Agent" in tags:
        return "에이전트 기반 제품이나 워크플로 설계 방향을 가늠하는 데 유용합니다."
    return "최근 흐름을 빠르게 파악하는 데 도움이 됩니다."


def _topic_context(item: Dict[str, object]) -> str:
    tags = list(item.get("topic_tags", []))
    if not tags:
        return "관련 흐름을 보여줍니다."

    if "Security" in tags and "Threat Modeling" in tags:
        return "보안 통제 지점과 위협 가정을 함께 검토해야 하는 상황에서 특히 유용합니다."
    if "Security" in tags:
        return "아키텍처 리뷰 기준과 운영 통제 지점을 설계하는 데 직접 참고할 수 있습니다."
    if "Threat Modeling" in tags:
        return "위협 가정, 공격 경로, 검증 포인트를 정리하는 관점에서 시사점이 있습니다."
    if "AI Agent" in tags:
        return "도구 인터페이스, 권한 경계, 실행 책임을 어떻게 나눌지 설계할 때 시사점이 큽니다."
    if "AI Model" in tags:
        return "모델 평가와 추론 운영을 실제 서비스 조건에 맞춰 검토할 때 도움이 됩니다."
    return "관련 흐름을 파악하는 데 도움이 됩니다."


def _strip_sentence_ending(text: str) -> str:
    for ending in ["입니다", "합니다", "니다"]:
        if text.endswith(ending):
            return text[: -len(ending)]
    if text.endswith("."):
        return text[:-1]
    return text


def _build_key_insights(items: List[Dict[str, object]], grouped: Dict[str, List[Dict[str, object]]]) -> List[str]:
    if not items:
        return []

    insights: List[str] = []
    high_practicality = sum(1 for item in items if int(item.get("practicality_score", 0)) >= 14)
    high_novelty = sum(1 for item in items if int(item.get("novelty_score", 0)) >= 8)
    repeated_signals = sum(1 for item in items if int(item.get("cross_source_score", 0)) >= 12)
    github_count = sum(1 for item in items if str(item.get("source", "")) == "GitHub Trending")
    hn_count = sum(1 for item in items if str(item.get("source", "")) == "Hacker News")
    news_count = sum(1 for item in items if str(item.get("source", "")) == "RSS News")

    if high_practicality >= 3:
        insights.append("상위 신호 대부분이 템플릿, 스타터, 체크리스트에 몰렸습니다. 시장은 개념보다 실행 단위를 요구하고 있습니다.")
    if _count_topic_hits(items, "Security") + _count_topic_hits(items, "Threat Modeling") >= 2:
        insights.append("보안 검토와 위협 모델링이 상위권에 함께 올라왔습니다. 자동화는 이제 승인 가능한 통제 구조를 전제로 움직입니다.")
    if repeated_signals >= 1:
        insights.append("같은 의제가 여러 채널에서 반복됐습니다. 이 흐름은 일시적 화제가 아니라 구조적 수요로 굳어지고 있습니다.")
    if github_count > 0 and hn_count > 0 and news_count > 0:
        insights.append("구현 자산, 운영 리스크, 시장 수요가 같은 방향을 가리켰습니다. 올해 의사결정은 더 빠르게 수렴할 것입니다.")
    if high_novelty >= 2:
        insights.append("새로운 관심사는 성능 개선이 아니라 운영 통제 강화에 집중됐습니다. 다음 경쟁 축도 그쪽으로 고정될 것입니다.")

    return insights[:5]


def _build_top_three_takeaways(items: List[Dict[str, object]]) -> List[str]:
    takeaways: List[str] = []
    for item in items[:3]:
        takeaways.append(_condense_takeaway(item))

    while len(takeaways) < 3:
        takeaways.append("이번 사이클에서는 추가 핵심 항목이 임계값을 넘지 못했습니다.")
    return takeaways[:3]


def _build_action_points(items: List[Dict[str, object]]) -> List[str]:
    action_points: List[str] = []
    for item in items:
        point = _action_point_for_item(item)
        if point not in action_points:
            action_points.append(point)
        if len(action_points) == 3:
            break

    if not action_points:
        action_points.append("지금 바로 적용 가능한 항목이 없어 다음 수집 사이클을 기다리는 편이 낫습니다.")
    return action_points


def _condense_takeaway(item: Dict[str, object]) -> str:
    title = str(item.get("title", "")).strip()
    title_lower = title.lower()

    if "starter" in title_lower or "orchestration" in title_lower:
        return "에이전트 경쟁의 승부처는 설명이 아니라 바로 검증 가능한 구현 자산이다."
    if "architecture review" in title_lower:
        return "자동화는 실행 보조를 넘어 설계 검토 단계까지 확장된다."
    if "threat modeling" in title_lower:
        return "위협 모델링은 선택이 아니라 자동화 착수의 선행 조건이다."
    if "checklist" in title_lower:
        return "리뷰 체크리스트까지 자동화 범위에 들어오면서 운영 절차가 표준화된다."
    if "what breaks first" in title_lower:
        return "현장은 성능보다 실패 지점을 먼저 검증하는 팀을 선택한다."
    return f"'{title}'는 이번 사이클에서 우선 검토할 만한 신호로 떠올랐습니다."


def _action_point_for_item(item: Dict[str, object]) -> str:
    title = str(item.get("title", "")).strip()
    title_lower = title.lower()

    if "starter" in title_lower or "orchestration" in title_lower:
        return "에이전트 워크플로 스타터를 작은 파일럿에 붙여 평가 훅과 도구 호출 로그부터 점검해볼 수 있습니다."
    if "template" in title_lower or "threat modeling" in title_lower:
        return "자동화 대상 업무마다 위협 모델링 템플릿을 붙여 승인 기준과 실패 시 대응 절차를 먼저 정의할 수 있습니다."
    if "architecture review" in title_lower or "checklist" in title_lower:
        return "기존 설계 리뷰 체크리스트를 자동화 파이프라인 입력 항목으로 바꿔 반복 검토를 줄일 수 있습니다."
    if "what breaks first" in title_lower or "tool-using" in title_lower:
        return "도구 사용 에이전트에는 실패 로그, 권한 제한, 사람 검토 지점을 먼저 넣는 편이 안전합니다."
    return f"'{title}'와 비슷한 흐름을 작은 범위에서 파일럿으로 검증해볼 수 있습니다."


def _format_comparison(difference: str, conclusion: str, implication: str, use_triplet_format: bool) -> str:
    if use_triplet_format:
        return f"차이: {difference} 결론: {conclusion} 의미: {implication}"
    return f"{difference} 그래서 {conclusion} 결국 {implication}"


def _importance_badge(item: Dict[str, object]) -> str:
    score = int(item.get("score", 0))
    cross_source = int(item.get("cross_source_score", 0))
    practicality = int(item.get("practicality_score", 0))
    if score >= 90 or cross_source >= 12:
        return "🔥 핵심"
    if score >= 72 or practicality >= 14:
        return "⚡ 중요"
    return "📎 참고"


def _build_comparisons(items: List[Dict[str, object]], grouped: Dict[str, List[Dict[str, object]]]) -> List[str]:
    source_counts = _count_sources(items)
    compare_prompt = _load_compare_prompt().lower()
    include_reddit = "reddit" in compare_prompt
    include_direction = "underlying direction" in compare_prompt or "direction" in compare_prompt
    use_triplet_format = all(keyword in compare_prompt for keyword in ["difference", "conclusion", "implication"])

    differences: List[str] = []
    if source_counts.get("GitHub Trending", 0) > 0 and source_counts.get("Hacker News", 0) > 0:
        differences.append("GitHub는 바로 도입 가능한 구현 자산을 내놓고, HN은 그 자산이 실제 운영에서 부딪히는 실패 비용을 드러냅니다.")
    if source_counts.get("RSS News", 0) > 0 and source_counts.get("GitHub Trending", 0) > 0:
        differences.append("News는 조직 수요가 커지는 방향을 밀어 올리고, GitHub는 그 수요를 곧바로 구현할 수 있는 형태로 번역합니다.")
    if include_reddit and source_counts.get("Reddit", 0) > 0:
        differences.append("Reddit은 기능 설명보다 현업 사용자가 직접 겪는 권한 경계와 운영 마찰을 먼저 끌어올립니다.")
    elif source_counts.get("Hacker News", 0) > 0:
        differences.append("커뮤니티 채널은 기능 소개보다 권한 경계와 실패 비용을 더 앞세웁니다.")

    if not differences:
        return []

    conclusion = "결국 승부는 새 모델이 아니라 구현 속도와 운영 통제를 함께 갖춘 팀에서 결정됩니다."
    implication = "이 흐름에서 늦는 팀은 기능 경쟁이 아니라 승인 속도와 운영 안정성에서 밀리게 됩니다."
    if include_direction:
        implication = "이 흐름은 실험 중심 조직보다 통제 가능한 실행 체계를 먼저 만든 조직 쪽으로 시장을 이동시킵니다."

    combined_difference = " / ".join(differences)
    return [_format_comparison(combined_difference, conclusion, implication, use_triplet_format)]


def _build_implications(items: List[Dict[str, object]], grouped: Dict[str, List[Dict[str, object]]]) -> List[str]:
    implications: List[str] = []

    if _count_topic_hits(items, "AI Agent") >= 3:
        implications.append("에이전트 경쟁력은 이제 모델 성능보다 워크플로 분해, 도구 호출 통제, 평가 루프 설계에서 결정됩니다.")
    if _count_topic_hits(items, "AI Agent") >= 1:
        implications.append("MCP, tool use, skills 계층은 곧 권한 경계와 실행 책임을 정의하는 운영 표준이 됩니다.")
    if _count_topic_hits(items, "Security") + _count_topic_hits(items, "Threat Modeling") >= 3:
        implications.append("보안 아키텍처 리뷰와 threat modeling을 초기에 넣지 않은 팀은 자동화 범위가 커질수록 승인 비용과 수정 비용이 폭증합니다.")
    if _count_topic_hits(items, "AI Agent") >= 3:
        implications.append("실무 자동화는 단일 모델 도입으로 끝나지 않고, 사람 검토 지점과 실패 복구 절차를 포함한 운영 체계로 굳어집니다.")

    implications.append("결국 앞서는 팀은 더 똑똑한 모델을 가진 팀이 아니라 더 통제 가능하고 더 검증 가능한 시스템을 먼저 완성한 팀입니다.")
    return implications[:3]


def _count_sources(items: Iterable[Dict[str, object]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for item in items:
        for source in str(item.get("source", "")).split(" | "):
            if source:
                counts[source] += 1
    return dict(counts)


def _count_topic_hits(items: Iterable[Dict[str, object]], topic_name: str) -> int:
    total = 0
    for item in items:
        tags = list(item.get("topic_tags", []))
        if topic_name in tags:
            total += 1
    return total


def _format_topic_list(topics: List[str]) -> str:
    localized = [topic for topic in topics]
    if len(localized) == 1:
        return localized[0]
    if len(localized) == 2:
        return f"{localized[0]}와 {localized[1]}"
    return f"{localized[0]}, {localized[1]}, {localized[2]}"


def _pattern_based_summary(text: str) -> str:
    patterns = [
        (
            ["starter kit", "agent workflow", "evaluation hook", "tool execution"],
            "다단계 에이전트 워크플로를 위한 스타터킷에 평가 훅과 도구 실행 예시를 담은 내용입니다",
        ),
        (
            ["threat modeling", "template", "automation pipeline"],
            "AI 자동화 파이프라인에 적용할 수 있는 위협 모델링 템플릿을 정리한 내용입니다",
        ),
        (
            ["architecture review", "guardrail", "production"],
            "운영 환경에서 에이전트 기반 아키텍처 리뷰를 적용할 때 필요한 가드레일을 다룬 내용입니다",
        ),
        (
            ["failure mode", "tool permission", "memory", "evaluation loop"],
            "도구 권한, 메모리, 평가 루프 관점에서 코딩 에이전트의 실패 양상을 비교한 내용입니다",
        ),
        (
            ["tool registr", "permission model", "prompt contract"],
            "에이전트 시스템에서 도구 레지스트리, 권한 모델, 프롬프트 계약을 어떻게 설계할지 비교한 내용입니다",
        ),
        (
            ["alert triage", "human review"],
            "보안 알림 분류 자동화에서 어디까지 AI가 맡고 어디서부터 사람 검토가 필요한지 다룬 내용입니다",
        ),
        (
            ["classic threat modeling", "ai copilots", "autonomous tasks"],
            "기존 위협 모델링을 AI 코파일럿과 자율 작업 환경에 맞게 적용하는 흐름을 설명한 내용입니다",
        ),
        (
            ["workflow automation", "design review", "policy check"],
            "설계 리뷰와 정책 점검까지 확장되는 AI 워크플로 자동화 수요를 설명한 내용입니다",
        ),
        (
            ["agent", "security review"],
            "에이전트를 활용한 보안 검토 방식과 운영 체크리스트를 다룬 내용입니다",
        ),
    ]

    for keywords, sentence in patterns:
        if all(keyword in text for keyword in keywords):
            return sentence

    if "threat modeling" in text:
        return "AI 시스템에 필요한 위협 모델링 이슈를 다룬 내용입니다"
    if "architecture review" in text:
        return "보안 아키텍처 리뷰와 설계 점검 흐름을 다룬 내용입니다"
    if "automation" in text:
        return "실무에 적용되는 AI 자동화 사례를 설명한 내용입니다"
    if "tool use" in text or "mcp" in text or "skills" in text:
        return "에이전트의 도구 사용 방식과 실행 구조를 설명한 내용입니다"
    if "agent" in text:
        return "에이전트 기반 워크플로와 운영 방식을 다룬 내용입니다"
    return ""
