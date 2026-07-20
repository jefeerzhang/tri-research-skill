#!/usr/bin/env python3
"""Validate the structural contract of a tri-research Markdown report."""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REFERENCE_RE = re.compile(r"^\[(\d+)]\s+(.+)$", re.MULTILINE)
INLINE_RE = re.compile(r"\[(\d+)]")
URL_RE = re.compile(r"https?://\S+")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
ENGLISH_RE = re.compile(r"\b[A-Za-z]{4,}\b")
MIN_REPORT_SOURCES = 10
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
    # Fragments and tracking parameters are not distinct evidence sources.
    return urlunsplit((parsed.scheme.lower(), host, path, query, ""))


def validate(
    text: str, min_sources: int, *, expected_topic: str | None = None
) -> list[str]:
    errors: list[str] = []
    required_headings = ("## TL;DR", "## 参考文献", "## 搜索与降级状态")
    for heading in required_headings:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")

    if expected_topic:
        heading = H1_RE.search(text)
        expected_normalized = normalize_topic(expected_topic)
        actual_normalized = normalize_topic(heading.group(1)) if heading else ""
        if not expected_normalized or expected_normalized not in actual_normalized:
            errors.append(
                "report H1 does not contain the confirmed topic: " + expected_topic
            )

    references = {int(number): entry for number, entry in REFERENCE_RE.findall(text)}
    if len(references) < min_sources:
        errors.append(
            f"expected at least {min_sources} references, found {len(references)}"
        )

    if references:
        expected = list(range(1, max(references) + 1))
        actual = sorted(references)
        if actual != expected:
            errors.append(f"reference numbers are not consecutive: {actual}")

    reference_urls: dict[int, str] = {}
    for number, entry in sorted(references.items()):
        url_match = URL_RE.search(entry)
        if not url_match:
            errors.append(f"reference [{number}] has no URL")
        else:
            raw_url = url_match.group(0).rstrip(".,;:)]}>")
            canonical_url = canonicalize_url(raw_url)
            if canonical_url is None:
                errors.append(f"reference [{number}] has an invalid http/https URL")
            else:
                reference_urls[number] = canonical_url
        if not re.search(r"\bTier:\s*[123]\b", entry):
            errors.append(f"reference [{number}] has no valid Tier")
        if not re.search(r"\bFound by:\s*[^—\n]+", entry):
            errors.append(f"reference [{number}] has no Found by metadata")

    unique_urls = set(reference_urls.values())
    if len(unique_urls) < len(reference_urls):
        duplicate_numbers = sorted(
            number
            for number, url in reference_urls.items()
            if list(reference_urls.values()).count(url) > 1
        )
        errors.append(f"reference URLs are not unique: {duplicate_numbers}")
    if len(unique_urls) < min_sources:
        errors.append(
            f"expected at least {min_sources} unique reference URLs, found {len(unique_urls)}"
        )

    body = text.split("## 参考文献", 1)[0]
    cited = {int(number) for number in INLINE_RE.findall(body)}
    missing = sorted(cited - set(references))
    if missing:
        errors.append(f"inline citations have no reference entries: {missing}")
    unused = sorted(set(references) - cited)
    if unused:
        errors.append(f"reference entries are not cited in the body: {unused}")

    reference_entries = list(references.values())
    if reference_entries and not any(
        CHINESE_RE.search(entry) for entry in reference_entries
    ):
        errors.append("report has no Chinese-language reference")
    if reference_entries and not any(
        ENGLISH_RE.search(entry) for entry in reference_entries
    ):
        errors.append("report has no English-language reference")

    status_match = re.search(
        r"^## 搜索与降级状态\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if status_match and not re.search(
        r"\b(?:available|unavailable|quota_exhausted)\b", status_match.group("body")
    ):
        errors.append("search status section has no normalized channel status")

    forbidden = ("generated by AI", "由 AI 撰写", "AI 生成水印")
    for marker in forbidden:
        if marker.lower() in text.lower():
            errors.append(f"forbidden generation marker found: {marker}")
    return errors


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--min-sources", type=source_threshold, default=MIN_REPORT_SOURCES
    )
    parser.add_argument(
        "--topic", help="Confirmed research topic that must appear in H1"
    )
    return parser


def source_threshold(value: str) -> int:
    parsed = int(value)
    if parsed < MIN_REPORT_SOURCES:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_REPORT_SOURCES}")
    return parsed


def main() -> int:
    args = create_parser().parse_args()
    if not args.report.is_file():
        print(f"ERROR:report does not exist: {args.report}", file=sys.stderr)
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
    print(f"OK:validated {args.report} with at least {args.min_sources} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
