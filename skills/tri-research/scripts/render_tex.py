#!/usr/bin/env python3
"""Report -> XeLaTeX (-> PDF) 渲染器：把验收报告渲成书样单文件 PDF。

报告 md 是唯一真源；本脚本生成派生的 ``.tex``，并在检测到 xelatex 时编译成
``.pdf``。渲染遵循 ``references/report-format.md`` 契约内的结构（H1 标题、
7 个 ``## `` 章节、行内 ``[N]`` / 置信标签、单行参考文献、执行情况表格）；
契约外的 Markdown 降级为转义纯文本。

**drawio 框架图排除**：报告里内嵌的机制/结构图（``![...]`` 图片行）及其
``*图：...*`` 说明在生成 LaTeX 时一并**跳过**，因此 PDF 不含中间产物 drawio
框架图（与 ``report-format.md``「机制图（可选）」的约定一致）。

版式：内置 XeLaTeX + xeCJK 书样（5x8 英寸、思源/系统 CJK 字体可配、回退
Noto CJK），自包含、不依赖外部模板仓库。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from validate_report import H1_RE, REFERENCE_RE, URL_RE, _strip_url_punctuation  # noqa: E402

TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
SEP_ROW_RE = re.compile(r":?-{2,}:?")

# LaTeX 需转义的字符（URL 除外）。
_LATEX_TEX = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


class RenderError(RuntimeError):
    """The input is not renderable as a research report."""


def esc(text: str) -> str:
    """转义 LaTeX 特殊字符（用于正文/元数据，不用于 \\url{}）。"""
    return "".join(_LATEX_TEX.get(c, c) for c in text)


def inline(text: str) -> str:
    """先转义，再应用契约内行内标记（**加粗** / *斜体*）。"""
    escaped = esc(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", lambda m: r"\textbf{%s}" % m.group(1), escaped)
    escaped = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
        lambda m: r"\textit{%s}" % m.group(1),
        escaped,
    )
    return escaped


def strip_ref_meta(text: str) -> str:
    """去掉参考文献条目里的 ``层级: X`` / ``来源: Y`` / ``URL:`` 元数据前缀。

    来源值用贪婪 ``[^,，\\n]+`` 吞到逗号为止；不能用非贪婪 ``+?``，否则会与可选的
    ``,`` 配合、只匹配到来源名的前几个字符（如 ``Exa`` -> 剩 ``xa``）。
    """
    text = re.sub(r"\s*层级[:：]\s*[123]\s*,?\s*", " ", text)
    text = re.sub(r"\s*来源[:：]\s*[^,\n，]+\s*,?\s*", " ", text)
    text = re.sub(r"\s*URL[:：]\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def render_reference(number: int, entry: str) -> str:
    """一行参考文献 -> \\refitem{N}{作者, "标题", 出处, 年份. \\url{URL}}。"""
    url_match = URL_RE.search(entry)
    before = entry[: url_match.start()] if url_match else entry
    text = strip_ref_meta(before)
    if not text:
        text = strip_ref_meta(entry)
    parts = [esc(text)]
    if url_match:
        url = _strip_url_punctuation(url_match.group(0))
        if url:
            # Use \\url|...| so a literal } in the URL cannot close the argument early.
            # hyperref treats | as an alternate delimiter; brace form breaks on }.
            parts.append(r" \url|" + url + "|")
    return r"\refitem{%d}{%s}" % (number, "".join(parts))


def render_table(lines: list[str]) -> str:
    """连续的 ``| ... |`` 行 -> longtable（分隔行跳过）。"""
    rows: list[list[str]] = []
    for line in lines:
        if not TABLE_ROW_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(SEP_ROW_RE.fullmatch(c) for c in cells if c):
            continue
        rows.append(cells)
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    colspec = "p{0.95in}p{2.85in}" if ncols == 2 else "".join(["l"] * ncols)
    def _pad(row: list[str]) -> list[str]:
        if len(row) >= ncols:
            return row[:ncols]
        return row + [""] * (ncols - len(row))

    head, *body = rows
    out = [r"\begin{longtable}{@{}%s@{}}" % colspec, r"\toprule"]
    out.append(" & ".join(inline(c) for c in _pad(head)) + r" \\")
    out.append(r"\midrule")
    out.append(r"\endhead")
    for row in body:
        out.append(" & ".join(inline(c) for c in _pad(row)) + r" \\")
    out.append(r"\bottomrule")
    out.append(r"\end{longtable}")
    return "\n".join(out)


def render_section(title: str, lines: list[str]) -> str:
    """章节 body -> LaTeX。跳过 ``![...]`` 图片行（drawio 框架图）。"""
    if title == "参考文献":
        refs = [(int(number), entry) for number, entry in REFERENCE_RE.findall("\n".join(lines))]
        if not refs:
            raise RenderError("参考文献章节无有效条目")
        items = "\n\n".join(render_reference(n, e) for n, e in refs)
        return r"\section{%s}" % esc(title) + "\n\n" + items + "\n"

    blocks: list[str] = []
    table_lines: list[str] = []
    list_items: list[str] = []

    def flush_table() -> None:
        nonlocal table_lines
        if table_lines:
            blocks.append(render_table(table_lines))
            table_lines.clear()

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("\n".join([r"\begin{itemize}"] + list_items + [r"\end{itemize}"]))
            list_items.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # 跳过 drawio 框架图（![...]）及其 *图：...* 说明，避免 PDF 里悬空引用。
        if line.startswith("![") or line.startswith("*图"):
            continue
        if TABLE_ROW_RE.match(line):
            flush_list()
            table_lines.append(line)
            continue
        flush_table()
        if line.startswith("- "):
            flush_table()
            list_items.append(r"\item " + inline(line[2:]))
            continue
        flush_table()
        flush_list()
        blocks.append(inline(line))

    flush_table()
    flush_list()

    body = "\n\n".join(blocks)
    return r"\section{%s}" % esc(title) + ("\n\n" + body if body else "") + "\n"


def split_sections(text: str) -> tuple[str, list[str]]:
    """把报告拆成 (H1 标题, [(章节名, 行)...])。标题之前的内容按前言保留。"""
    heading = H1_RE.search(text)
    title = heading.group(1) if heading else ""
    sections: list[tuple[str, list[str]]] = []
    for part in re.split(r"(?m)^(?=## )", text):
        if not part.startswith("## "):
            continue
        title_line, _, body = part[3:].partition("\n")
        sections.append((title_line.strip(), body.splitlines()))
    return title, sections


def font_block(fonts_dir: Path | None) -> str:
    """CJK 字体设置：--fonts-dir 指向思源字体文件；否则回退系统/Noto CJK 字体名。"""
    if fonts_dir is not None:
        d = fonts_dir.as_posix().rstrip("/") + "/"
        return "\n".join(
            [
                r"\setmainfont[Path=%s]{SourceHanSerifCN-Regular.otf}" % d,
                r"\setCJKmainfont[Path=%s]{SourceHanSerifCN-Regular.otf}" % d,
                r"\setsansfont[Path=%s]{SourceHanSansCN-Medium.otf}" % d,
                r"\setCJKsansfont[Path=%s]{SourceHanSansCN-Medium.otf}" % d,
            ]
        )
    return "\n".join(
        [
            r"\setmainfont{Noto Serif CJK SC}",
            r"\setCJKmainfont{Noto Serif CJK SC}",
            r"\setsansfont{Noto Sans CJK SC}",
            r"\setCJKsansfont{Noto Sans CJK SC}",
        ]
    )


HEADER_FOOTER = r"""
\fancypagestyle{bodyrunning}{%
  \fancyhf{}%
  \fancyhead[LO]{\sffamily\fontsize{7.5}{9}\selectfont\color{SecondaryInk}%TITLE%}
  \fancyhead[RO]{\sffamily\fontsize{7.5}{9}\selectfont\color{SecondaryInk}\thepage}%
  \fancyhead[LE]{\sffamily\fontsize{7.5}{9}\selectfont\color{SecondaryInk}\thepage}%
  \fancyhead[RE]{\sffamily\fontsize{7.5}{9}\selectfont\color{SecondaryInk}%TITLE%}%
  \renewcommand{\headrulewidth}{0pt}%
  \renewcommand{\footrulewidth}{0pt}%
}
\pagestyle{bodyrunning}
"""


def build_document(title: str, sections: list[tuple[str, list[str]]], fonts_dir: Path | None) -> str:
    """组装 XeLaTeX 书样文档（自包含内置模板）。"""
    safe_title = esc(title)
    template = r"""% !TEX program = xelatex
