"""Contract tests for the Report -> XeLaTeX renderer (``scripts/render_tex.py``).

Covers: 7-section structure, drawio framework image exclusion (``![...]`` line
and its ``*图：...*`` caption are dropped), reference metadata (层级/来源)
stripped and no partial-match residue, execution table -> longtable.
Compilation is NOT required (needs xelatex); these test ``--no-compile``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT / "scripts")
import sys  # noqa: E402

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from render_tex import (  # noqa: E402
    build_document,
    create_parser,
    find_xelatex,
    render_reference,
    render_table,
    strip_ref_meta,
)

REPORT = """# 测试主题：机制与证据

## 概述

一段概述文字 [1]。

![机制示意图](mech_diagram.png)

*图：测试框架图的说明文字。*

## 已有事实

- 是一条事实 [1]。 [高]

## 主要文献观点

观点文字。

## 主要矛盾与冲突点

矛盾文字。

## 未来研究方向

方向文字。

## 参考文献

[1] Author, "Title", Journal, 2025, 层级: 1, 来源: Exa, URL: https://doi.org/10.1000/example
[2] 王三; 李四, "中文标题", 出版社, 2026, 层级: 2, 来源: AnySearch, URL: https://example.com/a

## 执行情况

| 项目 | 说明 |
|------|------|
| 搜索源使用 | Exa: 2 |
| 报告位置 | ~/reports/x.md |
"""


def run_no_compile(report: str) -> tuple[str, Path]:
    """渲染一份合成报告（--no-compile），返回 (tex 文本, 输出路径)。"""
    with tempfile.TemporaryDirectory() as tmps:
        tmp = Path(tmps)
        report_path = tmp / "report.md"
        report_path.write_text(report, encoding="utf-8")
        tex_path = tmp / "report.tex"
        args = create_parser().parse_args(
            [str(report_path), "-o", str(tex_path), "--no-compile"]
        )
        from render_tex import run

        rc = run(args)
        assert rc == 0, "render_tex.run returned non-zero"
        return tex_path.read_text(encoding="utf-8"), tex_path


class TestRenderTex(unittest.TestCase):
    def test_generated_tex_has_sections_but_no_drawio_image(self) -> None:
        tex, _ = run_no_compile(REPORT)
        self.assertIn(r"\section{概述}", tex)
        self.assertIn(r"\section{参考文献}", tex)
        self.assertIn(r"\begin{longtable}", tex)
        # drawio framework image + image alt + its caption must be excluded
        self.assertNotIn("includegraphics", tex)
        self.assertNotIn("mech_diagram", tex)
        self.assertNotIn(".png", tex)
        self.assertNotIn("机制示意图", tex)
        self.assertNotIn("测试框架图的说明文字", tex)

    def test_reference_metadata_stripped(self) -> None:
        tex, _ = run_no_compile(REPORT)
        self.assertIn(
            r'\refitem{1}{Author, "Title", Journal, 2025 \url|https://doi.org/10.1000/example|}',
            tex,
        )
        self.assertIn(
            r'\refitem{2}{王三; 李四, "中文标题", 出版社, 2026 \url|https://example.com/a|}',
            tex,
        )
        self.assertNotIn("来源:", tex)
        self.assertNotIn("层级:", tex)

    def test_strip_ref_meta_no_partial_residue(self) -> None:
        # 回归：贪婪吞到逗号，不能把 "Exa" 匹配成 "E" 留下 "xa"。
        cleaned = strip_ref_meta('"T", J, 2025, 层级: 1, 来源: Exa, URL: https://x')
        self.assertNotIn("xa", cleaned)
        self.assertIn('"T", J, 2025', cleaned)
        cleaned2 = strip_ref_meta('"T", J, 2025, 层级: 2, 来源: AnySearch, URL: https://x')
        self.assertNotIn("nySearch", cleaned2)

    def test_build_document_has_cover_and_refitem(self) -> None:
        title, sections = _split(REPORT)
        doc = build_document(title, sections, None)
        self.assertIn("DEEP RESEARCH REPORT", doc)
        self.assertIn(r"\newcommand{\refitem}", doc)
        self.assertIn(r"\end{document}", doc)

    def test_render_table_pads_short_rows_to_header_width(self) -> None:
        tex = render_table(["| a | b |", "|---|---|", "| onlyone |"])
        self.assertIn(r"onlyone &  \\", tex)

    def test_render_reference_keeps_url_with_closing_brace(self) -> None:
        line = render_reference(1, 'A, "T", 2020, URL: https://ex.com/a}b')
        self.assertIn(r"\url|https://ex.com/a}b|", line)
        self.assertNotIn(r"\url{https://ex.com/a}", line)


class FindXelatexTests(unittest.TestCase):
    """Seam: find_xelatex() — discover engine via env / known installs / PATH."""

    def test_discovers_tinytex_under_appdata_even_when_username_differs(self) -> None:
        # Repro: Chinese Windows often has USERNAME≠profile folder
        # (e.g. USERNAME=张剑, profile=jefeer). Hard-coding
        # C:\\Users\\{USERNAME}\\... misses a real TinyTeX install.
        with tempfile.TemporaryDirectory() as tmps:
            appdata = Path(tmps) / "Roaming"
            engine = appdata / "TinyTeX" / "bin" / "windows" / "xelatex.exe"
            engine.parent.mkdir(parents=True)
            engine.write_bytes(b"")
            env = {
                "APPDATA": str(appdata),
                "USERNAME": "NotTheProfileName",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                for key in ("TRI_RESEARCH_XELATEX", "XELATEX"):
                    os.environ.pop(key, None)
                with mock.patch("render_tex.shutil.which", return_value=None):
                    found = find_xelatex()
            self.assertEqual(found, str(engine))

    def test_discovers_tinytex_under_home_dot_tinytex(self) -> None:
        with tempfile.TemporaryDirectory() as tmps:
            home = Path(tmps) / "home"
            engine = home / ".TinyTeX" / "bin" / "x86_64-linux" / "xelatex"
            engine.parent.mkdir(parents=True)
            engine.write_bytes(b"")
            with mock.patch.dict(os.environ, {}, clear=False):
                for key in ("TRI_RESEARCH_XELATEX", "XELATEX", "APPDATA"):
                    os.environ.pop(key, None)
                with mock.patch.object(Path, "home", return_value=home):
                    with mock.patch("render_tex.shutil.which", return_value=None):
                        found = find_xelatex()
            self.assertEqual(found, str(engine))


def _split(report: str) -> tuple[str, list[tuple[str, list[str]]]]:
    from render_tex import split_sections

    return split_sections(report)


if __name__ == "__main__":
    unittest.main()
