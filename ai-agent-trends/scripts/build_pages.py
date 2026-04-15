from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable, List

ROOT_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT_DIR / "reports"
SITE_DIR = ROOT_DIR / "site"
SITE_REPORTS_DIR = SITE_DIR / "reports"


def build_pages() -> List[Path]:
    report_paths = sorted(
        [path for path in REPORTS_DIR.glob("*.md") if path.is_file()],
        reverse=True,
    )

    SITE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    written_files: List[Path] = []

    for report_path in report_paths:
        markdown_text = report_path.read_text(encoding="utf-8")
        report_html = _wrap_page(
            title=f"AI Trend Report {report_path.stem}",
            content_html=_render_markdown(markdown_text),
            description=f"{report_path.stem} generated AI trend report.",
            home_href="../index.html",
        )
        output_path = SITE_REPORTS_DIR / f"{report_path.stem}.html"
        output_path.write_text(report_html, encoding="utf-8")
        written_files.append(output_path)

    index_html = _build_index_page(report_paths)
    index_path = SITE_DIR / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    written_files.append(index_path)

    nojekyll_path = SITE_DIR / ".nojekyll"
    nojekyll_path.write_text("", encoding="utf-8")
    written_files.append(nojekyll_path)

    return written_files


def _build_index_page(report_paths: Iterable[Path]) -> str:
    report_paths = list(report_paths)
    latest_report = report_paths[0] if report_paths else None

    hero_html = [
        "<section class='hero'>",
        "<p class='eyebrow'>AI Agent Trends</p>",
        "<h1>Daily trend reports published from GitHub Actions</h1>",
        "<p class='lede'>Windows local runs can continue as-is, and GitHub now has a web-friendly report surface for scheduled publishing.</p>",
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

    content_html = "\n".join(hero_html + latest_html + archive_html)
    return _wrap_page(
        title="AI Trend Reports",
        content_html=content_html,
        description="Automated AI trend reports published with GitHub Actions and GitHub Pages.",
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
    @media (max-width: 720px) {{
      .shell {{ width: min(100vw - 20px, 920px); padding-top: 18px; }}
      .topbar {{ flex-direction: column; align-items: flex-start; }}
      .hero, .panel, .report {{ border-radius: 18px; }}
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
    print(f"Built {len(outputs)} files into {SITE_DIR}")