% 由 tri-research render_tex.py 生成（派生产物，报告 md 为唯一真源）
\documentclass[10pt,twoside,openany]{book}
\usepackage{geometry}
\geometry{paperwidth=5in,paperheight=8in,top=0.7in,bottom=0.7in,inner=0.5in,outer=0.5in,headheight=10pt,headsep=20pt,footskip=25.2pt}
\addtolength{\textheight}{-12pt}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{setspace}
\defaultfontfeatures{Ligatures=TeX}
__FONTS__
\usepackage{fancyhdr}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{enumitem}
\usepackage[unicode=true,hidelinks]{hyperref}
\definecolor{PrimaryInk}{HTML}{161618}
\definecolor{SecondaryInk}{HTML}{5C5C62}
\definecolor{AccentRed}{HTML}{B23A48}
\hypersetup{pdftitle={__TITLE__},pdfauthor={Deep Research}}
\color{PrimaryInk}
\setcounter{secnumdepth}{0}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlength{\topskip}{10pt}
\renewcommand{\baselinestretch}{1.25}
\clubpenalty=10000
\widowpenalty=10000
\raggedbottom
\makeatletter
\renewcommand{\section}{\@startsection{section}{1}{\z@}%
  {-1.8ex \@plus -1ex \@minus -.2ex}{1ex \@plus .2ex}%
  {\sffamily\fontsize{12.5}{16}\selectfont\color{PrimaryInk}}}
