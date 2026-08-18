#!/usr/bin/env python3
"""验证 tri-research 报告的结构契约。"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Make sibling `_common` importable when this file is loaded via importlib
# (state_machine.py does the same in its own bootstrap).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import MIN_REPORT_SOURCES, now_iso, source_threshold  # noqa: E402

REFERENCE_RE = re.compile(r"^\[(\d+)]\s+(.+)$", re.MULTILINE)
INLINE_RE = re.compile(r"\[(\d+)]")
URL_RE = re.compile(r"https?://\S+")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
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
SOURCE_USAGE_ROW_RE = re.compile(
    r"(?m)^\|?\s*搜索源使用\s*\|?\s*(.+?)\s*\|?\s*$"
)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
RESERVED_HOSTS = {"example.com", "example.net", "example.org", "localhost"}
RESERVED_SUFFIXES = (".example", ".invalid", ".localhost", ".test")


class ReportValidationError(RuntimeError):
    """Raised when report validation or proof lifecycle fails."""


def normalize_topic(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _strip_url_punctuation(url: str) -> str:
    # ASCII + common CJK trailing punctuation that URL_RE (\S+) may swallow
    # from surrounding prose (period, comma, Chinese quotes/brackets, etc.).
    url = url.rstrip(".,;:。，；：）》」』”’\"'")
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    while url and url[-1] in pairs and url.count(url[-1]) > url.count(pairs[url[-1]]):
        url = url[:-1]
    return url


def canonicalize_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    host = parsed.hostname.lower()
    if host in RESERVED_HOSTS or host.endswith(RESERVED_SUFFIXES):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ):
        return None
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in TRACKING_QUERY_KEYS
        ),
        doseq=True,
    )
    return urlunsplit((parsed.scheme.lower(), host, path, query, ""))


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks, correctly handling nested fences.

    A code fence of N backticks is only closed by another run of exactly N
    backticks — inner fences with fewer backticks are part of the block
    content, not closing delimiters (CommonMark spec).
    """
    fence_re = re.compile(r"`{3,}")
    result: list[str] = []
    stack: list[tuple[int, int]] = []
    pos = 0
    for match in fence_re.finditer(text):
        start = match.start()
        end = match.end()
        length = end - start
        if not stack:
            stack.append((length, start))
        elif stack[-1][0] == length:
            _open_length, open_start = stack.pop()
            if not stack:
                result.append(text[pos:open_start])
                pos = end
        else:
            stack.append((length, start))
    if pos == 0:
        return text
    result.append(text[pos:])
    return "".join(result)


def _language_entries(reference_entries: list[str]) -> tuple[int, int]:
    """Count entries with real Chinese / English evidence, per entry.

    A reference counts as Chinese only if its author/title portion (before
    the URL) contains at least MIN_CHINESE_CHARS_PER_ENTRY CJK characters,
    and as English only if it contains at least MIN_ENGLISH_WORDS_PER_ENTRY
    English words of 4+ letters. This replaces the old ANY-style check where
    a stray Latin token such as "CCTV" inside an otherwise Chinese entry
    counted as English-language evidence.
    """
    chinese = english = 0
    for entry in reference_entries:
        content = entry.split("http")[0]
        if len(CHINESE_RE.findall(content)) >= MIN_CHINESE_CHARS_PER_ENTRY:
            chinese += 1
        if len(ENGLISH_WORD_RE.findall(content)) >= MIN_ENGLISH_WORDS_PER_ENTRY:
            english += 1
    return chinese, english


