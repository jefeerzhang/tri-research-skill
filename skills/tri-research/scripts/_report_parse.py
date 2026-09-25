#!/usr/bin/env python3
"""报告语法的唯一之家（Report Parse）：章节模型、参考文献字段、行内 span、URL 方言。

验收器（validate_report）、LaTeX/PDF 渲染器（render_tex）、溯源对账
（evidence audit）和测试夹具读的是同一份契约 ``references/report-format.md``，
因此它们必须穿过同一个 seam 解析报告，而不是各写一遍正则。本 module 只回答
「这份文本长什么样」，不回答「合不合格」——判定与排版都留在调用方。

依赖方向单向：本 module 只用标准库，不被 scripts/ 下任何 module 反向依赖。

一处边界值得写明：`canonicalize_url` 对保留域、私有 IP、带凭据的 URL 返回
`None`，看着像判定，其实是「比对键」定义的一部分——什么算同一个来源、什么根本
不成其为来源，验收器与溯源对账必须共用同一个答案。本 module 依然不判断报告合
不合格（那是 validate_report），也不判断引用有没有台账命中（那是 evidence audit）。
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from typing import NamedTuple
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

# --------------------------------------------------------------------------- #
# 语法常量：契约里出现的每一种标记，只在这里定义一次
# --------------------------------------------------------------------------- #

REFERENCES_TITLE = "参考文献"
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# 章节切分锚定行首的 `## `：`### 三级标题` 不是章节边界，也不能劫持切片。
SECTION_SPLIT_RE = re.compile(r"(?m)^(?=## )")
REFERENCE_RE = re.compile(r"^\[(\d+)]\s+(.+)$", re.MULTILINE)
URL_RE = re.compile(r"https?://\S+")
# 来源值取到下一个字段边界（半/全角逗号）或行尾：契约里 `来源:` 后面还跟着
# `URL:`，取到行尾会把 URL 一起吞进徽标。
TIER_RE = re.compile(r"层级[:：]\s*([123])")
SOURCE_RE = re.compile(r"来源[:：]\s*([^\n,，]+)")
FENCE_RE = re.compile(r"`{3,}")
_SPAN_RE = re.compile(
    r"(?P<code>``(?:(?!``).)*?``|`[^`\n]+`)"
    r"|(?P<bold>\*\*(?:(?!\*\*).)*?\*\*)"
    r"|(?P<conf>\[(?P<conf_v>[高中低])\])"
    r"|(?P<cite>\[(?P<cite_n>\d+)\])",
    re.DOTALL,
)

TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
RESERVED_HOSTS = {"example.com", "example.net", "example.org", "localhost"}
RESERVED_SUFFIXES = (".example", ".invalid", ".localhost", ".test")
URL_TRAILING_PUNCTUATION = ".,;:。，；：）》」』”’\"'"


# --------------------------------------------------------------------------- #
# URL 方言
# --------------------------------------------------------------------------- #


def strip_url_punctuation(url: str) -> str:
    """剥掉 ``URL_RE`` (\\S+) 从周围正文里误吞的尾部标点。"""
    url = url.rstrip(URL_TRAILING_PUNCTUATION)
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    while url and url[-1] in pairs and url.count(url[-1]) > url.count(pairs[url[-1]]):
        url = url[:-1]
    return url


def canonicalize_url(value: str) -> str | None:
    """归一化到「同一来源 = 同一字符串」；不可信或非法 URL 返回 None。

    Evidence Audit 与出处小注都以此为唯一比对键，两侧必须同方言。
    """
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
        (parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    # Percent-encoding normalization (RFC 3986): decode then re-encode so that
    # "%20" vs a literal space — or any differently-escaped/cased form —
    # collapse to one canonical path. Without this the Evidence Audit treated
    # the same URL as two, turning a legal citation untraced and failing done.
    # safe keeps pchar sub-delims so ordinary paths are not over-encoded.
    path = quote(unquote(path), safe="/:@!$&'()*+,;=").rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value_part)
            for key, value_part in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
        ),
        doseq=True,
    )
    return urlunsplit((parsed.scheme.lower(), host, path, query, ""))


# --------------------------------------------------------------------------- #
# 行内语法：一次解析，验收器与外壳共读
# --------------------------------------------------------------------------- #


class Span(NamedTuple):
    """一段行内文本及其类型：text / code / bold / cite / conf。

    ``code`` 的 text 含反引号本身（原样保留，不丢字），关键是它的 kind
    不是 cite——行内代码里的 ``arr[0]`` 永远不是引用。
    """

    kind: str
    text: str


def inline_spans(text: str) -> list[Span]:
    """把一行（或一段）文本切成带类型的 span；``[N]`` 只有在代码外才是引用。"""
    spans: list[Span] = []
    position = 0
    for match in _SPAN_RE.finditer(text):
        if match.start() > position:
            spans.append(Span("text", text[position : match.start()]))
        if match.group("code") is not None:
            spans.append(Span("code", match.group(0)))
        elif match.group("bold") is not None:
            spans.append(Span("bold", match.group(0)[2:-2]))
        elif match.group("conf") is not None:
            spans.append(Span("conf", match.group("conf_v")))
        else:
            spans.append(Span("cite", match.group("cite_n")))
        position = match.end()
    if position < len(text):
        spans.append(Span("text", text[position:]))
    return spans


def _fence_length(line: str) -> int | None:
    match = FENCE_RE.search(line)
    return match.end() - match.start() if match else None


def fence_mask(lines: Iterable[str]) -> list[bool]:
    """逐行标注「这行属不属于围栏代码块」，定界行本身也算。

    全仓库唯一的围栏规则在这里：N 个反引号开的围栏只被恰好 N 个反引号的行
    关闭——更少是块内容的一部分，不是闭合符（CommonMark）。整段扫下来仍未
    闭合的围栏不算代码块：报告写到一半截断时，正文里的引用不该被整段吞掉。
    """
    lines = list(lines)
    mask = [False] * len(lines)
    open_length: int | None = None
    start = 0
    for index, line in enumerate(lines):
        length = _fence_length(line)
        if open_length is None:
            if length:
                open_length, start = length, index
            continue
        if length != open_length:
            continue
        for position in range(start, index + 1):
            mask[position] = True
        open_length = None
    return mask


def strip_code_blocks(text: str) -> str:
    """移除围栏代码块，每块折叠成一个空行（判定见 :func:`fence_mask`）。"""
    lines = text.split("\n")
    kept: list[str] = []
    inside = False
    for line, masked in zip(lines, fence_mask(lines)):
        if masked:
            if not inside:
                kept.append("")
                inside = True
            continue
        inside = False
        kept.append(line)
    return "\n".join(kept)


def citation_numbers(text: str) -> set[int]:
    """正文里真实引用的编号：代码内的 ``[N]`` 不算，``**[N]**`` 仍算。"""

    def walk(spans: list[Span]) -> set[int]:
        numbers: set[int] = set()
        for span in spans:
            if span.kind == "cite":
                numbers.add(int(span.text))
            elif span.kind == "bold":
                numbers.update(walk(inline_spans(span.text)))
        return numbers

    return walk(inline_spans(strip_code_blocks(text)))


# --------------------------------------------------------------------------- #
# 文档模型
# --------------------------------------------------------------------------- #


class Reference(NamedTuple):
    """一条参考文献行的结构化视图（字段缺失为 None，判定留给调用方）。"""

    number: int
    entry: str
    prefix: str  # URL 之前的作者/标题段
    suffix: str  # URL 之后的剩余文本
    matched_url: str  # URL_RE 原始匹配（可能带尾部标点）；无 URL 时为 ""
    url: str | None  # 剥尾部标点后的 URL
    canonical_url: str | None
    tier: str | None
    source: str | None


class Section(NamedTuple):
    title: str
    lines: list[str]
    references: list[Reference]


class ParsedReport(NamedTuple):
    title: str
    preamble: list[str]
    sections: list[Section]
    references: list[Reference]  # 各参考文献章节条目的拼接
    body_text: str  # 第一个参考文献章节之前的原文（引用闭环只扫这一段）
    references_present: bool


def section_of(parsed: ParsedReport, title: str) -> Section | None:
    """按标题取一个章节；不存在返回 None（缺不缺章节是调用方的判定）。"""
    return next((section for section in parsed.sections if section.title == title), None)


def parse_reference(number: int, entry: str) -> Reference:
    """解析单行参考文献条目（``[N]`` 已剥掉）：字段缺失为 None，不判定对错。

    只拿到「编号 + 一行原文」的消费方（如排版层）用它，而不是自己再搜一遍
    URL —— 那正是四份平行实现的长法。
    """
    url_match = URL_RE.search(entry)
    matched_url = url_match.group(0) if url_match else ""
    prefix = entry[: url_match.start()] if url_match else entry
    suffix = entry[url_match.end() :] if url_match else ""
    stripped = strip_url_punctuation(matched_url) if matched_url else ""
    url = stripped or None
    tier_match = TIER_RE.search(entry)
    source_match = SOURCE_RE.search(entry)
    return Reference(
        number=number,
        entry=entry,
        prefix=prefix,
        suffix=suffix,
        matched_url=matched_url,
        url=url,
        canonical_url=canonicalize_url(url) if url else None,
        tier=tier_match.group(1) if tier_match else None,
        source=source_match.group(1).strip() if source_match else None,
    )


def parse_report(text: str) -> ParsedReport:
    """把一份研究报告文本解析成章节、参考文献字段与可扫引用的 body。

    BOM 与行首锚定在这里统一处理：所有读者看到的章节边界都是同一套。
    ``sections`` 收全部章节（外壳要按原顺序上纸），``body_text`` 只到第一个
    ``## 参考文献`` 之前（引用闭环的范围）。没有 ``## 参考文献`` 章节时
    ``references`` 为空、``references_present`` 为 False——「缺章节算不算错」
    属判定，不在解析层。
    """
    text = text.lstrip("\ufeff")
    parts = SECTION_SPLIT_RE.split(text)
    head = parts[0]
    heading = H1_RE.search(head)
    title = heading.group(1) if heading else ""
    preamble = [stripped for line in head.splitlines() if (stripped := line.strip()) and not stripped.startswith("# ")]

    sections: list[Section] = []
    body_parts = [head]
    references_present = False
    for part in parts[1:]:
        title_line, _, body = part[3:].partition("\n")
        section_title = title_line.strip()
        lines = body.splitlines()
        if section_title == REFERENCES_TITLE:
            references_present = True
            sections.append(
                Section(
                    section_title,
                    lines,
                    [parse_reference(int(number), entry) for number, entry in REFERENCE_RE.findall(part)],
                )
            )
            continue
        sections.append(Section(section_title, lines, []))
        if not references_present:
            # 参考文献之后的章节（执行情况、附录）里也有 "[n] ..." 行，
            # 那是表格与附注，不是作者引用的证据——扫它会伪造缺失引用。
            body_parts.append(part)

    return ParsedReport(
        title=title,
        preamble=preamble,
        sections=sections,
        references=[reference for section in sections for reference in section.references],
        body_text="".join(body_parts),
        references_present=references_present,
    )
