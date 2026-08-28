"""Report Shell 渲染器契约测试：章纸骨架、零外链闸门、转义安全。"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _test_helpers import example_report, make_valid_report, register_report_evidence

SCRIPT = Path(__file__).parents[1] / "scripts" / "render_report.py"
STATE_MACHINE = Path(__file__).parents[1] / "scripts" / "state_machine.py"
EVIDENCE = Path(__file__).parents[1] / "scripts" / "evidence.py"


class RenderCliHarness:
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        command = [sys.executable, str(SCRIPT), *args]
        result = subprocess.run(command, capture_output=True, text=True)
        if ok and result.returncode != 0:
            self.fail(f"failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"unexpectedly succeeded: {command}\nstdout={result.stdout}")
        return result

    def make_report(self, name: str = "report.md", **kwargs) -> Path:
        report = self.tmp / name
        make_valid_report(report, **kwargs)
        return report

    def render(self, report: Path, *extra: str, ok: bool = True) -> Path:
        result = self.run_cli(str(report), *extra, ok=ok)
        if not ok:
            return result
        match = re.search(r"FILE:(.+)", result.stdout)
        self.assertIsNotNone(match, msg=result.stdout)
        return Path(match.group(1))


class RenderGoldenTests(RenderCliHarness, unittest.TestCase):
    def test_render_golden_example(self) -> None:
        # Render into the temp dir: never pollute the shared examples/ tree.
        output = self.render(example_report(), "-o", str(self.tmp / "golden.html"))
        self.assertTrue(output.is_file())
        html_text = output.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", html_text)
        self.assertIn("人工智能与劳动分配", html_text)

    def test_preamble_before_first_section_is_not_lost(self) -> None:
        """不丢字契约：H1 与第一个 ## 之间的导语（如 blockquote）必须上纸。"""
        report = self.make_report()
        # Prepend a blockquote line after the H1 of the generated report.
        text = report.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        lines.insert(1, "\n> **本报告为样例说明**，位于导语区。\n")
        report.write_text("".join(lines), encoding="utf-8", newline="")
        output = self.render(report)
        self.assertIn("本报告为样例说明", output.read_text(encoding="utf-8"))

    def test_default_output_is_sibling_html(self) -> None:
        report = self.make_report()
        output = self.render(report)
        self.assertEqual(output, report.with_suffix(".html"))

    def test_custom_output_flag(self) -> None:
        report = self.make_report()
        custom = self.tmp / "share" / "外壳.html"
        output = self.render(report, "-o", str(custom))
        self.assertEqual(output, custom)
        self.assertTrue(custom.is_file())

    def test_missing_refs_section_is_error(self) -> None:
        not_a_report = self.tmp / "not-a-report.md"
        not_a_report.write_text("# 随手笔记\n\n## 想法\n\n一些字\n", encoding="utf-8")
        result = self.run_cli(str(not_a_report), ok=False)
        self.assertIn("ERROR:", result.stderr)
        self.assertIn("参考文献", result.stderr)

    def test_missing_report_is_error(self) -> None:
        result = self.run_cli(str(self.tmp / "ghost.md"), ok=False)
        self.assertIn("ERROR:", result.stderr)


class RenderContractTests(RenderCliHarness, unittest.TestCase):
    def test_zero_external_resources(self) -> None:
        """零外链闸门：无 script/link/img，外链 href 只出现在参考文献锚点。"""
        output = self.render(self.make_report())
        html_text = output.read_text(encoding="utf-8")
        self.assertNotIn("<script", html_text)
        self.assertNotIn("<link", html_text)
        self.assertNotIn("<img", html_text)
        self.assertNotIn("url(http", html_text)
        # Every external href belongs to a reference URL anchor.
        external_hrefs = re.findall(r'href="(http[^"]+)"', html_text)
        report_urls = re.findall(r"https?://\S+", (self.tmp / "report.md").read_text(encoding="utf-8"))
        self.assertEqual(len(external_hrefs), len(report_urls))

    def test_anchor_links_both_ways(self) -> None:
        output = self.render(self.make_report())
        html_text = output.read_text(encoding="utf-8")
        self.assertIn('id="ref-1"', html_text)
        # Body cites jump to refs; the first cite of a ref carries a back-target id.
        self.assertIn('href="#ref-1"', html_text)
        self.assertIn('id="cite-1-first"', html_text)

    def test_report_content_is_escaped(self) -> None:
        report = self.tmp / "injection.md"
        make_valid_report(report)
        with report.open("a", encoding="utf-8") as handle:
            handle.write('\n注入行 <script>alert("x")</script> 与 <b>假标签</b> & 实体\n')
        output = self.render(report)
        html_text = output.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", html_text)
        self.assertIn("&lt;script&gt;", html_text)
        self.assertIn("&amp; 实体", html_text)

    def test_confidence_and_tier_marks(self) -> None:
        report = self.tmp / "marks.md"
        make_valid_report(report)
        with report.open("a", encoding="utf-8") as handle:
            handle.write("\n交叉验证的结论 [1][2] [高]。\n单一来源的说法 [3] [低]。\n")
        output = self.render(report)
        html_text = output.read_text(encoding="utf-8")
        self.assertIn('class="conf conf-high"', html_text)
        self.assertIn('class="conf conf-low"', html_text)
        self.assertIn('class="tier tier-1"', html_text)
        self.assertIn('class="tier tier-2"', html_text)

    def test_execution_table_rendered(self) -> None:
        output = self.render(self.make_report())
        html_text = output.read_text(encoding="utf-8")
        self.assertIn("<table>", html_text)
        self.assertIn("<thead>", html_text)
        self.assertIn("搜索源使用", html_text)
        self.assertNotIn("|------|", html_text)

    def test_external_markdown_degrades_to_escaped_paragraph(self) -> None:
        """契约外语法不丢字：列表/代码围栏降级为转义纯文本段落。"""
        report = self.tmp / "external.md"
        make_valid_report(report)
        with report.open("a", encoding="utf-8") as handle:
            handle.write("\n- 无序列表项\n- 另一项\n\n```python\nprint('hi')\n```\n")
        output = self.render(report)
        html_text = output.read_text(encoding="utf-8")
        self.assertIn("- 无序列表项", html_text)
        self.assertIn("```python", html_text)
        # html.escape escapes single quotes as &#x27;.
        self.assertIn("print(&#x27;hi&#x27;)", html_text)


