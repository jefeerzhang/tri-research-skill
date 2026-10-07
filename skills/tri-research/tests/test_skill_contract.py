"""Skill 合约的真实不变量（架构审查候选 2）。

本文件只钉两类东西：

1. **有程序化真源的不变量** —— 名册、档位、版本、章节、计数。断言读真源本身
   （``validate_report.USAGE_ROSTER`` / ``validate_report.REQUIRED_HEADINGS`` /
   ``Backend.requirement`` / SKILL frontmatter / discover 计数），不另写一份字面量。
2. **决定守卫** —— 曾被明确否决的做法不得回潮：MCP 通道、``ALLOW_DEGRADED``
   逃生口、已删除的 ledger API、required 降级措辞、单技能即就绪措辞。

不钉散文措辞。ADR 是决策记录，因此只钉「哪份 ADR 记了哪个决定」这一最小事实
（见 ``test_each_adr_records_its_decision``）——重写一句话不该让 CI 变红。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from _test_helpers import load_module

ROOT = Path(__file__).parents[1]
REPO_ROOT = ROOT.parents[1]

# 产品锁（R-A + OpenAlex）：点名名单恰好这七源，不得增删改名。
# 这是**唯一一处有意的冻结点**——它的职责就是让「增删改名册」这个产品决定红掉。
# 运行时可执行真源是 validate_report.USAGE_ROSTER（ADR-0009）；
# test_usage_roster_hard_gate_cannot_drift 断言两者相等。
LOCKED_USAGE_ROSTER = (
    "AnySearch",
    "SciVerse",
    "Exa",
    "SerpApi",
    "Tavily",
    "OpenAlex",
    "WebSearch",
)
SOURCE_NAME_RE = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in LOCKED_USAGE_ROSTER) + r")\b")

# 名册棘轮的**覆盖清单**（候选 1）：凡在正文里逐一点名七源的文档与资产，
# 都必须登记在这里。棘轮覆盖面 = 这份清单，不再靠「记得改哪几个文件」。
ROSTER_BEARING_FILES = (
    ROOT / "SKILL.md",
    ROOT / "README.md",
    REPO_ROOT / "README.md",
    ROOT / "references" / "report-format.md",
    ROOT / "references" / "runtime-adapters.md",
    ROOT / "test-prompts.json",
    REPO_ROOT / "assets" / "tri-research-architecture.json",
    REPO_ROOT / "CONTEXT.md",
)

# ADR 是决策记录。只钉「哪份 ADR 记了哪个决定」这一个最小事实（候选 2），
# 不再逐条钉散文措辞——重写一句话不该让 CI 变红。
# 锚点取该决定的核心名词，验的是「这决定还在」，不是「这句话是这样写的」。
ADR_DECISIONS = (
    ("0007-serpapi-required-key-探活与Scholar间接.md", ("SerpApi", "required")),
    ("0009-源覆盖硬门禁单一名单.md", ("R-A", "USAGE_ROSTER")),
    ("0010-检索成功路径与证据台账因果绑定.md", ("--session", "ADR-0005")),
    ("0011-BackendRequirementLevel可执行化.md", ("BackendRequirementLevel", "SciVerseReadiness")),
    ("0012-tri-research与serpapi交付单元契约.md", ("D1", "ADR-0015")),
    ("0013-检索拓扑三类能力与Registry非主路径.md", ("Machine Backend", "External Tool", "Host")),
    ("0014-DONE门面与active-session身份.md", ("build_proof", "active-session")),
    ("0015-共享运行时打包.md", ("tri_research_runtime", "pip install")),
    ("0016-openalex-machine-backend.md", ("OpenAlex", "optional")),
)


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

        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{v}"', pyproject, "pyproject.toml runtime 版本漂移")

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        rel = re.search(r"^##\s+\[([^\]]+)\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$", changelog, re.MULTILINE)
        self.assertIsNotNone(rel, "CHANGELOG 缺少已发布版本条目")
        self.assertEqual(v, rel.group(1), "CHANGELOG 最新发布版本与 frontmatter 不一致")

    def test_source_roster_is_documented_across_docs(self) -> None:
        """点名名册必须在 SKILL / skill README / 根 README 出现（读产品锁，不写第二份）。"""
        for name in LOCKED_USAGE_ROSTER:
            self.assertIn(name, self.skill)
            self.assertIn(name, self.skill)
            self.assertIn(name, self.readme)
            if self.root_readme:
                self.assertIn(name, self.root_readme)
        self.assertIn("七个搜索后端", self.skill)
        self.assertIn("七个搜索后端", self.readme)

    @staticmethod
    def _executable_tiers() -> dict[str, str]:
        """档位的可执行真源：``Backend.requirement``（ADR-0011）。

        文档表格里的「必选 / 可选」是散文，真源是 backend 上的枚举字段。
        这里把两者连起来，免得档位期望在文档里再手写一遍。
        """
        backends = load_module(ROOT / "scripts" / "search_backends.py", "search_backends_contract")
        return {
            backends.EXA_BACKEND.name: str(backends.EXA_BACKEND.requirement),
            backends.TAVILY_BACKEND.name: str(backends.TAVILY_BACKEND.requirement),
            backends.OPENALEX_BACKEND.name: str(backends.OPENALEX_BACKEND.requirement),
        }

    def test_executable_tiers_are_the_single_owner(self) -> None:
        """档位只有一个家：**Backend.requirement**（候选 1）。

        下方 Exa / SerpApi 的文档档位测试把手写期望建在这份真源上；
        真源一变，期望随之失效，而不是两处各自相信自己的记忆。
        """
        self.assertEqual(
            self._executable_tiers(),
            {"Exa": "required", "Tavily": "optional", "OpenAlex": "optional"},
            "Backend.requirement 档位漂移：ADR-0001（Exa required）、ADR-0016（OpenAlex optional）、Tavily optional 是唯一真源",
        )

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

    def test_roster_reach_covers_every_roster_bearing_doc(self) -> None:
        """候选 1：棘轮的覆盖面必须等于名册的重复面。

        ADR-0009 只钉了 SKILL 硬门禁行 / report-format / skill README 三处，
        但逐一点名七源的还有根 README、runtime-adapters、test-prompts.json、
        架构 JSON 与 CONTEXT。接入 OpenAlex 这条第七条时改了十来个文件，却只有
        3 个被闸门读到；本测试把覆盖面显式化，让棘轮与重复面同宽。

        清单是**显式**的，不做自动发现。原因：CHANGELOG、docs/adr/、tests/ 与
        examples/ 里的历史报告也会逐一点名七源，但它们是**记录**而不是**声明**——
        回填历史记录不是本棘轮的职责，自动发现只会制造误报。
        """
        missing: list[str] = []
        for path in ROSTER_BEARING_FILES:
            rel = path.relative_to(REPO_ROOT).as_posix()
            self.assertTrue(path.exists(), f"ROSTER_BEARING_FILES 登记了不存在的文件: {rel}")
            blob = path.read_text(encoding="utf-8")
            absent = [name for name in LOCKED_USAGE_ROSTER if not SOURCE_NAME_RE.search(blob)]
            if absent:
                missing.append(f"{rel} 缺: {' / '.join(absent)}")
        self.assertEqual(missing, [], "名册覆盖清单里有点名不全的文件:\n  " + "\n  ".join(missing))

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

        期望不再手写：它读 ``Backend.requirement``（候选 1），真源一变这里就红。
        合约测试此前只查六源名字，不查档位，于是 skill README / runtime-adapters
        把 Exa 悄悄留成「可选」也没人拦。
        """
        self.assertEqual(
            self._executable_tiers()["Exa"],
            "required",
            "ADR-0001：Exa 的可执行档位应为 required（真源是 Backend.requirement）",
        )
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
        self.assertIn("STEM", self.skill)  # STEM 主题不强制 google_scholar
        # 决定守卫：不得宣称 Scholar 是独立后端。
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

    def test_search_execution_spec(self) -> None:
        """搜索执行纪律的关键决定词（无程序化真源，故为决定守卫）。

        「中英双补」「全源覆盖」是执行纪律的判定词；validate_report 只做报告级
        双语检查，逐维度逐源不审计（SKILL 自己写明），所以这里钉的是决定本身。
        """
        self.assertIn("搜索执行规范", self.skill)
        self.assertIn("中英双补", self.skill)
        self.assertIn("全源覆盖", self.skill)
        self.assertIn("semantic_search", self.skill)

    def test_report_format_disclosed_to_reference(self) -> None:
        """格式契约下放到 references/report-format.md。

        章节名单读 ``validate_report.REQUIRED_HEADINGS``（真源），不手写第二份
        七章节字面量——手写那份在改章节名时必然过期（候选 2）。
        """
        self.assertIn("references/report-format.md", self.skill)
        reference = (ROOT / "references" / "report-format.md").read_text(encoding="utf-8")
        validator = load_module(ROOT / "scripts" / "validate_report.py", "validate_report_sections_contract")
        missing = [heading for heading in validator.REQUIRED_HEADINGS if f"## {heading}" not in reference]
        self.assertEqual(missing, [], f"report-format.md 缺章节（真源 REQUIRED_HEADINGS）: {missing}")
        self.assertIn("层级:", reference)
        self.assertIn("来源:", reference)

    def test_anysearch_3_compatible(self) -> None:
        self.assertIn("get_sub_domains", self.subagent)
        self.assertIn("runtime.conf", self.subagent)

    def test_sciverse_python_sdk_not_mcp(self) -> None:
        """SciVerse 唯一通道是 Python SDK；MCP 调用形式是决定守卫（禁止回潮）。"""
        self.assertIn("SciVerse 调用规范", self.skill)
        self.assertIn("pip install sciverse", self.skill)
        self.assertIn("AgentToolsClient", self.skill)
        self.assertIn("SCIVERSE_API_TOKEN", self.skill)
        # 决定守卫：不应出现 MCP 工具调用形式。
        self.assertNotIn("mcp__sciverse__semantic_search", self.skill)
        self.assertNotIn("mcp__sciverse__search_papers", self.skill)
        self.assertNotIn("mcp__sciverse__read_content", self.skill)

    def test_state_machine_is_two_step(self) -> None:
        state_script = (ROOT / "scripts" / "state_machine.py").read_text(encoding="utf-8")
        self.assertIn("STARTED", state_script)
        self.assertIn("DONE", state_script)
        self.assertNotIn("record_dispatch", state_script)
        self.assertNotIn("record_result", state_script)

    def test_hard_gates_documented(self) -> None:
        """硬门禁与推荐流程必须分开写，且 validate_report 的范围必须写明。

        用章节结构钉（两个小节真的存在），而不是钉「代码不审计」这类句子。
        """
        self.assertIn("## 硬门禁与推荐流程", self.skill)
        self.assertIn("### 硬门禁（代码强制）", self.skill)
        self.assertIn("### 推荐流程（非硬门禁）", self.skill)
        self.assertIn("validate_report.py", self.skill)

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

    def test_tavily_is_lead_only_not_in_subagent(self) -> None:
        # 分配决定：Tavily 在点名名单内但仅 Lead Agent，子代理不得出现。
        # （「Tavily 在主 SKILL 里」由名册覆盖测试负责，这里不再重复正向断言。）
        self.assertNotIn("Tavily", self.subagent)

    def test_adr_0010_session_ledger_bind_is_documented(self) -> None:
        """ADR-0010 的可执行契约：External 登记模板不得失踪。

        ADR 措辞由 test_each_adr_records_its_decision 统一覆盖；这里只留
        「模板真的在 SKILL 里」与「主路径必须 --session」两件可执行事实。
        """
        for backend in ("AnySearch", "SciVerse", "WebSearch"):
            self.assertIn(
                f"add --backend {backend}",
                self.skill,
                msg=f"missing External registration template for {backend}",
            )
        self.assertIn("--session", self.skill)

    def test_adr_0011_requirement_level_is_executable(self) -> None:
        """ADR-0011：档位可执行；runtime-adapters 钉住扩展清单；门禁无降级开关。"""
        adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        self.assertIn("## WebBackend 扩展清单", adapters)
        self.assertIn("## ExternalTool 扩展清单", adapters)
        self.assertIn("iter_readiness_descriptors", adapters)
        self.assertIn("SciVerseReadiness", adapters)

        self.assertIn("requirement=required", self.skill)
        gate = (ROOT / "scripts" / "required_backends.py").read_text(encoding="utf-8")
        self.assertIn("iter_required_descriptors", gate)
        # 决定守卫：不得出现降级逃生开关（ADR-0006 / 0011 明确否决）。
        self.assertNotIn("ALLOW_DEGRADED", gate)

    def test_adr_0012_companion_install_contract(self) -> None:
        """ADR-0012 D1：最小安装是 tri-research + serpapi；禁止可回退措辞。

        ``pin`` 与 ``forbidden`` 是**决定守卫**（D1 的措辞就是决定本身，无法用
        程序化真源表达）；ADR 文件全文措辞交由 test_each_adr_records_its_decision。
        """
        pin = "不足以 `state_machine start`"
        self.assertIn(pin, self.root_readme)
        self.assertIn(pin, self.readme)
        self.assertIn(pin, self.skill)
        self.assertIn("--skill serpapi", self.root_readme)
        self.assertIn("--skill serpapi", self.readme)
        self.assertIn("research-subagent", self.root_readme)

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        tri = next(p for p in marketplace["plugins"] if p["name"] == "tri-research")
        self.assertEqual(tri.get("dependencies"), ["serpapi"])
        serpapi_plugin = next(p for p in marketplace["plugins"] if p["name"] == "serpapi")
        self.assertNotIn("辅助", serpapi_plugin["description"])

        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Delivery Unit**", context)

        serpapi_skill = (ROOT.parent / "serpapi" / "SKILL.md").read_text(encoding="utf-8")
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
        """ADR-0013：三类能力 + Registry 非 Lead 主路径；架构图禁止 MCP 误标。

        CONTEXT 部分只钉**结构**（三个术语词条存在、Registry 词条带 `_Avoid_`），
        不钉 `_Avoid_` 行里写了哪几句话；ADR 全文措辞交由 ADR 决策表。
        """
        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Machine Backend**", context)
        self.assertIn("**External Tool**", context)
        self.assertIn("**Host**", context)
        registry = next(
            (blk for blk in context.split("**") if blk.startswith("SearchBackendRegistry")),
            "",
        )
        self.assertTrue(registry, "CONTEXT 缺少 SearchBackendRegistry 词条")
        avoid = context.split("**SearchBackendRegistry**", 1)[1].split("**SearchResult**", 1)[0]
        self.assertIn("_Avoid_", avoid)

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

        adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        self.assertIn("## Host 能力", adapters)

    def test_adr_0014_control_plane_polish(self) -> None:
        """ADR-0014：citations 是薄解释层，不得独立枚举章节或名册。

        本测试的实质是**经真源**验证 citations 没有变成第二份规则清单
        （读 REQUIRED_HEADINGS / USAGE_ROSTER），不是钉 ADR 的措辞。
        """
        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Evidence Error**", context)
        self.assertIn("**Active Session Pointer**", context)

        self.assertIn("并行会话", self.skill)
        self.assertIn("--session", self.skill)
        self.assertIn("active-session", self.skill)

        citations = (ROOT.parent / "citations" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("validate_report.py", citations)
        validator = load_module(ROOT / "scripts" / "validate_report.py", "validate_report_citations_contract")
        listed_headings = sum(1 for heading in validator.REQUIRED_HEADINGS if heading in citations)
        self.assertLess(
            listed_headings,
            len(validator.REQUIRED_HEADINGS),
            "citations SKILL must not independently enumerate all required chapters",
        )
        listed_sources = sum(1 for name in validator.USAGE_ROSTER if name in citations)
        self.assertLess(
            listed_sources,
            len(validator.USAGE_ROSTER),
            "citations SKILL must not independently enumerate USAGE_ROSTER",
        )

    def test_adr_0015_shared_runtime_package(self) -> None:
        """ADR-0015：可安装 runtime 包；serpapi 走包 import（不再是「待 ADR-0015」）。"""
        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("**Shared Runtime**", context)
        self.assertIn("tri_research_runtime", context)

        self.assertIn("pip install -e .", self.root_readme)
        adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        self.assertIn("tri_research_runtime", adapters)
        self.assertIn("pip install -e .", adapters)

        serpapi_skill = (ROOT.parent / "serpapi" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("tri_research_runtime", serpapi_skill)
        # 决定守卫：路径耦合的「待 ADR-0015」待办标记必须已解决，不得回潮。
        self.assertNotIn("待 ADR-0015", serpapi_skill)

        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("tri-research-runtime", pyproject)

    def test_adr_0016_openalex_machine_backend(self) -> None:
        """ADR-0016：OpenAlex 为 optional Machine；重开 0007§6；调用矩阵不进子代理。

        ADR 全文措辞交由 ADR 决策表；这里钉 CONTEXT 词条结构、调用矩阵
        （架构 JSON 的 components / boundaries / edges）与被演进的 ADR 标记。
        """
        context = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
        openalex_blk = context.split("**OpenAlex**", 1)[1]
        self.assertIn("Machine Backend", openalex_blk)
        self.assertIn("optional", openalex_blk)
        self.assertIn("_Avoid_", openalex_blk)

        self.assertIn("openalex_search.py", self.skill)
        self.assertIn("OpenAlex", self.subagent)
        self.assertIn("openalex_search.py", self.subagent)
        # 分配决定：Tavily 仍仅 Lead。
        self.assertNotIn("Tavily", self.subagent)

        adapters = (ROOT / "references" / "runtime-adapters.md").read_text(encoding="utf-8")
        self.assertIn("OpenAlex", adapters)

        for evolved in (
            "0007-serpapi-required-key-探活与Scholar间接.md",
            "0009-源覆盖硬门禁单一名单.md",
            "0010-检索成功路径与证据台账因果绑定.md",
            "0013-检索拓扑三类能力与Registry非主路径.md",
        ):
            blob = (REPO_ROOT / "docs" / "adr" / evolved).read_text(encoding="utf-8")
            self.assertIn("部分被 ADR-0016 演进", blob, msg=evolved)

        arch = json.loads((REPO_ROOT / "assets" / "tri-research-architecture.json").read_text(encoding="utf-8"))
        labels = {c["id"]: c for c in arch["components"]}
        self.assertIn("openalex", labels)
        self.assertIn("OpenAlex", labels["openalex"]["label"])
        self.assertIn("Machine", labels["openalex"]["sublabel"])
        machine = next(b for b in arch["boundaries"] if b["label"] == "Machine Backend")
        self.assertIn("openalex", machine["wraps"])
        edges = {(c["from"], c["to"]) for c in arch["connections"]}
        self.assertIn(("search_cli", "openalex"), edges)
        self.assertNotIn(("subagent", "openalex"), edges)
        cards = " ".join(item for card in arch["cards"] for item in [card["title"], *card["items"]])
        self.assertIn("OpenAlex", cards)

    def test_each_adr_records_its_decision(self) -> None:
        """每份 ADR 仍然记着它的决定（候选 2：只钉决定，不钉措辞）。

        取代原先逐份 ADR 的「散文短语必须出现」清单（0013 一份就钉了 14 条）。
        断言的是决定的核心名词，不是某句原话。
        """
        missing: list[str] = []
        for filename, anchors in ADR_DECISIONS:
            path = REPO_ROOT / "docs" / "adr" / filename
            if not path.exists():
                missing.append(f"{filename}: 文件缺失")
                continue
            blob = path.read_text(encoding="utf-8")
            absent = [anchor for anchor in anchors if anchor not in blob]
            if absent:
                missing.append(f"{filename} 缺: {' / '.join(absent)}")
        self.assertEqual(missing, [], "ADR 决策记录缺失:\n  " + "\n  ".join(missing))

    def test_every_adr_keeps_rejected_options(self) -> None:
        """被拒选项是 ADR 的价值所在。用结构钉，不用「被拒」二字钉。"""
        missing: list[str] = []
        for path in sorted((REPO_ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")):
            blob = path.read_text(encoding="utf-8")
            if "Considered Options" not in blob and "被拒" not in blob:
                missing.append(path.name)
        self.assertEqual(missing, [], "以下 ADR 缺少被拒选项记录:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    unittest.main()