def validate(
    text: str, min_sources: int, *, expected_topic: str | None = None
) -> list[str]:
    text = text.lstrip("\ufeff")
    errors: list[str] = []
    required_headings = (
        "## 概述",
        "## 已有事实",
        "## 主要文献观点",
        "## 主要矛盾与冲突点",
        "## 未来研究方向",
        "## 参考文献",
        "## 执行情况",
    )
    for heading in required_headings:
        # 锚定行首的二级标题，避免把 "### 概述" 这类三级标题（"## 概述"
        # 的子串）误判为存在，也避免把正文中出现的 "## 概述" 片段当章节。
        if not re.search(r"(?m)^" + re.escape(heading) + r"(?:\s|$)", text):
            errors.append(f"缺少必需章节: {heading}")

    if expected_topic:
        heading = H1_RE.search(text)
        expected_normalized = normalize_topic(expected_topic)
        actual_normalized = normalize_topic(heading.group(1)) if heading else ""
        if not expected_normalized or expected_normalized not in actual_normalized:
            errors.append(f"报告标题未包含确认主题: {expected_topic}")

    execution_text = text.split("## 执行情况", 1)[1] if "## 执行情况" in text else ""
    if execution_text:
        next_section = re.search(r"(?m)^## ", execution_text)
        if next_section:
            execution_text = execution_text[: next_section.start()]
        usage_match = SOURCE_USAGE_ROW_RE.search(execution_text)
        if not usage_match:
            errors.append("执行情况缺少搜索源使用行")
        else:
            usage_cell = usage_match.group(1)
            missing_backends = [
                name for name in REQUIRED_SOURCE_BACKENDS if name not in usage_cell
            ]
            if missing_backends:
                errors.append(
                    "执行情况搜索源使用未报告: " + " / ".join(missing_backends)
                )

    references_text = text.split("## 参考文献", 1)[1] if "## 参考文献" in text else ""
    # 截止到下一个二级标题：## 参考文献 之后的章节（执行情况、附录等）
    # 里的 "[n] ..." 行不是参考文献条目，不能被 REFERENCE_RE 扫到。
    next_section = re.search(r"(?m)^## ", references_text)
    if next_section:
        references_text = references_text[: next_section.start()]
    ref_matches = REFERENCE_RE.findall(references_text)
    references = {int(number): entry for number, entry in ref_matches}
    if len(ref_matches) != len(references):
        errors.append("参考文献编号重复")
    if len(references) < min_sources:
        errors.append(f"至少需要 {min_sources} 条参考文献，实际 {len(references)} 条")

    if references:
        expected = list(range(1, max(references) + 1))
        actual = sorted(references)
        if actual != expected:
            errors.append(f"参考文献编号不连续: {actual}")

    reference_urls: dict[int, str] = {}
    for number, entry in sorted(references.items()):
        url_match = URL_RE.search(entry)
        if not url_match:
            errors.append(f"参考文献 [{number}] 缺少 URL")
        else:
            raw_url = _strip_url_punctuation(url_match.group(0))
            canonical_url = canonicalize_url(raw_url)
            if canonical_url is None:
                errors.append(f"参考文献 [{number}] URL 无效")
            else:
                reference_urls[number] = canonical_url
        if not re.search(r"层级[:：]\s*[123]", entry):
            errors.append(f"参考文献 [{number}] 缺少层级")
        if not re.search(r"来源[:：]\s*[^\n]+", entry):
            errors.append(f"参考文献 [{number}] 缺少来源工具")

    unique_urls = set(reference_urls.values())
    if len(unique_urls) < len(reference_urls):
        duplicate_numbers = sorted(
            number
            for number, url in reference_urls.items()
            if list(reference_urls.values()).count(url) > 1
        )
        errors.append(f"参考文献 URL 重复: {duplicate_numbers}")
    if len(unique_urls) < min_sources:
        errors.append(f"至少需要 {min_sources} 个不重复来源，实际 {len(unique_urls)} 个")

    body = text.split("## 参考文献", 1)[0]
    body = _strip_code_blocks(body)
    # 行内代码里的 [n] 不是引用，移除后再扫描。
    # 围栏代码块已被 _strip_code_blocks 剥离，这里只剩行内代码。
    # 先处理双反引号（可含内嵌单反引号），再处理单反引号。
    body = re.sub(r"``.+?``", "", body, flags=re.DOTALL)
    body = re.sub(r"`[^`\n]+`", "", body)
    cited = {int(number) for number in INLINE_RE.findall(body)}
    missing = sorted(cited - set(references))
    if missing:
        errors.append(f"正文引用无对应参考文献: {missing}")
    unused = sorted(set(references) - cited)
    if unused:
        errors.append(f"参考文献未在正文中引用: {unused}")

    reference_entries = list(references.values())
    # Check language coverage in the author/title portion (before URL), not metadata fields
    chinese_entries, english_entries = _language_entries(reference_entries)
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
        report_text = resolved_report.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReportValidationError(f"cannot read report: {exc}") from exc
    errors = validate(report_text, min_sources, expected_topic=expected_topic)
    if errors:
        raise ReportValidationError("validation failed: " + "; ".join(errors))
    validated_at = now_iso()
    return {
        "path": str(resolved_report),
        "sha256": sha256_bytes(report_text.encode("utf-8")),
        "topic": expected_topic,
        "min_sources": min_sources,
        "validated_at": validated_at,
    }


def require_complete_proof(proof: Any, session_id: str) -> None:
    """Assert that a DONE state carries a complete report_validation proof.

    Raises ReportValidationError — never KeyError — so callers can translate
    it to a CLI-friendly error without a traceback.
    """
    required = ("path", "sha256", "min_sources")
    if not isinstance(proof, dict):
        raise ReportValidationError(
            f"phase=DONE but report_validation is missing for session "
            f"{session_id!r} — state file is corrupt"
        )
    missing = [key for key in required if key not in proof or proof[key] in (None, "")]
    if missing:
        raise ReportValidationError(
            f"phase=DONE but report_validation is incomplete for session "
            f"{session_id!r} (missing: {', '.join(missing)}) — state file is corrupt"
        )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--min-sources", type=source_threshold, default=MIN_REPORT_SOURCES
    )
    parser.add_argument(
        "--topic", help="确认的研究主题（必须出现在标题中）"
    )
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

