"""报告语法 seam 的契约测试：章节切分、参考文献字段、行内 span、URL 方言。

这里测的是「解析出来的形状」，不是「合不合格」——判定属 validate_report，
其回归留在 test_validate_report.py。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from _test_helpers import load_module

SCRIPT = Path(__file__).parents[1] / "scripts" / "_report_parse.py"
MODULE = load_module(SCRIPT, "_report_parse")


class UrlDialectTests(unittest.TestCase):
    def test_strip_url_punctuation_keeps_balanced_parens(self) -> None:
        self.assertEqual(
            MODULE.strip_url_punctuation("https://en.wikipedia.org/wiki/AI_(disambiguation)"),
            "https://en.wikipedia.org/wiki/AI_(disambiguation)",
        )
        self.assertEqual(
            MODULE.strip_url_punctuation("https://en.wikipedia.org/wiki/AI_(disambiguation)."),
            "https://en.wikipedia.org/wiki/AI_(disambiguation)",
        )
        self.assertEqual(
            MODULE.strip_url_punctuation("https://example.com/page)."),
            "https://example.com/page",
        )

    def test_strip_url_punctuation_handles_chinese_punctuation(self) -> None:
        for chinese_punct in ("。", "，", "；", "：", "）", "》", "」", "』", "”", "’"):
            with self.subTest(punct=chinese_punct):
                self.assertEqual(
                    MODULE.strip_url_punctuation(f"https://example.com/article{chinese_punct}"),
                    "https://example.com/article",
                )

    def test_trailing_chinese_quote_is_stripped_before_canonicalization(self) -> None:
        """URL_RE 是贪婪的 (\\S+)；尾部 」 必须在归一化前剥掉。"""
        self.assertEqual(
            MODULE.canonicalize_url(MODULE.strip_url_punctuation("https://publisher-one.org/one」")),
            "https://publisher-one.org/one",
        )

    def test_percent_encoding_in_path_is_normalized(self) -> None:
        """path 里的 %20 与空格必须归一到同一 canonical URL。

        否则报告写 %20、台账记空格（或反之）会被 Evidence Audit 当成两条不同
        URL，合法引用变 untraced、done 假失败。
        """
        encoded = MODULE.canonicalize_url("https://publisher.org/a%20b")
        self.assertEqual(encoded, MODULE.canonicalize_url("https://publisher.org/a b"))
        self.assertEqual(encoded, "https://publisher.org/a%20b")

    def test_plain_path_is_not_over_encoded(self) -> None:
        """归一不得过度编码普通 path（否则会弄坏已有合法引用）。"""
        self.assertEqual(
            MODULE.canonicalize_url("https://publisher.org/one/two"),
            "https://publisher.org/one/two",
        )
        self.assertEqual(
            MODULE.canonicalize_url("https://en.wikipedia.org/wiki/AI_(disambiguation)"),
            "https://en.wikipedia.org/wiki/AI_(disambiguation)",
        )


class CodeFenceTests(unittest.TestCase):
    def test_fence_mask_marks_block_including_delimiters(self) -> None:
        self.assertEqual(
            MODULE.fence_mask(["a", "```", "x [1]", "```", "b [2]"]),
            [False, True, True, True, False],
        )

    def test_unclosed_fence_is_not_a_block(self) -> None:
        """截断的报告不该把后面的正文连引用一起吞掉。"""
        self.assertEqual(MODULE.fence_mask(["a", "```", "x [1]"]), [False, False, False])

    def test_nested_fence_closes_only_with_equal_length(self) -> None:
        self.assertEqual(
            MODULE.fence_mask(["a", "````", "```", "b", "```", "````", "c"]),
            [False, True, True, True, True, True, False],
        )

    def test_strip_code_blocks_preserves_text_before_fence(self) -> None:
        """围栏长度不能被当成切片终点（历史上的解包顺序 bug）。"""
        self.assertEqual(
            MODULE.strip_code_blocks("before\n```\ncode\n```\nafter"),
            "before\n\nafter",
        )
        self.assertEqual(
            MODULE.strip_code_blocks("prefix text\n```python\narr[0]\n```\nsuffix [1]"),
            "prefix text\n\nsuffix [1]",
        )
        self.assertEqual(
            MODULE.strip_code_blocks("a\n````\nb\n```\nc\n```\nd\n````\ne"),
            "a\n\ne",
        )
        self.assertEqual(MODULE.strip_code_blocks("```\nonly block\n```"), "")
        self.assertEqual(
            MODULE.strip_code_blocks("no fences here [1]"),
            "no fences here [1]",
        )
        # Regression: old unpack used fence length as slice end → "before" became "bef"
        self.assertIn("before", MODULE.strip_code_blocks("before\n```\nx\n```\ny"))
        self.assertNotIn("arr[0]", MODULE.strip_code_blocks("see [1]\n```\narr[0]\n```\n"))


class InlineSpanTests(unittest.TestCase):
    def test_kinds_and_order(self) -> None:
        spans = MODULE.inline_spans("**结论** [1] 与 `arr[0]` [高]")
        self.assertEqual(
            [(kind, text) for kind, text in spans],
            [
                ("bold", "结论"),
                ("text", " "),
                ("cite", "1"),
                ("text", " 与 "),
                ("code", "`arr[0]`"),
                ("text", " "),
                ("conf", "高"),
            ],
        )

    def test_inline_code_bracket_is_not_a_citation(self) -> None:
        self.assertEqual(MODULE.citation_numbers("索引写法 `arr[7]` 不是引用"), set())

    def test_bold_wrapped_citation_still_counts(self) -> None:
        self.assertEqual(MODULE.citation_numbers("**[3]** 是唯一来源"), {3})

    def test_confidence_bracket_never_becomes_a_number(self) -> None:
        self.assertEqual(MODULE.citation_numbers("这条结论 [高]。"), set())

    def test_double_backtick_code_with_inner_backtick(self) -> None:
        self.assertEqual(MODULE.citation_numbers("``说 `[9]` 不算``"), set())


class ParseReportTests(unittest.TestCase):
    REPORT = """# 主题

