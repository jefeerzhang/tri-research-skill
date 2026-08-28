#!/usr/bin/env python3
"""Report Shell 渲染器：验收报告 → 章纸风格单文件 HTML。

外壳（Report Shell，见 CONTEXT.md）是纯派生展示物：单向生成、可重渲可删，
验收体系（proof / INTEGRITY）不感知它；报告 Markdown 是唯一真源。

渲染器是标准库手写的迷你实现（零 Python 依赖），只承诺渲染
``references/report-format.md`` 契约内的结构——7 章节、单行参考文献、
执行情况表格、行内 ``[N]`` / 置信标签；契约外的 Markdown 语法降级为
转义纯文本段落（不丢字、只降排版）。版式借鉴 cailun 造纸三律：
纸是静的（零外链 / 零 JS / 零构建）、字是真的（只抄录报告）、版是定的。
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import StateError  # noqa: E402
from validate_report import H1_RE, REFERENCE_RE, URL_RE, _strip_url_punctuation, canonicalize_url  # noqa: E402

CONF_RE = re.compile(r"\[(高|中|低)\]")
CITE_RE = re.compile(r"\[(\d+)\]")
TIER_RE = re.compile(r"层级[:：]\s*([123])")
SOURCE_RE = re.compile(r"来源[:：]\s*([^\n,，]+)")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
CONF_CLASS = {"高": "high", "中": "mid", "低": "low"}

CSS = """
:root{--paper:#faf6ef;--ink:#2a2620;--muted:#8a8378;--hair:#e4dccb;--accent:#8c4356;
--green:#2e7d4f;--amber:#a8730a;--gray:#9a938a}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font-family:Georgia,"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,serif;
line-height:1.85;font-size:16.5px}
main{max-width:65ch;margin:0 auto;padding:56px 24px 96px}
.kicker{color:var(--muted);font-size:.78rem;letter-spacing:.35em}
header h1{font-size:1.9rem;line-height:1.4;margin:10px 0 0;letter-spacing:.02em}
header{border-bottom:3px double var(--hair);padding-bottom:28px;margin-bottom:8px}
section{padding:26px 0;border-bottom:1px solid var(--hair)}
section:last-of-type{border-bottom:none}
h2{font-size:1.05rem;letter-spacing:.28em;color:var(--accent);margin:0 0 18px;font-weight:600}
p{margin:0 0 14px;text-align:justify}
p.lead{font-size:1.06rem}
strong{font-weight:700}
.conf{display:inline-block;font-size:.72rem;padding:0 .5em;border-radius:3px;vertical-align:1px;border:1px solid}
.conf-high{color:var(--green);border-color:var(--green)}
.conf-mid{color:var(--amber);border-color:var(--amber)}
.conf-low{color:var(--gray);border-color:var(--gray)}
a.cite{color:var(--accent);text-decoration:none;border-bottom:1px dotted var(--accent)}
table{width:100%;border-collapse:collapse;font-size:.9rem;margin:6px 0 14px}
th,td{border:1px solid var(--hair);padding:7px 10px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;background:rgba(0,0,0,.02);white-space:nowrap}
ol.refs{list-style:none;margin:0;padding:0}
ol.refs li{padding:12px 0;border-bottom:1px dashed var(--hair)}
.ref-num{color:var(--accent);font-weight:700;margin-right:.5em}
.tier{display:inline-block;font-size:.7rem;border-radius:3px;padding:0 .45em;margin:0 .4em;border:1px solid}
.tier-1{color:var(--paper);background:var(--accent);border-color:var(--accent)}
.tier-2{color:var(--amber);border-color:var(--amber)}
.tier-3{color:var(--gray);border-color:var(--gray)}
.ref-url a{color:var(--muted);font-size:.82rem;word-break:break-all;text-decoration:none;border-bottom:1px solid var(--hair)}
footer{color:var(--muted);font-size:.75rem;text-align:center;padding:28px 0 0;letter-spacing:.12em}
.prov{display:block;font-size:.76rem;color:var(--muted);margin-top:4px}
.prov-miss{color:var(--gray);font-style:italic}
@media print{body{background:#fff}main{padding:0}}
"""


class RenderError(RuntimeError):
    """The input is not renderable as a research report."""


def render_inline(text: str, seen_cites: set[int]) -> str:
    """Escape then apply contract-internal inline marks (cite / conf / bold).

    Escaping happens FIRST, so report content can never inject markup;
    the substituted spans only contain characters we generated.
    """
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = CONF_RE.sub(lambda m: f'<span class="conf conf-{CONF_CLASS[m.group(1)]}">[{m.group(1)}]</span>', escaped)

    def _cite(match: re.Match[str]) -> str:
        number = int(match.group(1))
        anchor = f' id="cite-{number}-first"' if number not in seen_cites else ""
        seen_cites.add(number)
        return f'<a class="cite"{anchor} href="#ref-{number}">[{number}]</a>'

    return CITE_RE.sub(_cite, escaped)


def _meta(text: str) -> str:
    """Escape a reference fragment, then promote 层级 / 来源 to marks."""
    escaped = html.escape(text)
    escaped = TIER_RE.sub(lambda m: f'<span class="tier tier-{m.group(1)}">层级 {m.group(1)}</span>', escaped)
    # Text is already escaped here — wrapping must NOT escape again.
    escaped = SOURCE_RE.sub(lambda m: f'<span class="src">{m.group(0)}</span>', escaped)
    return escaped


def render_reference(number: int, entry: str, provenance=None) -> str:
    """One 参考文献 line → list item with tier badge, source chip, URL link.

    The URL may sit anywhere in the line (contract says last, real reports
    sometimes place it mid-line) — fields are promoted on BOTH sides of it.
    ``provenance`` is the Provenance Note callable ``number × url → note HTML``
    (None when no ledger context is requested).
    """
    url_match = URL_RE.search(entry)
    url = _strip_url_punctuation(url_match.group(0)) if url_match else None
    parts = [f'<span class="ref-num">[{number}]</span>']
    if url_match:
        if url:
            parts.append(_meta(entry[: url_match.start()]))
            safe_url = html.escape(url, quote=True)
            parts.append(f'<span class="ref-url"><a href="{safe_url}" rel="noopener">{html.escape(url)}</a></span>')
            parts.append(_meta(entry[url_match.end() :]))
        else:
            # URL_RE matched but punctuation stripping emptied it — keep raw text.
            parts.append(_meta(entry))
    else:
        parts.append(_meta(entry))
    if provenance is not None:
        parts.append(provenance(number, canonicalize_url(url) if url else None))
    return f'<li id="ref-{number}">{"".join(parts)}</li>'


def render_table(lines: list[str], seen_cites: set[int]) -> str:
    """Consecutive ``| ... |`` lines → HTML table (separator row skipped).

    Shares the section's ``seen_cites`` so `cite-N-first` ids stay unique.
    """
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue  # header/body separator
        rows.append(cells)
    if not rows:
        return ""
    head, *body = rows
    thead = "".join(f"<th>{render_inline(cell, seen_cites)}</th>" for cell in head)
    trs = "".join(
        "<tr>" + "".join(f"<td>{render_inline(cell, seen_cites)}</td>" for cell in row) + "</tr>" for row in body
    )
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{trs}</tbody></table>"


def split_sections(text: str) -> tuple[str, list[str], list[tuple[str, list[str]]]]:
    """Split report into (H1 title, preamble lines, [(section title, body lines)...]).

    The preamble is everything between the H1 and the first ``## `` —
    rendered as escaped paragraphs so the "不丢字" contract holds even
    for content the section parser does not model (e.g. blockquotes).
    """
    heading = H1_RE.search(text)
    title = heading.group(1) if heading else ""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for part in re.split(r"(?m)^(?=## )", text):
        if not part.startswith("## "):
            for line in part.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("# "):
                    preamble.append(stripped)
            continue
        title_line, _, body = part[3:].partition("\n")
        sections.append((title_line.strip(), body.splitlines()))
    return title, preamble, sections


def render_section(title: str, lines: list[str], seen_cites: set[int], provenance=None) -> str:
    """Section body → paragraphs / tables / (for 参考文献) the refs list.

    ``provenance`` (Provenance Note) is a callable ``number → note HTML``;
    contract-external markdown degrades to escaped plain paragraphs.
    """
    body_blocks: list[str] = []
    table_lines: list[str] = []
    paragraphs_wrapped = False

    def flush_table() -> None:
        if table_lines:
            body_blocks.append(render_table(table_lines, seen_cites))
            table_lines.clear()

    if title == "参考文献":
        refs = [(int(number), entry) for number, entry in REFERENCE_RE.findall("\n".join(lines))]
        items = "".join(render_reference(number, entry, provenance) for number, entry in refs)
        return f'<section><h2>{html.escape(title)}</h2><ol class="refs">{items}</ol></section>'
    for line in lines:
        if TABLE_ROW_RE.match(line):
            table_lines.append(line)
            continue
        flush_table()
        if not line.strip():
            continue
        body_blocks.append(render_inline(line.strip(), seen_cites))
    flush_table()
    blocks = []
    for block in body_blocks:
        if block.startswith("<table"):
            blocks.append(block)
        else:
            cls = ' class="lead"' if title == "概述" and not paragraphs_wrapped else ""
            paragraphs_wrapped = True
            blocks.append(f"<p{cls}>{block}</p>")
    return f"<section><h2>{html.escape(title)}</h2>{''.join(blocks)}</section>"


def render_report(title: str, preamble: list[str], sections: list[tuple[str, list[str]]], provenance=None) -> str:
    """Assemble the 章纸-style single-file HTML document."""
    seen_cites: set[int] = set()
    preamble_html = "".join(f"<p>{render_inline(line, seen_cites)}</p>" for line in preamble)
    body = preamble_html + "".join(
        render_section(section_title, lines, seen_cites, provenance) for section_title, lines in sections
    )
    shell = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header>
<div class="kicker">DEEP RESEARCH · 深度研究</div>
<h1>{html.escape(title)}</h1>
</header>
{body}
<footer>tri-research · 章纸版式 · 引用以报告原文为准</footer>
</main>
</body>
</html>
"""
    return shell


def build_provenance(session: str, state_dir: Path | None):
    """Provenance Note factory: ledger hits → note HTML per reference.

    Reuses the Evidence Audit's URL canonicalization — display layer, NOT
    an audit. Unknown session is an error; a missing ledger honestly marks
    every reference 台账未见. At most two `backend 「query」` groups are shown,
    more collapse into 等 N 处.
    """
    from evidence import StateStore, default_state_dir, evidence_path, load_records

    store = StateStore(state_dir if state_dir is not None else default_state_dir())
    store.load(session)  # unknown session → StateError → CLI ERROR: line
    hits: dict[str, list[tuple[str, str]]] = {}
    for record in load_records(evidence_path(store, session)):
        canonical = canonicalize_url(str(record.get("url", "")))
        if canonical:
            backend = str(record.get("backend") or record["kind"])
            hits.setdefault(canonical, []).append((backend, str(record.get("query", ""))))

    def note(number: int, canonical_url: str | None) -> str:
        if not canonical_url or canonical_url not in hits:
            return '<span class="prov prov-miss">台账未见</span>'
        pairs = sorted(set(hits[canonical_url]))
        shown = " · ".join(f"{backend}「{query}」" for backend, query in pairs[:2])
        extra = f" 等 {len(pairs)} 处" if len(pairs) > 2 else ""
        return f'<span class="prov">出处：{html.escape(shown)}{extra}</span>'

    return note


def default_output(report_path: Path) -> Path:
    return report_path.with_suffix(".html")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Output path (default: report path with .html)")
    parser.add_argument("--session", help="Evidence Ledger session id (enables Provenance Notes)")
    parser.add_argument("--state-dir", type=Path, default=None, help="State directory (default follows state_machine)")
    return parser


def run(args: argparse.Namespace) -> int:
    report_path = args.report.expanduser()
    if not report_path.is_file():
        raise RenderError(f"report does not exist: {report_path}")
    try:
        text = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RenderError(f"cannot read report: {exc}") from exc
    title, preamble, sections = split_sections(text)
    if not any(section_title == "参考文献" for section_title, _ in sections):
        raise RenderError(f"not a research report: no 参考文献 section in {report_path}")
    provenance = build_provenance(args.session, args.state_dir) if args.session else None
    document = render_report(title, preamble, sections, provenance)
    output_path = (args.output or default_output(report_path)).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8", newline="\n")
    print("OK:Report shell rendered")
    print(f"FILE:{output_path}")
    return 0


def main() -> int:
    args = create_parser().parse_args()
    try:
        return run(args)
    except (RenderError, StateError) as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