\makeatother
\setlist[itemize]{leftmargin=1.2em,itemsep=3pt,topsep=4pt,parsep=0pt}
\setlist[itemize,1]{label=\textcolor{AccentRed}{\rule[0.4ex]{0.5em}{0.5em}}}
__HEADER__
\newcommand{\refitem}[2]{\par\noindent\hangindent=1.5em\hangafter=1\textcolor{AccentRed}{\sffamily\bfseries [#1]}\hspace{0.4em}#2\par\vspace{3pt}}
\begin{document}
__COVER__
__BODY__
\end{document}
"""
    cover = (
        r"\begin{titlepage}\thispagestyle{empty}\vspace*{0.6in}"
        r"{\sffamily\fontsize{8}{10}\selectfont\color{SecondaryInk} DEEP RESEARCH REPORT}\\[4pt]"
        r"{\color{AccentRed}\rule{1.2in}{2.5pt}}\\[18pt]"
        r"{\sffamily\fontsize{19}{24}\selectfont\color{PrimaryInk} " + safe_title + r"}\\[16pt]"
        r"{\rmfamily\fontsize{9}{12}\selectfont\color{SecondaryInk} AI 深度研究 · 多源证据}\\[4pt]"
        r"{\rmfamily\fontsize{7.5}{10}\selectfont\color{SecondaryInk} 排版：XeLaTeX · 5×8 英寸}"
        r"\end{titlepage}\setcounter{page}{1}"
    )
    body = "\n\n".join(render_section(t, lines) for t, lines in sections)
    return (
        template.replace("__FONTS__", font_block(fonts_dir))
        .replace("__TITLE__", safe_title)
        .replace("__HEADER__", HEADER_FOOTER.replace("%TITLE%", safe_title))
        .replace("__COVER__", cover)
        .replace("__BODY__", body)
    )


def find_xelatex() -> str | None:
    """依次探测：环境变量 -> TinyTeX/MiKTeX 常见路径 -> PATH。

    Windows TinyTeX 必须走 ``%APPDATA%``（不能拼 ``C:\\Users\\{USERNAME}``）：
    配置目录名经常与 USERNAME 不一致（中文显示名、域账户等）。
    """
    for var in ("TRI_RESEARCH_XELATEX", "XELATEX"):
        val = os.environ.get(var)
        if val and Path(val).exists():
            return val
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "TinyTeX" / "bin" / "windows" / "xelatex.exe")
    home = Path.home()
    for rel in (("Library", "TinyTeX", "bin"), (".TinyTeX", "bin")):
        base = home.joinpath(*rel)
        if base.is_dir():
            candidates.extend(sorted(base.glob("*/xelatex")))
            candidates.extend(sorted(base.glob("*/xelatex.exe")))
    if sys.platform.startswith("win"):
        candidates.append(Path(r"C:\Program Files\MiKTeX\miktex\bin\x64\xelatex.exe"))
    for path in candidates:
        if path.is_file():
            return str(path)
    return shutil.which("xelatex")


def compile(engine: str, tex_path: Path, out_dir: Path) -> int:
    """跑两遍 xelatex（交叉引用/页码），返回退出码。"""
    for _ in range(2):
        proc = subprocess.run(
            [engine, "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(out_dir), tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout[-3000:] + "\n" + proc.stderr[-1500:] + "\n")
            return proc.returncode
    return 0


def default_output(report_path: Path) -> Path:
    return report_path.with_suffix(".tex")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="输出 .tex 路径 (default: 报告同目录 .tex)")
    parser.add_argument("--fonts-dir", type=Path, default=None, help="思源字体目录 (含 SourceHanSerifCN-Regular.otf 等)")
    parser.add_argument("--no-compile", action="store_true", help="只生成 .tex，不自动编译 PDF")
    parser.add_argument("--engine", default=None, help="xelatex 路径/命令 (default: 自动探测)")
    return parser


def run(args: argparse.Namespace) -> int:
    report_path = args.report.expanduser()
    if not report_path.is_file():
        raise RenderError(f"report does not exist: {report_path}")
    try:
        text = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RenderError(f"cannot read report: {exc}") from exc
    title, sections = split_sections(text)
    if not any(section_title == "参考文献" for section_title, _ in sections):
        raise RenderError(f"not a research report: no 参考文献 section in {report_path}")
    output_path = (args.output or default_output(report_path)).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = build_document(title, sections, args.fonts_dir.expanduser() if args.fonts_dir else None)
    output_path.write_text(document, encoding="utf-8", newline="\n")
    print("OK:Report tex rendered")
    print(f"FILE:{output_path}")
    if args.no_compile:
        return 0
    engine = args.engine or find_xelatex()
    if not engine:
        print("WARN:xelatex not found; .tex written but PDF not compiled (set --engine or install TeX)")
        return 0
    pdf_path = output_path.with_suffix(".pdf")
    print(f"INFO:compiling with {engine}")
    rc = compile(engine, output_path, output_path.parent)
    if rc != 0:
        print(f"ERROR:xelatex failed (rc={rc}); check the log; .tex kept", file=sys.stderr)
        return rc
    print("INFO:Report PDF rendered")
    print(f"FILE:{pdf_path}")
    return 0


def main() -> int:
    args = create_parser().parse_args()
    try:
        return run(args)
    except RenderError as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
