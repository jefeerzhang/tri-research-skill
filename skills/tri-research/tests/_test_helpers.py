"""Shared test fixtures for tri-research scripts."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

REQUIRED_SDK_STUBS = Path(__file__).resolve().parent / "_stubs" / "required_sdks"


def required_backend_cli_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Env for subprocess CLIs that call ``start``: fake keys + stub SDKs.

    Production has no escape hatch (ADR-0006); tests supply importable stub
    packages on PYTHONPATH and dummy keys so K+S passes without real SDKs.
    """
    env = dict(base if base is not None else os.environ)
    env["EXA_API_KEY"] = env.get("EXA_API_KEY") or "test-exa-key"
    env["SCIVERSE_API_TOKEN"] = env.get("SCIVERSE_API_TOKEN") or "test-sciverse-token"
    stub = str(REQUIRED_SDK_STUBS)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = stub + (os.pathsep + existing if existing else "")
    return env


def patch_required_backends(module) -> mock._patch:
    """No-op the Required Backend gate on an in-process loaded state_machine."""
    return mock.patch.object(module, "require_required_backends", lambda: None)


def report_reference_urls(report_path: Path) -> list[str]:
    """Raw reference URLs from a report's 参考文献 section, in order, deduped."""
    text = Path(report_path).read_text(encoding="utf-8")
    refs = text.split("## 参考文献", 1)[1] if "## 参考文献" in text else ""
    next_section = re.search(r"(?m)^## ", refs)
    if next_section:
        refs = refs[: next_section.start()]
    urls: list[str] = []
    for match in re.finditer(r"https?://\S+", refs):
        # Same trailing-punctuation strip as validate_report._strip_url_punctuation.
        url = match.group(0).rstrip(".,;:。，；：）》」』”’\"'")
        if url not in urls:
            urls.append(url)
    return urls


def register_report_evidence(state_dir: Path, session: str, report_path: Path, *, backend: str = "test") -> None:
    """Register every reference URL of `report` as seen evidence (test seam).

    `done` runs the Evidence Audit hard gate: report references must trace
    to the session's evidence ledger. Tests that drive a session to a
    successful done use this to simulate a Lead that registered its search
    results. In-process (no subprocess) so StateStore-level tests can use it.
    """
    evidence = load_module(
        Path(__file__).resolve().parents[1] / "scripts" / "evidence.py",
        "evidence_test_helper",
    )
    records = [
        {
            "kind": "seen",
            "ts": "2026-01-01T00:00+00:00",
            "backend": backend,
            "query": "test query",
            "url": url,
        }
        for url in report_reference_urls(report_path)
    ]
    evidence.append_records(evidence.StateStore(Path(state_dir)), session, records)


def make_valid_report(
    path: Path,
    *,
    topic: str = "人工智能与劳动分配",
    source_count: int = 10,
) -> None:
    inline = "".join(f"[{i}]" for i in range(1, source_count + 1))
    refs = []
    for i in range(1, source_count + 1):
        if i % 2 == 0:
            refs.append(
                f"[{i}] 作者{i} — 中文研究 — https://source-{i}.cn/article-{i} — 2024 — 层级: 2 — 来源: AnySearch"
            )
        else:
            refs.append(
                f"[{i}] Author — English study — https://source-{i}.org/paper-{i} — 2025 — 层级: 1 — 来源: SciVerse"
            )
    path.write_text(
        f"""# {topic}

## 概述
概述内容{inline}。

## 已有事实
事实[1][2]。

## 主要文献观点
观点[3][4]。

## 主要矛盾与冲突点
矛盾[5]。

## 未来研究方向
方向[6]。

## 参考文献
{chr(10).join(refs)}

## 执行情况

| 项目 | 说明 |
|------|------|
| 执行流程 | 预检 → 搜索 → 综合 → 验证 |
| 子代理派发 | 否 |
| 搜索源使用 | AnySearch: {source_count}条 / SciVerse: 0条 / Exa: 0条 / SerpApi: 0条 / WebSearch: 0条 |
| 耗时 | 3.0 分钟 |
| 报告位置 | ~/tri-research-reports/{path.name} |
""",
        encoding="utf-8",
    )


def load_module(script: Path, module_name: str):
    """Load a Python file as a module via importlib."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, str(script))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def example_report() -> Path:
    """Locate the canonical sample report in either repo or installed layout."""
    skill_examples = Path(__file__).resolve().parents[1] / "examples" / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"
    if skill_examples.is_file():
        return skill_examples
    repo_examples = Path(__file__).resolve().parents[3] / "examples" / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"
    return repo_examples
