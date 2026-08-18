"""Shared test fixtures for tri-research scripts."""
from __future__ import annotations

from pathlib import Path


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
