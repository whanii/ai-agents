from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable, List

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT_DIR / "reports"
DOCS_DIR = ROOT_DIR.parent / "docs"
DOCS_REPORTS_DIR = DOCS_DIR / "reports"


def build_pages() -> List[Path]:
    report_paths = sorted(
        [path for path in REPORTS_DIR.glob("*.md") if path.is_file()],
        reverse=True,
    )

    DOCS_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    written_files: List[Path] = []

    for report_path in report_paths:
        markdown_text = report_path.read_text(encoding="utf-8")
        report_html = _wrap_page(
            title=f"AI Trend Report {report_path.stem}",
            content_html=_render_markdown(markdown_text),
            description=f"{report_path.stem} generated AI trend report.",
            home_href="../index.html",
        )
        output_path = DOCS_REPORTS_DIR / f"{report_path.stem}.html"
        output_path.write_text(report_html, encoding="utf-8")
        written_files.append(output_path)

    index_html = _build_index_page(report_paths)
    index_path = DOCS_DIR / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    written_files.append(index_path)

    nojekyll_path = DOCS_DIR / ".nojekyll"
    nojekyll_path.write_text("", encoding="utf-8")
    written_files.append(nojekyll_path)

    return written_files


def _build_index_page(report_paths: Iterable[Path]) -> str:
    report_paths = list(report_paths)
    latest_report = report_paths[0] if report_paths else None

    hero_html = [
        "<section class='hero'>",
        "<p class='eyebrow'>AI Agent Trends</p>",
        "<h1>Daily trend reports published from a Windows scheduler</h1>",
        "<p class='lede'>Reports are generated on the local Windows machine, committed to GitHub, and served through GitHub Pages.</p>",
        "</section>",
    ]

    latest_html: List[str] = ["<section class='panel'>", "<h2>Latest Report</h2>"]
    if latest_report is None:
        latest_html.append("<p>No report has been generated yet.</p>")
    else:
        latest_html.append(
            f"<p><a class='primary-link' href='reports/{latest_report.stem}.html'>{html.escape(latest_report.stem)} report</a></p>"
        )
        latest_html.append(_report_meta_html(latest_report))
    latest_html.append("</section>")

    methodology_html = [
        "<section class='panel'>",
        "<p class='eyebrow'>How It Works</p>",
        "<h2>트렌드 수집 방식</h2>",
        "<p>이 페이지는 AI 모델, AI 에이전트, 보안, 위협 모델링 흐름을 매일 수집해 실무 관점의 리포트로 정리합니다. 안정적인 기본 소스와 새 후보를 찾는 발견형 수집을 함께 사용합니다.</p>",
        "<div class='info-grid'>",
        "<article class='info-card'>",
        "<h3>Core Sources</h3>",
        "<p>GitHub Trending, Hacker News, Reddit, 주요 RSS처럼 매일 안정적으로 확인할 수 있는 기본 수집원입니다.</p>",
        "</article>",
        "<article class='info-card'>",
        "<h3>Discovery</h3>",
        "<p>AI agent, MCP, LLM inference, AI security 같은 키워드로 HN과 GitHub Search에서 새 후보를 찾습니다. 최소 점수, 스타 수, 제외 패턴으로 스팸성 항목을 줄입니다.</p>",
        "</article>",
        "<article class='info-card'>",
        "<h3>Watchlist</h3>",
        "<p>OpenAI, Google AI, Hugging Face처럼 중요한 조직과 프로젝트의 발표를 별도로 추적합니다.</p>",
        "</article>",
        "<article class='info-card'>",
        "<h3>Report View</h3>",
        "<p>수집 항목은 AI Model, AI Agent, Security, Threat Modeling 네 토픽으로 분류됩니다. 상위 항목은 LLM으로 요약하고, 관련 항목과 제외 후보도 함께 보여줍니다.</p>",
        "</article>",
        "</div>",
        "</section>",
    ]

    criteria_html = [
        "<section class='panel'>",
        "<p class='eyebrow'>Selection Rules</p>",
        "<h2>리포트 포함 기준</h2>",
        "<p>수집된 항목은 점수화한 뒤 기준점 이상 후보만 리포트 본문에 올립니다. 기본 하한과 당일 상위 퍼센타일을 함께 사용하고, 단순 점수순만 쓰면 한 토픽에 쏠릴 수 있어 토픽별 대표 항목을 먼저 확보합니다.</p>",
        "<div class='info-grid'>",
        "<article class='info-card'>",
        "<h3>기본 기준</h3>",
        "<p>총점 50점을 기본 하한으로 두되, 후보가 충분히 많으면 당일 점수 분포의 상위 75퍼센타일 컷과 비교해 더 높은 기준을 사용합니다. 하루 리포트에는 최대 6개만 포함합니다.</p>",
        "</article>",
        "<article class='info-card'>",
        "<h3>점수 구성</h3>",
        "<p>출처 가중치, 최신성, 인기도, 토픽 매칭, 실용성, 신규성, 교차출처 신호, Discovery/Watchlist 신뢰도를 합산하고 Discovery 불확실성은 감점합니다.</p>",
        "</article>",
        "<article class='info-card'>",
        "<h3>토픽 다양성</h3>",
        "<p>AI Model, AI Agent, Security, Threat Modeling 후보가 있으면 각 토픽의 대표 항목을 우선 검토하고, 한 토픽이 최대 2개를 넘지 않도록 먼저 제한합니다.</p>",
        "</article>",
        "<article class='info-card'>",
        "<h3>관련 항목</h3>",
        "<p>핵심 6개에 들지 못해도 같은 토픽에서 점수가 높은 항목은 관련 항목이나 주목할 만한 제외 항목으로 남깁니다.</p>",
        "</article>",
        "</div>",
        "<details class='score-details'>",
        "<summary>점수화 방식 자세히 보기</summary>",
        "<ul>",
        "<li><strong>출처 가중치</strong>: GitHub Trending 24점, Hacker News 22점, Watchlist 21점, RSS 20점, Reddit 18점, Discovery 16점.</li>",
        "<li><strong>최신성</strong>: 6시간 이내 20점, 24시간 이내 14점, 72시간 이내 8점, 그 외 3점.</li>",
        "<li><strong>인기도</strong>: 원본 점수 또는 스타 수를 최대 100까지만 반영하고 5로 나눈 값, 최대 20점.</li>",
        "<li><strong>토픽 매칭</strong>: 매칭된 토픽 1개당 6점.</li>",
        "<li><strong>실용성</strong>: automation, workflow, tool, security, inference 같은 실행 지향 키워드로 최대 24점.</li>",
        "<li><strong>신규성</strong>: new, emerging, release, benchmark, weights 같은 변화 신호 키워드로 최대 16점.</li>",
        "<li><strong>교차출처</strong>: 유사 항목이 2개 출처에서 보이면 12점, 3개 이상이면 18점.</li>",
        "<li><strong>Discovery/Watchlist 신뢰도</strong>: Discovery는 HN 포인트나 GitHub 스타 수에 따라 4~12점, Watchlist는 12점을 부여합니다.</li>",
        "<li><strong>Discovery 감점</strong>: 검색 발견 후보는 기본 6점 감점하고, 신뢰도와 설명 품질이 충분하면 감점을 줄입니다.</li>",
        "</ul>",
        "</details>",
        "</section>",
    ]

    archive_html: List[str] = ["<section class='panel'>", "<h2>Archive</h2>"]
    if not report_paths:
        archive_html.append("<p>No archived reports yet.</p>")
    else:
        archive_html.append("<ul class='report-list'>")
        for report_path in report_paths:
            archive_html.append(
                f"<li><a href='reports/{report_path.stem}.html'>{html.escape(report_path.stem)}</a></li>"
            )
        archive_html.append("</ul>")
    archive_html.append("</section>")

    content_html = "\n".join(hero_html + latest_html + methodology_html + criteria_html + archive_html)
    return _wrap_page(
        title="AI Trend Reports",
        content_html=content_html,
        description="Automated AI trend reports published from a Windows scheduler and served with GitHub Pages.",
        home_href="index.html",
    )


