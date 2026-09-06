#!/usr/bin/env python3
"""验证 tri-research 报告的结构契约。"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

# Make sibling `_common` importable when this file is loaded via importlib
# (state_machine.py does the same in its own bootstrap).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import MIN_REPORT_SOURCES, now_iso, source_threshold  # noqa: E402
from _report_parse import Reference, citation_numbers, parse_report, section_of  # noqa: E402

CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
ENGLISH_WORD_RE = re.compile(r"\b[A-Za-z]{4,}\b")
# 条目级语言判定阈值：一条参考文献必须在作者/标题段（URL 之前）出现足够
# 的文字才计入对应语言。旧实现是 ANY 式检查——任何 4+ 字母英文词（如夹在
# 中文条目里的 "CCTV"）都会触发「有英文来源」，把纯中文报告放行。
MIN_CHINESE_CHARS_PER_ENTRY = 2
MIN_ENGLISH_WORDS_PER_ENTRY = 3
# 报告级英文门槛随报告规模缩放：真实报告（min_sources ≥ 10）要求至少 3 条
# 判定的真实英文条目（len // 3，下限 1）；小样本按比例放宽。
MIN_ENGLISH_ENTRIES = 3
# 执行情况「搜索源使用」行必须点名的后端（含可选源 Exa：未用也要写 0/跳过）
REQUIRED_SOURCE_BACKENDS = (
    "AnySearch",
    "SciVerse",
    "Exa",
    "SerpApi",
    "WebSearch",
)
SOURCE_USAGE_ROW_RE = re.compile(r"(?m)^\|?\s*搜索源使用\s*\|?\s*(.+?)\s*\|?\s*$")
# 契约要求的章节名（不含 "## " 前缀）：章节边界由 _report_parse 的锚定切分
# 决定，这里只列名单。
REQUIRED_HEADINGS = (
    "概述",
    "已有事实",
    "主要文献观点",
    "主要矛盾与冲突点",
    "未来研究方向",
    "参考文献",
    "执行情况",
)


class ReportValidationError(RuntimeError):
    """Raised when report validation or proof lifecycle fails."""


class ReportMissingError(ReportValidationError):
    """A proof points at a report file that can no longer be read."""


class ReportTamperedError(ReportValidationError):
    """The report bytes changed after the DONE proof recorded its hash."""


def normalize_topic(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def topic_in_title(expected_topic: str, title: str) -> bool:
    """True when ``title`` contains the confirmed ``expected_topic``.

    Substring matching on the separator-stripped normalized form lets a short
    ASCII topic match inside a longer Latin word ("AI" ⊂ "FAILURE"), so a
    report on the wrong subject was accepted. CJK topics have no word
    delimiters and keep plain normalized-substring matching; a pure-ASCII topic
    must additionally match at ASCII word boundaries in the case-folded title
    (arbitrary separators allowed between the topic's own words, since
    normalization drops them).
    """
    expected_normalized = normalize_topic(expected_topic)
    actual_normalized = normalize_topic(title)
    if not expected_normalized or expected_normalized not in actual_normalized:
        return False
    if not expected_normalized.isascii():
        return True
    words = re.findall(r"[a-z0-9]+", expected_topic.casefold())
    if not words:
        return True
    pattern = r"(?<![a-z0-9])" + r"[^a-z0-9]*".join(re.escape(word) for word in words) + r"(?![a-z0-9])"
    return re.search(pattern, title.casefold()) is not None


def _language_entries(references: list[Reference]) -> tuple[int, int]:
    """Count entries with real Chinese / English evidence, per entry.

    A reference counts as Chinese only if its author/title portion (before
    the URL) contains at least MIN_CHINESE_CHARS_PER_ENTRY CJK characters,
    and as English only if it contains at least MIN_ENGLISH_WORDS_PER_ENTRY
    English words of 4+ letters. This replaces the old ANY-style check where
    a stray Latin token such as "CCTV" inside an otherwise Chinese entry
    counted as English-language evidence.
    """
    chinese = english = 0
    for reference in references:
        content = reference.prefix
        if len(CHINESE_RE.findall(content)) >= MIN_CHINESE_CHARS_PER_ENTRY:
            chinese += 1
        if len(ENGLISH_WORD_RE.findall(content)) >= MIN_ENGLISH_WORDS_PER_ENTRY:
            english += 1
    return chinese, english


def validate(text: str, min_sources: int, *, expected_topic: str | None = None) -> list[str]:
    """结构门禁：只判定，语法一律读 _report_parse 的同一份解析结果。"""
    parsed = parse_report(text)
    errors: list[str] = []
    for heading in REQUIRED_HEADINGS:
        # 锚定行首的二级标题由 parse_report 负责：`### 概述` 不是章节，
        # 正文里出现的 "## 概述" 片段也不会被当成章节起点。
        if section_of(parsed, heading) is None:
            errors.append(f"缺少必需章节: ## {heading}")

    if expected_topic and not topic_in_title(expected_topic, parsed.title):
        errors.append(f"报告标题未包含确认主题: {expected_topic}")

    execution = section_of(parsed, "执行情况")
    execution_text = "\n".join(execution.lines) if execution else ""
    if execution_text:
        usage_match = SOURCE_USAGE_ROW_RE.search(execution_text)
        if not usage_match:
            errors.append("执行情况缺少搜索源使用行")
        else:
            usage_cell = usage_match.group(1)
            # Word-boundary match, not substring: "Example" contains "Exa", so a
            # row that never actually named Exa used to slip through the hard
            # gate. Reject a hit only when the name is glued to another ASCII
            # letter (a longer Latin word); adjacency to CJK / count text
            # ("Exa：0条" / "Exa未配置") still counts — those are the real report
            # formats, and \b would wrongly treat CJK as a word char.
            missing_backends = [
                name
                for name in REQUIRED_SOURCE_BACKENDS
                if not re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", usage_cell)
            ]
            if missing_backends:
                errors.append("执行情况搜索源使用未报告: " + " / ".join(missing_backends))

    references = {reference.number: reference for reference in parsed.references}
    if len(parsed.references) != len(references):
        errors.append("参考文献编号重复")
    if len(references) < min_sources:
        errors.append(f"至少需要 {min_sources} 条参考文献，实际 {len(references)} 条")

    if references:
        expected = list(range(1, max(references) + 1))
        actual = sorted(references)
        if actual != expected:
            errors.append(f"参考文献编号不连续: {actual}")

    reference_urls: dict[int, str] = {}
    for number, reference in sorted(references.items()):
        if reference.url is None:
            errors.append(f"参考文献 [{number}] 缺少 URL")
        elif reference.canonical_url is None:
            errors.append(f"参考文献 [{number}] URL 无效")
        else:
            reference_urls[number] = reference.canonical_url
        if reference.tier is None:
            errors.append(f"参考文献 [{number}] 缺少层级")
        if reference.source is None:
            errors.append(f"参考文献 [{number}] 缺少来源工具")

    unique_urls = set(reference_urls.values())
    if len(unique_urls) < len(reference_urls):
        duplicate_numbers = sorted(
            number for number, url in reference_urls.items() if list(reference_urls.values()).count(url) > 1
        )
        errors.append(f"参考文献 URL 重复: {duplicate_numbers}")
    if len(unique_urls) < min_sources:
        errors.append(f"至少需要 {min_sources} 个不重复来源，实际 {len(unique_urls)} 个")

    # 引用闭环的扫描范围与规则都在 seam 里：body 只到参考文献之前，围栏与行内
    # 代码里的 [n] 不算引用，**[1]** 仍然算。
    cited = citation_numbers(parsed.body_text)
    missing = sorted(cited - set(references))
    if missing:
        errors.append(f"正文引用无对应参考文献: {missing}")
    unused = sorted(set(references) - cited)
    if unused:
        errors.append(f"参考文献未在正文中引用: {unused}")

    # Check language coverage in the author/title portion (before URL), not metadata fields
    chinese_entries, english_entries = _language_entries(list(references.values()))
    if chinese_entries == 0:
        errors.append("报告缺少中文来源")
    if english_entries < min(MIN_ENGLISH_ENTRIES, len(references)):
        errors.append(
            f"报告英文证据不足: 仅 {english_entries} 条真实英文条目"
            f"（需至少 {min(MIN_ENGLISH_ENTRIES, len(references))} 条）"
        )

    forbidden = ("generated by AI", "由 AI 撰写", "AI 生成水印")
    for marker in forbidden:
        if marker.lower() in text.lower():
            errors.append(f"禁止标记: {marker}")
    return errors


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_and_build_proof(
    report_path: Path,
    min_sources: int,
    *,
    expected_topic: str,
) -> dict[str, Any]:
    """Validate a report file and build its ``report_validation`` proof.

    This is the path-level entry point for the report acceptance lifecycle:
    resolve/read the file, run the structural validator, compute the SHA-256,
    and return the proof dict that a DONE session must persist. A proof always
    records the confirmed topic string.
    """
    resolved_report = report_path.expanduser().resolve()
    if not resolved_report.is_file():
        raise ReportValidationError(f"report does not exist: {resolved_report}")
    try:
        # Read raw bytes: the SHA-256 proof must fingerprint the file as it
        # exists on disk. read_text() applies universal-newline translation,
        # so hashing its result would not match CRLF-authored files.
        report_bytes = resolved_report.read_bytes()
        report_text = report_bytes.decode("utf-8")
    except OSError as exc:
        raise ReportValidationError(f"cannot read report: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ReportValidationError(f"report is not valid UTF-8: {exc}") from exc
    errors = validate(report_text, min_sources, expected_topic=expected_topic)
    if errors:
        raise ReportValidationError("validation failed: " + "; ".join(errors))
    validated_at = now_iso()
    return {
        "path": str(resolved_report),
        "sha256": sha256_bytes(report_bytes),
        "topic": expected_topic,
        "min_sources": min_sources,
        "validated_at": validated_at,
    }


def require_complete_proof(proof: Any, session_id: str) -> None:
    """Compatibility shim: full DONE schema lives in ``proof.require_complete``.

    Kept so older imports / tests that still call this name keep working.
    Lazily imports ``proof`` to avoid a load-time cycle (``proof`` already
    imports this module). Re-raises as this module's ``ReportValidationError``
    so importlib dual-load callers still match ``isinstance`` against the
    loaded copy (same pattern as StateError in ``_common``).
    """
    from proof import ProofError, require_complete  # local: proof → validate_report

    try:
        require_complete(proof, session_id)
    except ProofError as exc:
        raise ReportValidationError(str(exc)) from exc


def verify_proof_integrity(proof: dict[str, Any]) -> None:
    """Recompute the report's SHA-256 and compare it against the stored proof.

    This is the verification half of the Report Validation lifecycle: DONE
    records a fingerprint via :func:`validate_and_build_proof`; re-running
    this catches any post-DONE edit to the report on disk. It reads raw
    bytes with the same recipe as proof-building — a text-mode read would
    mistranslate CRLF files and yield false mismatches (see fix 550874e).

    Raises ReportMissingError when the file cannot be read and
    ReportTamperedError when its current bytes no longer match the recorded
    hash. Both subclass ReportValidationError so callers that already handle
    that base type keep working unchanged.
    """
    raw_path = proof["path"]
    if not isinstance(raw_path, str):
        # proof.require_complete only rejects None/""; a hand-corrupted state
        # could hold a non-string. Guard so we keep the module's never-
        # traceback invariant instead of crashing inside Path().
        raise ReportMissingError(f"report not readable: proof path is not a string: {raw_path!r}")
    report_path = Path(raw_path).expanduser()
    try:
        report_bytes = report_path.read_bytes()
    except OSError as exc:
        raise ReportMissingError(f"report not readable: {report_path} ({exc})") from exc
    if sha256_bytes(report_bytes) != proof["sha256"]:
        raise ReportTamperedError(f"report changed after DONE: {report_path}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-sources", type=source_threshold, default=MIN_REPORT_SOURCES)
    parser.add_argument("--topic", help="确认的研究主题（必须出现在标题中）")
    return parser


def main() -> int:
    args = create_parser().parse_args()
    if not args.report.is_file():
        print(f"ERROR:报告不存在: {args.report}", file=sys.stderr)
        return 1
    errors = validate(
        args.report.read_text(encoding="utf-8"),
        args.min_sources,
        expected_topic=args.topic,
    )
    if errors:
        for error in errors:
            print(f"ERROR:{error}", file=sys.stderr)
        return 1
    print(f"OK:验证通过，{args.min_sources}+ 来源")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
