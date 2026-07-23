#!/usr/bin/env python3
"""验证 tri-research 报告的结构契约。"""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Make sibling `_common` importable when this file is loaded via importlib
# (state_machine.py does the same in its own bootstrap).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import MIN_REPORT_SOURCES, source_threshold  # noqa: E402

REFERENCE_RE = re.compile(r"^\[(\d+)]\s+(.+)$", re.MULTILINE)
INLINE_RE = re.compile(r"\[(\d+)]")
URL_RE = re.compile(r"https?://\S+")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
ENGLISH_RE = re.compile(r"\b[A-Za-z]{4,}\b")
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


def normalize_topic(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _strip_url_punctuation(url: str) -> str:
    url = url.rstrip(".,;:。，；：）》")
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
        if heading not in text:
            errors.append(f"缺少必需章节: {heading}")

    if expected_topic:
        heading = H1_RE.search(text)
        expected_normalized = normalize_topic(expected_topic)
        actual_normalized = normalize_topic(heading.group(1)) if heading else ""
        if not expected_normalized or expected_normalized not in actual_normalized:
            errors.append(f"报告标题未包含确认主题: {expected_topic}")

    references_text = text.split("## 参考文献", 1)[1] if "## 参考文献" in text else ""
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
        if not re.search(r"层级:\s*[123]", entry):
            errors.append(f"参考文献 [{number}] 缺少层级")
        if not re.search(r"来源:\s*[^\n]+", entry):
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
    cited = {int(number) for number in INLINE_RE.findall(body)}
    missing = sorted(cited - set(references))
    if missing:
        errors.append(f"正文引用无对应参考文献: {missing}")
    unused = sorted(set(references) - cited)
    if unused:
        errors.append(f"参考文献未在正文中引用: {unused}")

    reference_entries = list(references.values())
    # Check language coverage in the author/title portion (before URL), not metadata fields
    content_parts = [entry.split("http")[0] for entry in reference_entries]
    if content_parts and not any(CHINESE_RE.search(part) for part in content_parts):
        errors.append("报告缺少中文来源")
    if content_parts and not any(ENGLISH_RE.search(part) for part in content_parts):
        errors.append("报告缺少英文来源")

    forbidden = ("generated by AI", "由 AI 撰写", "AI 生成水印")
    for marker in forbidden:
        if marker.lower() in text.lower():
            errors.append(f"禁止标记: {marker}")
    return errors


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

