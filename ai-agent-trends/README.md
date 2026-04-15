# AI Agent Trends

`ai-agent-trends` is a Windows-friendly Python project that collects AI trend signals daily and turns them into structured markdown reports.

The v1 pipeline focuses on these topics:

- AI Agent & Automation
- MCP / tool use / skills
- AI Security
- threat modeling

Sources in v1:

- GitHub Trending
- Hacker News
- Reddit
- Tech news via RSS feeds

`X/Twitter` is intentionally excluded.

## Project Purpose

The project gathers recent trend signals from builder communities and tech news, normalizes them into a common schema, removes duplicates, classifies them into predefined topics, ranks their importance, and writes a markdown report to the `reports/` folder.

If live collection fails because of network limits, missing packages, or upstream changes, the pipeline falls back to mock data so the end-to-end run still succeeds.

## Folder Structure

```text
ai-agent-trends/
├─ config/        # Topics, source definitions, and report schedule settings
├─ data/
│  ├─ raw/        # Raw collected source payloads
│  └─ processed/  # Normalized and ranked pipeline output
├─ prompts/       # Prompt text for future LLM-assisted classification/summarization
├─ reports/       # Generated markdown reports
├─ scripts/       # Fetchers and pipeline stages
└─ README.md
```

## Pipeline Output Schema

Each normalized item uses this schema:

```python
{
    "title": str,
    "url": str,
    "source": str,
    "summary": str,
    "score": int,
    "created_at": str,
    "topic_tags": list[str]
}
```

## How To Run

1. Install Python 3.10+.
2. Install optional packages:

```powershell
pip install requests beautifulsoup4 pyyaml python-dotenv
```

3. Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key_here
```

4. Run the pipeline:

```powershell
python scripts/run_pipeline.py
```

The script writes:

- raw source snapshots into `data/raw/`
- normalized and ranked results into `data/processed/`
- a report like `reports/YYYY-MM-DD.md`

## Notes

- The code uses `requests` plus `BeautifulSoup` or public APIs/RSS where appropriate.
- The code is written to run on Windows and avoids Linux-only dependencies.
- `run_pipeline.py` is executable as the main entry point.
- `summarize_items.py` loads `OPENAI_API_KEY` from `.env` and falls back to a local summary if the key is missing or the API call fails.
