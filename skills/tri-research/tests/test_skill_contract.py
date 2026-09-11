from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from _test_helpers import load_module

ROOT = Path(__file__).parents[1]
REPO_ROOT = ROOT.parents[1]

# 产品锁（2026-09-11 R-A）：点名名单恰好这六源，不得增删改名。
LOCKED_USAGE_ROSTER = (
    "AnySearch",
    "SciVerse",
    "Exa",
    "SerpApi",
    "Tavily",
    "WebSearch",
)
SOURCE_NAME_RE = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in LOCKED_USAGE_ROSTER) + r")\b")


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.subagent = (ROOT.parent / "research-subagent" / "SKILL.md").read_text(encoding="utf-8")
        _root_readme_path = REPO_ROOT / "README.md"
        cls.root_readme = _root_readme_path.read_text(encoding="utf-8") if _root_readme_path.exists() else ""
        cls.test_prompts = (ROOT / "test-prompts.json").read_text(encoding="utf-8")

    def test_version_reconciliation(self) -> None:
        """跨文件版本对账:全部发布通道与 SKILL.md frontmatter 单一真源对齐。

        历史教训:6.3.1 时 marketplace.json 曾漂移到 6.0.0;此前本测试为
        硬编码版本字符串,且未覆盖 marketplace.json / citations SKILL.md。
        现改为从 frontmatter 动态读取,发版时无需改测试;[Unreleased] 期间
        CHANGELOG 最新「已发布」条目仍应等于 frontmatter 版本。
        """
        m = re.search(r'^version:\s*"([^"]+)"', self.skill, re.MULTILINE)
        self.assertIsNotNone(m, "tri-research SKILL.md frontmatter 缺少 version")
        v = m.group(1)

        self.assertIn(f'version: "{v}"', self.subagent, "research-subagent SKILL.md 版本漂移")
        citations = (ROOT.parent / "citations" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f'version: "{v}"', citations, "citations SKILL.md 版本漂移")
        self.assertIn(f"当前版本：`{v}`", self.readme, "skill README 当前版本漂移")
        if self.root_readme:
            self.assertIn(f"version-{v}", self.root_readme, "根 README 徽章版本漂移")
        self.assertIn(f'"version": "{v}"', self.test_prompts, "test-prompts.json 版本漂移")

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(v, marketplace["metadata"]["version"], "marketplace.json metadata.version 漂移")

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        rel = re.search(r"^##\s+\[([^\]]+)\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$", changelog, re.MULTILINE)
        self.assertIsNotNone(rel, "CHANGELOG 缺少已发布版本条目")
        self.assertEqual(v, rel.group(1), "CHANGELOG 最新发布版本与 frontmatter 不一致")

    def test_six_source_table_present(self) -> None:
        for name in ("AnySearch", "Tavily", "SciVerse", "Exa", "SerpApi", "WebSearch"):
            self.assertIn(name, self.skill)
            self.assertIn(name, self.readme)
            if self.root_readme:
                self.assertIn(name, self.root_readme)
        self.assertIn("六个搜索后端", self.skill)
        self.assertIn("六个搜索后端", self.readme)

    def test_skill_is_concise(self) -> None:
        self.assertLessEqual(len(self.skill.splitlines()), 450)

    def test_subagent_is_concise(self) -> None:
        self.assertLessEqual(len(self.subagent.splitlines()), 120)

    def test_citation_format_documented(self) -> None:
        # 硬门禁清单里的引用行字段锚点（模板本体在 references/report-format.md）
        self.assertIn("层级:", self.skill)
        self.assertIn("来源:", self.skill)

    def test_chinese_first(self) -> None:
        self.assertNotIn("## TL;DR", self.skill)
        self.assertNotIn("## Summary", self.skill)

    def test_source_allocation(self) -> None:
        self.assertIn("AnySearch", self.skill)
        self.assertIn("SciVerse", self.skill)
        self.assertIn("Exa", self.skill)
        self.assertIn("SerpApi", self.skill)
        self.assertIn("Tavily", self.skill)
        self.assertIn("WebSearch", self.skill)

    def test_usage_roster_hard_gate_cannot_drift(self) -> None:
        """ADR-0009 R-A：SKILL 硬门禁点名名单与 validate_report.USAGE_ROSTER 不得漂移。

        一侧改名/删名（文档六源、代码五源曾是审计 P0-1）必须让 CI 红。
        """
        validator = load_module(ROOT / "scripts" / "validate_report.py", "validate_report_contract")
        roster = tuple(validator.USAGE_ROSTER)
        self.assertEqual(roster, LOCKED_USAGE_ROSTER)
        self.assertIs(validator.REQUIRED_SOURCE_BACKENDS, validator.USAGE_ROSTER)

        gate_line = next(
            (ln for ln in self.skill.splitlines() if "搜索源使用" in ln and "点名" in ln),
            "",
        )
        self.assertTrue(gate_line, "SKILL 硬门禁缺少「搜索源使用」点名条款")
        named = frozenset(SOURCE_NAME_RE.findall(gate_line))
        self.assertEqual(
            named,
            frozenset(LOCKED_USAGE_ROSTER),
            f"SKILL 硬门禁源名与 USAGE_ROSTER 漂移: {gate_line}",
        )
        self.assertIn("0/跳过", gate_line)
        self.assertIn("ADR-0009", gate_line)

        report_format = (ROOT / "references" / "report-format.md").read_text(encoding="utf-8")
        self.assertNotIn("五名称", report_format)
        self.assertNotIn("Tavily 可并入说明", report_format)
        format_usage = next(
            (ln for ln in report_format.splitlines() if "搜索源使用" in ln),
            "",
        )
        self.assertTrue(format_usage, "report-format.md 缺少搜索源使用行")
        self.assertEqual(
            frozenset(SOURCE_NAME_RE.findall(format_usage)),
            frozenset(LOCKED_USAGE_ROSTER),
            f"report-format 搜索源使用行与 USAGE_ROSTER 漂移: {format_usage}",
        )

        readme_usage = next(
            (ln for ln in self.readme.splitlines() if "搜索源使用行" in ln),
            "",
        )
        self.assertTrue(readme_usage, "skill README 缺少搜索源使用行")
        self.assertEqual(
            frozenset(SOURCE_NAME_RE.findall(readme_usage)),
            frozenset(LOCKED_USAGE_ROSTER),
            f"skill README 搜索源使用行与 USAGE_ROSTER 漂移: {readme_usage}",
        )

        adr = (REPO_ROOT / "docs" / "adr" / "0009-源覆盖硬门禁单一名单.md").read_text(encoding="utf-8")
        self.assertIn("R-A", adr)
        for name in LOCKED_USAGE_ROSTER:
            self.assertIn(name, adr)

        self.assertNotIn("五名称", self.skill)
        self.assertNotIn("五名称", self.readme)

    def test_exa_is_required_tier_across_docs(self) -> None:
        """ADR-0001 把 Exa 提升为 required；各处文档表格/引导不得再标可选。

        合约测试此前只查六源名字（test_six_source_table_present /
        test_source_allocation），不查档位，于是 skill README / runtime-adapters
        把 Exa 悄悄留成「可选」也没人拦。
        """
        runtime_adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        docs = (
            ("skill", self.skill),
            ("readme", self.readme),
            ("root_readme", self.root_readme),
            ("runtime_adapters", runtime_adapters),
        )
        for name, blob in docs:
            if not blob:
                continue
            # 任何点名 Exa 且带档位词的表格行，必须是必选/required，不得是可选/optional。
            for line in blob.splitlines():
                if "Exa" in line and "|" in line and any(t in line for t in ("必选", "可选", "required", "optional")):
                    self.assertTrue(
                        ("必选" in line or "required" in line) and not ("可选" in line or "optional" in line),
                        msg=f"{name}: Exa 档位漂移（应为必选/required）: {line}",
                    )
            self.assertNotIn("Exa 是可选", blob, msg=name)

    def test_serpapi_is_required_tier_across_docs(self) -> None:
        """ADR-0007：SerpApi 升为 required（Key + 探活）；各处文档不得再标可选/静默跳过。"""
        runtime_adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        docs = (
            ("skill", self.skill),
            ("readme", self.readme),
            ("root_readme", self.root_readme),
            ("runtime_adapters", runtime_adapters),
        )
        for name, blob in docs:
            if not blob:
                continue
            for line in blob.splitlines():
                if (
                    "SerpApi" in line
                    and "|" in line
                    and any(t in line for t in ("必选", "可选", "required", "optional"))
                ):
                    self.assertTrue(
                        ("必选" in line or "required" in line) and not ("可选" in line or "optional" in line),
                        msg=f"{name}: SerpApi 档位漂移（应为必选/required）: {line}",
                    )
            self.assertNotIn("SerpApi 是可选", blob, msg=name)
            # 静默跳过与 required 矛盾，文档不得再把 SerpApi 说成会静默跳过。
            self.assertNotIn("SerpApi 静默跳过", blob, msg=name)

    def test_google_scholar_is_indirect_serpapi_only_for_hss(self) -> None:
        """Scholar 是 SerpApi 的间接能力；仅人文社科强制至少一轮 google_scholar。"""
        self.assertIn("google_scholar", self.skill)
        self.assertIn("人文社科", self.skill)
        self.assertIn("Google Scholar", self.skill)
        self.assertIn("STEM", self.skill)  # STEM 主题不强制 google_scholar
        # 不得宣称 Scholar 是独立后端，或无差别地让所有主题强制。
        self.assertNotIn("Google Scholar 是独立", self.skill)

    def test_required_backends_have_no_degrade_escape(self) -> None:
        """ADR-0006：文档不得再暗示无 Exa/SciVerse 仍可开跑。"""
        forbidden = (
            "用户明确要求降级",
            "同时尝试无 API 模式",
            "必选源未配置 → 提示用户配置，同时尝试",
        )
        for name, blob in (
            ("skill", self.skill),
            ("readme", self.readme),
            ("root_readme", self.root_readme),
            ("subagent", self.subagent),
        ):
            if not blob:
                continue
            for phrase in forbidden:
                self.assertNotIn(phrase, blob, msg=f"{name} still allows required degrade: {phrase!r}")
        self.assertIn("硬门禁", self.skill)
        self.assertIn("ADR-0006", self.skill)
        self.assertIn("ADR-0007", self.skill)
        self.assertIn("required_backends", (ROOT / "scripts" / "state_machine.py").read_text(encoding="utf-8"))
        # SerpApi 也在 required 门禁内（Key + 探活，ADR-0007），不是可选源。
        gate = (ROOT / "scripts" / "required_backends.py").read_text(encoding="utf-8")
        self.assertIn("SERPAPI_KEY", gate)

    def test_skill_does_not_claim_env_only_keys(self) -> None:
        """SKILL 曾写「API key 只读环境变量」，但 KeyProvider 实为 cli > env > .env。

        实现（_search_registry.KeyProvider + Backend.env_file，ADR-0004）早就吃
        本地 `.env`；文档再说「只读环境变量」会误导用户以为 .env 不生效。
        """
        self.assertNotIn("只读环境变量", self.skill)
        self.assertIn("`.env`", self.skill)

    def test_anysearch_guide_has_real_validation_command(self) -> None:
        """首次使用引导表 AnySearch 的验证列曾是占位符「验证命令」，须给可运行命令。

        其他行（Exa/SciVerse/Tavily）都给了具体命令，AnySearch 行不能留占位符。
        """
        guide_row = next(
            ln for ln in self.skill.splitlines() if ln.startswith("| **AnySearch**") and "npx skills add" in ln
        )
        cells = [c.strip() for c in guide_row.split("|")]
        validation_cell = cells[3]  # ['', 源, 安装, 验证, 必要性, '']
        self.assertNotIn("验证命令", validation_cell)
        self.assertIn("`", validation_cell)

    def test_subagent_uses_only_allowed_sources(self) -> None:
        self.assertIn("AnySearch", self.subagent)
        self.assertIn("SciVerse", self.subagent)
        self.assertIn("Exa", self.subagent)
        self.assertNotIn("SerpApi", self.subagent)

    def test_lead_uses_anysearch_when_no_subagent(self) -> None:
        # Lead Agent should be able to use AnySearch directly
        self.assertIn("Lead Agent + 子代理", self.skill)
        # AnySearch must be mandatory for all agents
        self.assertIn("必选搜索源", self.skill)
        # Fallback chain must be documented
        self.assertIn("fallback", self.skill.lower())

    def test_search_execution_spec(self) -> None:
        # Search execution spec must be documented
        self.assertIn("搜索执行规范", self.skill)
        # Bilingual requirement - must be prominent (leading words only;
        # sentence-level wording is free to evolve)
        self.assertIn("中英双补", self.skill)
        self.assertIn("全源覆盖", self.skill)
        # Full source coverage per dimension; both AnySearch and SciVerse mandatory
        self.assertIn("必选搜索源", self.skill)
        # SciVerse must have a bilingual usage example
        self.assertIn("semantic_search", self.skill)

    def test_report_format_disclosed_to_reference(self) -> None:
        # 格式契约下放到 references/report-format.md；SKILL.md 保留 context pointer，
        # 七章节锚点改在 reference 上断言。
        self.assertIn("references/report-format.md", self.skill)
        reference = (ROOT / "references" / "report-format.md").read_text(encoding="utf-8")
        for section in (
            "## 概述",
            "## 已有事实",
            "## 主要文献观点",
            "## 主要矛盾与冲突点",
            "## 未来研究方向",
            "## 参考文献",
            "## 执行情况",
        ):
            self.assertIn(section, reference)
        self.assertIn("层级:", reference)
        self.assertIn("来源:", reference)

    def test_anysearch_3_compatible(self) -> None:
        self.assertIn("get_sub_domains", self.subagent)
        self.assertIn("runtime.conf", self.subagent)

    def test_sciverse_python_sdk_not_mcp(self) -> None:
        # v6.0.0 起 SciVerse 走 Python SDK 必选路径
        self.assertIn("SciVerse 调用规范", self.skill)
        self.assertIn("pip install sciverse", self.skill)
        self.assertIn("AgentToolsClient", self.skill)
        self.assertIn("SCIVERSE_API_TOKEN", self.skill)
        # 禁止项:不应包含 SciVerse 工具调用形式 (e.g. mcp__sciverse__semantic_search)
        self.assertNotIn("mcp__sciverse__semantic_search", self.skill)
        self.assertNotIn("mcp__sciverse__search_papers", self.skill)
        self.assertNotIn("mcp__sciverse__read_content", self.skill)
        # 必含 "Python SDK" 作为必选路径明示
        self.assertIn("Python SDK", self.skill)
        # 必含 "禁止" 的反例黑名单
        self.assertIn("禁止", self.skill)

    def test_state_machine_is_two_step(self) -> None:
        state_script = (ROOT / "scripts" / "state_machine.py").read_text(encoding="utf-8")
        self.assertIn("STARTED", state_script)
        self.assertIn("DONE", state_script)
        self.assertNotIn("record_dispatch", state_script)
        self.assertNotIn("record_result", state_script)

    def test_hard_gates_documented(self) -> None:
        # Soft policies must not be presented as the only completion criteria
        self.assertIn("硬门禁", self.skill)
        self.assertIn("推荐流程", self.skill)
        self.assertIn("代码不审计", self.skill)
        self.assertIn("报告级", self.skill)
        # validate_report scope must be explicit
        self.assertIn("validate_report.py", self.skill)
        self.assertIn("只做报告级", self.skill)

    def test_docs_do_not_promise_removed_ledger_apis(self) -> None:
        # v6 removed dispatch ledger from state_machine; docs/prompts must not require it
        for blob_name, blob in (
            ("skill", self.skill),
            ("readme", self.readme),
            ("root_readme", self.root_readme),
            ("test_prompts", self.test_prompts),
        ):
            self.assertNotIn("record_dispatch", blob, msg=blob_name)
            self.assertNotIn("record_result", blob, msg=blob_name)

    def test_tavily_listed_in_main_skill(self) -> None:
        # v6.3.1：Tavily 为六源之一，仅 Lead Agent；subagent 用 AnySearch+SciVerse+Exa
        self.assertIn("Tavily", self.skill)
        self.assertNotIn("Tavily", self.subagent)

    def test_adr_0010_session_ledger_bind_is_documented(self) -> None:
        """ADR-0010：研究主路径必须 --session；External 登记模板不得失踪。"""
        adr = (REPO_ROOT / "docs" / "adr" / "0010-检索成功路径与证据台账因果绑定.md").read_text(encoding="utf-8")
        self.assertIn("ADR-0005", adr)
        self.assertIn("台账写入失败则 CLI 非零退出", adr)
        self.assertIn("--session", adr)

        self.assertIn("ADR-0010", self.skill)
        self.assertIn("必须", self.skill)
        self.assertIn("--session", self.skill)
        self.assertIn("不是研究主路径", self.skill)
        for backend in ("AnySearch", "SciVerse", "WebSearch"):
            self.assertIn(
                f"add --backend {backend}",
                self.skill,
                msg=f"missing External registration template for {backend}",
            )
        self.assertIn("台账写入失败", self.skill)
        self.assertIn("ADR-0010", self.readme)
        self.assertIn("ADR-0010", (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8"))

    def test_adr_0011_requirement_level_is_executable(self) -> None:
        """ADR-0011：档位可执行；runtime-adapters 钉住 WebBackend / ExternalTool 清单。"""
        adr = (REPO_ROOT / "docs" / "adr" / "0011-BackendRequirementLevel可执行化.md").read_text(encoding="utf-8")
        self.assertIn("SciVerseReadiness", adr)
        self.assertIn("ALLOW_DEGRADED", adr)
        self.assertIn("SearchBackendRegistry", adr)
        self.assertIn("REGISTRY.register", adr)

        adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        self.assertIn("## WebBackend 扩展清单", adapters)
        self.assertIn("## ExternalTool 扩展清单", adapters)
        self.assertIn("iter_readiness_descriptors", adapters)
        self.assertIn("SciVerseReadiness", adapters)

        self.assertIn("ADR-0011", self.skill)
        self.assertIn("requirement=required", self.skill)
        gate = (ROOT / "scripts" / "required_backends.py").read_text(encoding="utf-8")
        self.assertIn("iter_required_descriptors", gate)
        self.assertNotIn("ALLOW_DEGRADED", gate)

    def test_adr_0012_companion_install_contract(self) -> None:
        """ADR-0012 D1：最小安装是 tri-research + serpapi；禁止单技能即就绪 / 可回退措辞。"""
        adr = (REPO_ROOT / "docs" / "adr" / "0012-tri-research与serpapi交付单元契约.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("D1", adr)
        self.assertIn("ADR-0015", adr)
        self.assertIn("不足以", adr)
        self.assertIn("state_machine start", adr)

        pin = "不足以 `state_machine start`"
        self.assertIn(pin, self.root_readme)
        self.assertIn(pin, self.readme)
        self.assertIn(pin, self.skill)
        self.assertIn("--skill serpapi", self.root_readme)
        self.assertIn("--skill serpapi", self.readme)
        self.assertIn("ADR-0012", self.skill)
        self.assertIn("research-subagent", self.root_readme)

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        tri = next(p for p in marketplace["plugins"] if p["name"] == "tri-research")
        self.assertEqual(tri.get("dependencies"), ["serpapi"])
        serpapi_plugin = next(p for p in marketplace["plugins"] if p["name"] == "serpapi")
        self.assertNotIn("辅助", serpapi_plugin["description"])

        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Delivery Unit**", context)

        serpapi_skill = (ROOT.parent / "serpapi" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("当被 tri-research 引用时升为 required，不可回退", serpapi_skill)
        self.assertIn("cli > env > .env", serpapi_skill)
        forbidden = (
            "只安装 tri-research",
            "可回退其他搜索",
            "fall back to other available search methods",
            "Default provider? No",
            "Not the default search provider",
        )
        docs = (
            ("root_readme", self.root_readme),
            ("skill_readme", self.readme),
            ("skill", self.skill),
            ("serpapi_skill", serpapi_skill),
            ("marketplace", json.dumps(marketplace, ensure_ascii=False)),
        )
        for name, blob in docs:
            for phrase in forbidden:
                self.assertNotIn(phrase, blob, msg=f"{name} still allows conflicting install wording: {phrase!r}")

    def test_adr_0013_retrieval_topology(self) -> None:
        """ADR-0013：三类能力 + Registry 非 Lead 主路径；架构图禁止 MCP 误标。"""
        adr = (REPO_ROOT / "docs" / "adr" / "0013-检索拓扑三类能力与Registry非主路径.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "Machine Backend",
            "External Tool",
            "Host",
            "SearchBackendRegistry",
            "程序化 seam",
            "不是 Lead",
            "AnySearch",
            "SciVerse",
            "WebSearch",
            "Exa",
            "SerpApi",
            "Tavily",
        ):
            self.assertIn(phrase, adr)
        self.assertNotIn("宿主 MCP", adr)

        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Machine Backend**", context)
        self.assertIn("**External Tool**", context)
        self.assertIn("**Host**", context)
        self.assertIn("不是** Lead Agent 主路径", context)
        self.assertIn("不是** 六源统一总线", context)
        self.assertIn("六源 Registry 总线", context)
        self.assertIn("宿主 MCP", context)  # Avoid 词必须出现
        registry = next(
            (blk for blk in context.split("**") if blk.startswith("SearchBackendRegistry")),
            "",
        )
        self.assertTrue(registry, "CONTEXT 缺少 SearchBackendRegistry 词条")
        avoid = context.split("**SearchBackendRegistry**", 1)[1].split("**SearchResult**", 1)[0]
        self.assertIn("_Avoid_", avoid)
        self.assertIn("六源 Registry 总线", avoid)
        self.assertIn("Lead 主路径", avoid)

        arch_path = REPO_ROOT / "assets" / "tri-research-architecture.json"
        arch = json.loads(arch_path.read_text(encoding="utf-8"))
        blob = json.dumps(arch, ensure_ascii=False)
        self.assertNotIn("宿主 MCP", blob)
        self.assertNotIn("MCP 工具", blob)
        self.assertNotIn("mcp__", blob.lower())

        labels = {c["id"]: c for c in arch["components"]}
        self.assertIn("exa", labels)
        self.assertIn("tavily", labels)
        self.assertIn("serpapi", labels)
        self.assertIn("anysearch", labels)
        self.assertIn("sciverse", labels)
        self.assertIn("websearch", labels)
        self.assertNotIn("registry", labels)
        self.assertNotEqual(labels["anysearch"]["id"], labels["sciverse"]["id"])
        self.assertIn("CLI", labels["anysearch"]["sublabel"])
        self.assertIn("SDK", labels["sciverse"]["sublabel"])
        self.assertIn("Host", labels["websearch"]["sublabel"])
        self.assertNotIn("MCP", labels["anysearch"].get("sublabel", ""))
        self.assertNotIn("MCP", labels["sciverse"].get("sublabel", ""))

        edges = {(c["from"], c["to"]): c for c in arch["connections"]}
        self.assertIn(("lead", "websearch"), edges)
        self.assertIn(("lead", "search_cli"), edges)
        self.assertIn(("subagent", "anysearch"), edges)
        self.assertIn(("subagent", "sciverse"), edges)
        self.assertIn(("subagent", "search_cli"), edges)
        self.assertIn(("search_cli", "exa"), edges)
        self.assertIn(("search_cli", "serpapi"), edges)
        self.assertIn(("search_cli", "tavily"), edges)
        self.assertNotIn(("subagent", "serpapi"), edges)
        self.assertNotIn(("subagent", "tavily"), edges)
        self.assertNotIn(("subagent", "websearch"), edges)
        for conn in arch["connections"]:
            self.assertNotIn("MCP", conn.get("label", ""))

        cards = " ".join(item for card in arch["cards"] for item in [card["title"], *card["items"]])
        self.assertIn("Exa", cards)
        self.assertIn("SciVerse", cards)
        self.assertIn("SerpApi", cards)
        self.assertIn("required", cards)
        self.assertIn("Machine", cards)
        self.assertIn("External", cards)
        self.assertIn("Host", cards)
        self.assertIn("Registry", cards)

        html = (REPO_ROOT / "assets" / "tri-research-architecture.html").read_text(encoding="utf-8")
        self.assertNotIn("宿主 MCP", html)
        self.assertNotIn("MCP 工具调用", html)

        self.assertIn("不是统一六源 Registry 总线", self.root_readme)
        self.assertIn("ADR-0013", self.readme)
        adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        self.assertIn("## Host 能力", adapters)
        self.assertIn("ADR-0013", adapters)


if __name__ == "__main__":
    unittest.main()