> 导语，位于 H1 与第一个章节之间。

## 概述
观点 [1]。

### 参考文献
这段里的 `### 参考文献` 只是三级标题。

## 参考文献
[1] 作者 — 研究 — https://a.cn/one — 2025 — 层级: 1 — 来源: SciVerse, Exa

## 执行情况
| 项目 | 说明 |
|------|------|
| 报告位置 | ~/tri-research-reports/[9].md |
"""

    def setUp(self) -> None:
        self.parsed = MODULE.parse_report(self.REPORT)

    def test_level_three_heading_does_not_hijack_section_slice(self) -> None:
        titles = [section.title for section in self.parsed.sections]
        self.assertEqual(titles, ["概述", "参考文献", "执行情况"])
        self.assertEqual(self.parsed.title, "主题")

    def test_heading_before_first_section_becomes_preamble(self) -> None:
        self.assertEqual(self.parsed.preamble, ["> 导语，位于 H1 与第一个章节之间。"])

    def test_body_text_stops_at_first_reference_section(self) -> None:
        """执行情况表格里的 [9] 不是引用：参考文献之后的章节不进 body。"""
        self.assertNotIn("执行情况", self.parsed.body_text)
        self.assertEqual(MODULE.citation_numbers(self.parsed.body_text), {1})

    def test_reference_fields_are_split_without_losing_text(self) -> None:
        (reference,) = self.parsed.references
        self.assertEqual(reference.number, 1)
        self.assertEqual(reference.url, "https://a.cn/one")
        self.assertEqual(reference.canonical_url, "https://a.cn/one")
        self.assertEqual(reference.tier, "1")
        # 来源值停在逗号：后面的字段不能被吞进徽标。
        self.assertEqual(reference.source, "SciVerse")
        self.assertTrue(reference.prefix.startswith("作者 — 研究 — "))
        self.assertEqual(f"{reference.prefix}{reference.matched_url}{reference.suffix}", reference.entry)

    def test_missing_reference_section_is_reported_not_judged(self) -> None:
        parsed = MODULE.parse_report("# 主题\n\n## 概述\n一些字\n")
        self.assertFalse(parsed.references_present)
        self.assertEqual(parsed.references, [])
        self.assertIn("## 概述", parsed.body_text)

    def test_utf8_bom_does_not_shift_the_title(self) -> None:
        self.assertEqual(MODULE.parse_report("﻿" + self.REPORT).title, "主题")

    def test_section_of_returns_none_for_absent_section(self) -> None:
        self.assertIsNone(MODULE.section_of(self.parsed, "不存在"))
        self.assertEqual(MODULE.section_of(self.parsed, "执行情况").lines[0], "| 项目 | 说明 |")

    def test_repeated_reference_sections_each_keep_their_entries(self) -> None:
        text = (
            "# 主题\n\n## 参考文献\n[1] A — https://a.cn/1 — 层级: 1 — 来源: Exa\n"
            "\n## 附录\n附注\n\n## 参考文献\n[2] B — https://b.cn/2 — 层级: 2 — 来源: Exa\n"
        )
        parsed = MODULE.parse_report(text)
        ref_sections = [s for s in parsed.sections if s.title == "参考文献"]
        self.assertEqual([[r.number for r in s.references] for s in ref_sections], [[1], [2]])
        self.assertEqual([r.number for r in parsed.references], [1, 2])


class GrammarOwnershipTests(unittest.TestCase):
    """源码闸门：报告语法只能有一个家（沿用 test_host_helpers 的形制）。

    消费方再手抄一条正则，四份平行实现就会悄悄长回来——那时同一份报告又会
    按「谁在读」给出不同答案，正是这次收口要消灭的失效模式。
    """

    GRAMMAR_LITERALS = (
        r"^\[(\d+)]\s+(.+)$",  # REFERENCE_RE：一行一条参考文献
        r"https?://\S+",  # URL_RE：贪婪匹配后还要剥尾部标点
        "``(?:(?!``).)*?``",  # 双反引号行内代码：里面的 [n] 不是引用
        r"(?m)^(?=## )",  # SECTION_SPLIT_RE：章节从哪里断开
        r"^#\s+(.+?)\s*$",  # H1_RE：报告标题
    )

    def test_grammar_literals_exist_in_parse_module(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for literal in self.GRAMMAR_LITERALS:
            self.assertIn(literal, source, f"{literal!r} must stay home in _report_parse.py")

    def test_no_other_script_redefines_report_grammar(self) -> None:
        """枚举整个 scripts/ 目录，新文件也躲不过闸门。"""
        for path in sorted(SCRIPT.parent.glob("*.py")):
            if path.name == "_report_parse.py":
                continue
            source = path.read_text(encoding="utf-8")
            for literal in self.GRAMMAR_LITERALS:
                self.assertNotIn(
                    literal,
                    source,
                    f"{path.name} must import from _report_parse instead of hand-copying {literal!r}",
                )


if __name__ == "__main__":
    unittest.main()