class ProvenanceTests(RenderCliHarness, unittest.TestCase):
    """Provenance Note：台账出处小注（展示层语义，非审计）。"""

    def setUp(self) -> None:
        super().setUp()
        self.state_dir = self.tmp / "state"

    def run_state_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        command = [sys.executable, str(STATE_MACHINE), "--state-dir", str(self.state_dir), *args]
        result = subprocess.run(command, capture_output=True, text=True)
        if ok and result.returncode != 0:
            self.fail(f"state_machine failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def run_evidence_cli(self, *args: str) -> subprocess.CompletedProcess:
        command = [sys.executable, str(EVIDENCE), "--state-dir", str(self.state_dir), *args]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=f"evidence failed: {result.stderr}")
        return result

    def start_session(self, session: str) -> None:
        self.run_state_cli("--session", session, "start")

    def add_url(self, session: str, url: str, *, backend: str = "exa", query: str = "q") -> None:
        self.run_evidence_cli("--session", session, "add", "--backend", backend, "--query", query, "--url", url)

    def write_ref_report(self, name: str, refs: list[str]) -> Path:
        report = self.tmp / name
        report.write_text("# 测试主题\n\n## 参考文献\n" + "\n".join(refs) + "\n", encoding="utf-8")
        return report

    @staticmethod
    def ref_line(number: int, url: str) -> str:
        return f"[{number}] 作者 — 研究 — {url} — 2025 — 层级: 1 — 来源: Exa"

    def test_provenance_hits_and_misses(self) -> None:
        self.start_session("prov")
        report = self.make_report("prov.md")
        register_report_evidence(self.state_dir, "prov", report)
        # Ref 11 appended AFTER registration in a new refs section: honestly untraced.
        with report.open("a", encoding="utf-8") as handle:
            handle.write("\n## 参考文献\n\n[11] 作者 — 研究 — https://never-seen.cn/x — 2025 — 层级: 3 — 来源: Exa\n")
        output = self.render(report, "--session", "prov", "--state-dir", str(self.state_dir))
        html_text = output.read_text(encoding="utf-8")
        self.assertEqual(html_text.count('class="prov prov-miss"'), 1)
        self.assertIn("台账未见", html_text)
        self.assertIn("出处：test「test query」", html_text)

    def test_provenance_dedup_and_overflow(self) -> None:
        self.start_session("dedup")
        report = self.write_ref_report(
            "dedup.md",
            [self.ref_line(1, "https://a.cn/one")],
        )
        for backend, query in (("exa", "q1"), ("tavily", "q2"), ("exa", "q1"), ("serpapi", "q3")):
            self.add_url("dedup", "https://a.cn/one", backend=backend, query=query)
        output = self.render(report, "--session", "dedup", "--state-dir", str(self.state_dir))
        html_text = output.read_text(encoding="utf-8")
        # 3 distinct groups → show first 2 (sorted) + 等 3 处.
        self.assertIn("exa「q1」 · serpapi「q3」 等 3 处", html_text)

    def test_provenance_matches_tracking_params(self) -> None:
        self.start_session("tracking")
        report = self.write_ref_report(
            "tracking.md",
            [self.ref_line(1, "https://a.cn/one?utm_source=x&fbclid=y")],
        )
        self.add_url("tracking", "https://a.cn/one")
        output = self.render(report, "--session", "tracking", "--state-dir", str(self.state_dir))
        self.assertIn("出处：exa「q」", output.read_text(encoding="utf-8"))

    def test_no_session_means_no_provenance_dom(self) -> None:
        report = self.make_report("plain.md")
        output = self.render(report)
        self.assertNotIn('class="prov', output.read_text(encoding="utf-8"))

    def test_missing_ledger_marks_all_miss(self) -> None:
        self.start_session("no-ledger")
        report = self.make_report("no-ledger.md")
        output = self.render(report, "--session", "no-ledger", "--state-dir", str(self.state_dir))
        html_text = output.read_text(encoding="utf-8")
        self.assertEqual(html_text.count("台账未见"), 10)

    def test_unknown_session_is_error(self) -> None:
        report = self.make_report("ghost.md")
        result = self.run_cli(str(report), "--session", "ghost", "--state-dir", str(self.state_dir), ok=False)
        self.assertTrue(result.stderr.startswith("ERROR:"), msg=result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
