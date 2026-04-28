from __future__ import annotations

from datetime import datetime
import getpass
import os
from pathlib import Path
import platform
import shutil
import sys
from typing import Any, Dict, List

from deduplicate import deduplicate_items
from fetch_discovery import fetch_items as fetch_discovery
from fetch_github_trending import fetch_items as fetch_github_trending
from fetch_hn import fetch_items as fetch_hn
from fetch_news import fetch_items as fetch_news
from fetch_reddit import fetch_items as fetch_reddit
from fetch_watchlist import fetch_items as fetch_watchlist
from normalize import load_config, normalize_items, write_json
from rank_items import rank_items
from summarize_items import build_report_markdown, enrich_report_candidates, report_filename, write_report

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
REPORTS_DIR = ROOT_DIR / "reports"


def run_pipeline() -> Dict[str, Any]:
    configure_console_encoding()
    log_runtime_context()

    # Load lightweight JSON-compatible YAML configs from the repo.
    topics_config = load_config(CONFIG_DIR / "topics.yaml")
    sources_config = load_config(CONFIG_DIR / "sources.yaml")
    schedule_config = load_config(CONFIG_DIR / "schedule.yaml")

    raw_collections = collect_all_sources(sources_config)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    write_json(DATA_RAW_DIR / f"raw-{timestamp}.json", raw_collections)

    # Flatten source-specific collections into one common processing stream.
    flattened_raw = [item for source_items in raw_collections.values() for item in source_items]
    normalized = normalize_items(flattened_raw, topics_config)
    deduplicated = deduplicate_items(normalized)
    ranked = rank_items(deduplicated)
    ranked = enrich_report_candidates(ranked)

    write_json(DATA_PROCESSED_DIR / f"normalized-{timestamp}.json", normalized)
    write_json(DATA_PROCESSED_DIR / f"ranked-{timestamp}.json", ranked)

    now = datetime.now()
    report_name = report_filename(now)
    report_path = REPORTS_DIR / report_name
    # Always emit a report, even when upstream fetchers had to fall back to mock items.
    write_report(report_path, build_report_markdown(ranked))

    return {
        "raw_count": len(flattened_raw),
        "normalized_count": len(normalized),
        "deduplicated_count": len(deduplicated),
        "ranked_count": len(ranked),
        "report_path": str(report_path),
    }


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def detect_runtime() -> str:
    system_name = platform.system().lower()
    if system_name == "windows":
        return "windows"
    if system_name == "linux":
        release = platform.release().lower()
        if "microsoft" in release or os.getenv("WSL_DISTRO_NAME"):
            return "wsl"
        return "linux"
    return system_name or "unknown"


def log_runtime_context() -> None:
    path_entries = os.getenv("PATH", "").split(os.pathsep)
    codex_path_entries = [entry for entry in path_entries if "codex" in entry.lower() or "npm" in entry.lower()]

    print("Runtime context:")
    print(f"  runtime: {detect_runtime()}")
    print(f"  user: {getpass.getuser()}")
    print(f"  cwd: {Path.cwd()}")
    print(f"  HOME: {os.getenv('HOME', '')}")
    print(f"  USERPROFILE: {os.getenv('USERPROFILE', '')}")
    print(f"  CODEX_CLI_PATH: {os.getenv('CODEX_CLI_PATH', '')}")
    print(f"  CODEX_HOME: {os.getenv('CODEX_HOME', '')}")
    print(f"  which codex: {shutil.which('codex') or ''}")
    print(f"  which codex.cmd: {shutil.which('codex.cmd') or ''}")
    print(f"  which codex.exe: {shutil.which('codex.exe') or ''}")
    print(f"  PATH codex/npm entries: {', '.join(codex_path_entries) if codex_path_entries else '(none)'}")


def collect_all_sources(sources_config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    collections: Dict[str, List[Dict[str, Any]]] = {}

    if sources_config.get("github_trending", {}).get("enabled", True):
        collections["github_trending"] = fetch_github_trending(sources_config.get("github_trending", {}))
    else:
        collections["github_trending"] = []

    if sources_config.get("hacker_news", {}).get("enabled", True):
        collections["hacker_news"] = fetch_hn(sources_config.get("hacker_news", {}))
    else:
        collections["hacker_news"] = []

    if sources_config.get("reddit", {}).get("enabled", True):
        collections["reddit"] = fetch_reddit(sources_config.get("reddit", {}))
    else:
        collections["reddit"] = []

    if sources_config.get("rss_news", {}).get("enabled", True):
        collections["rss_news"] = fetch_news(sources_config.get("rss_news", {}))
    else:
        collections["rss_news"] = []

    if sources_config.get("discovery", {}).get("enabled", False):
        collections["discovery"] = fetch_discovery(sources_config.get("discovery", {}))
    else:
        collections["discovery"] = []

    if sources_config.get("watchlist", {}).get("enabled", False):
        collections["watchlist"] = fetch_watchlist(sources_config.get("watchlist", {}))
    else:
        collections["watchlist"] = []

    return collections


if __name__ == "__main__":
    result = run_pipeline()
    print("Pipeline completed.")
    print(f"Raw items: {result['raw_count']}")
    print(f"Normalized items: {result['normalized_count']}")
    print(f"Deduplicated items: {result['deduplicated_count']}")
    print(f"Ranked items: {result['ranked_count']}")
    print(f"Report: {result['report_path']}")