def _report_meta_html(report_path: Path) -> str:
    return (
        "<p class='meta'>"
        f"Source markdown: <code>reports/{html.escape(report_path.name)}</code>"
        "</p>"
    )


def _wrap_page(title: str, content_html: str, description: str, home_href: str) -> str:
    safe_title = html.escape(title)
    safe_description = html.escape(description)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <meta name="description" content="{safe_description}">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4efe6;
      --panel: rgba(255, 251, 245, 0.9);
      --ink: #1f2933;
      --muted: #52606d;
      --accent: #a63a17;
      --accent-soft: #f6d8c7;
      --line: rgba(31, 41, 51, 0.12);
      --shadow: 0 18px 45px rgba(79, 56, 33, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.75), transparent 38%),
        linear-gradient(180deg, #e7ddcf 0%, var(--bg) 42%, #efe8de 100%);
      line-height: 1.7;
    }}
    .shell {{
      width: min(920px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 24px;
      font-size: 0.95rem;
    }}
    .topbar a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .hero, .panel, .report {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 28px;
      margin-bottom: 18px;
    }}
    .panel {{
      padding: 24px;
      margin-bottom: 18px;
    }}
    .report {{
      padding: 28px;
    }}
    .eyebrow {{
      margin: 0 0 8px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
      font-size: 0.8rem;
      font-weight: 700;
    }}
    h1, h2, h3 {{
      line-height: 1.2;
    }}
    h1 {{ margin: 0 0 10px; font-size: clamp(2rem, 5vw, 3.3rem); }}
    h2 {{ margin-top: 0; font-size: 1.55rem; }}
    h3 {{ margin-top: 1.8rem; font-size: 1.15rem; }}
    p, li {{ font-size: 1.02rem; }}
    .lede, .meta {{ color: var(--muted); }}
    .primary-link {{
      color: var(--accent);
      font-size: 1.15rem;
      font-weight: 700;
      text-decoration: none;
    }}
    .report-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }}
    .report-list a {{
      color: var(--ink);
      text-decoration: none;
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
      display: inline-block;
    }}
    .info-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 18px;
    }}
    .info-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: rgba(255, 255, 255, 0.42);
    }}
    .info-card h3 {{
      margin: 0 0 8px;
      color: var(--accent);
    }}
    .info-card p {{
      margin: 0;
      color: var(--muted);
    }}
    .report a {{
      color: var(--accent);
    }}
    code {{
      background: rgba(31, 41, 51, 0.06);
      border-radius: 6px;
      padding: 0.12rem 0.32rem;
      font-size: 0.95em;
    }}
    pre {{
      background: #1d242b;
      color: #f5f7fa;
      padding: 16px;
      border-radius: 16px;
      overflow-x: auto;
    }}
    blockquote {{
      margin: 1rem 0;
      padding: 0.2rem 0 0.2rem 1rem;
      border-left: 4px solid var(--accent-soft);
      color: var(--muted);
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 16px;
      background: rgba(255, 255, 255, 0.42);
    }}
    .score-details {{
      margin-top: 16px;
    }}
    summary {{
      cursor: pointer;
      color: var(--accent);
      font-weight: 700;
    }}
    @media (max-width: 720px) {{
      .shell {{ width: min(100vw - 20px, 920px); padding-top: 18px; }}
      .topbar {{ flex-direction: column; align-items: flex-start; }}
      .hero, .panel, .report {{ border-radius: 18px; }}
      .info-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <a href="{html.escape(home_href)}">Home</a>
      <span class="meta">Published with GitHub Pages</span>
    </div>
    {content_html}
  </main>
</body>
</html>
"""


def _render_markdown(markdown_text: str) -> str:
    try:
        import markdown

        body_html = markdown.markdown(
            markdown_text,
            extensions=["extra", "sane_lists", "smarty"],
        )
    except Exception:
        body_html = _simple_markdown_to_html(markdown_text)
    return f"<article class='report'>{body_html}</article>"


def _simple_markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    html_lines: List[str] = []
    in_list = False
    in_code = False
    code_lines: List[str] = []

    for raw_line in lines:
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                html_lines.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue

        if line in {"<details>", "</details>"} or line.startswith("<summary>"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(line)
            continue

        if line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{_inline_markdown(line[2:].strip())}</h1>")
            continue

        if line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{_inline_markdown(line[3:].strip())}</h2>")
            continue

        if line.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{_inline_markdown(line[4:].strip())}</h3>")
            continue

        if line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline_markdown(line[2:].strip())}</li>")
            continue

        if in_list:
            html_lines.append("</ul>")
            in_list = False

        html_lines.append(f"<p>{_inline_markdown(line.strip())}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_code:
        html_lines.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")

    return "\n".join(html_lines)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


if __name__ == "__main__":
    outputs = build_pages()
    print(f"Built {len(outputs)} files into {DOCS_DIR}")
