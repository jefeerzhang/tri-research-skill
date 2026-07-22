from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "state_machine.py"


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        import subprocess
        self.subprocess = subprocess
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name) / "state"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, ok: bool = True):
        command = [
            sys.executable,
            str(SCRIPT),
            "--state-dir",
            str(self.state_dir),
            *args,
        ]
        result = self.subprocess.run(command, capture_output=True, text=True)
        if ok and result.returncode != 0:
            self.fail(f"failed: {command}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"unexpectedly succeeded: {command}\nstdout={result.stdout}")
        return result

    def set_params(self, session: str, *, topic: str = "人工智能与劳动分配", min_sources: int = 10) -> None:
        params = json.dumps(
            {
                "topic": topic,
                "min_sources": min_sources,
                "keywords_zh": ["人工智能", "劳动分配"],
                "keywords_en": ["artificial intelligence", "labor allocation"],
            },
            ensure_ascii=False,
        )
        self.run_cli("--session", session, "set_params", params)

    def write_valid_report(self, name: str = "report.md", *, topic: str = "人工智能与劳动分配", source_count: int = 10) -> Path:
        report = Path(self.temp_dir.name) / name
        inline = "".join(f"[{i}]" for i in range(1, source_count + 1))
        refs = []
        for i in range(1, source_count + 1):
            if i % 2 == 0:
                refs.append(f"[{i}] 作者{i} — 中文研究 — https://source-{i}.cn/article-{i} — 2024 — 层级: 2 — 来源: AnySearch")
            else:
                refs.append(f"[{i}] Author{i} — English study — https://source-{i}.org/paper-{i} — 2025 — 层级: 1 — 来源: SciVerse")
        report.write_text(
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
| 搜索源使用 | AnySearch: {source_count}条 |
| 耗时 | 3.0 分钟 |
| 报告位置 | ~/tri-research-reports/{name} |
""",
            encoding="utf-8",
        )
        return report

    def test_start_creates_session(self) -> None:
        result = self.run_cli("--session", "test-start", "start")
        self.assertIn("STATE:STARTED", result.stdout)
        self.assertIn("SESSION:test-start", result.stdout)

    def test_start_rejects_duplicate(self) -> None:
        self.run_cli("--session", "dup", "start")
        result = self.run_cli("--session", "dup", "start", ok=False)
        self.assertIn("already exists", result.stderr)

    def test_set_params_and_get(self) -> None:
        self.run_cli("--session", "params", "start")
        params = json.dumps(
            {"topic": "测试", "min_sources": 10, "keywords_zh": ["测试"], "keywords_en": ["test"]},
            ensure_ascii=False,
        )
        self.run_cli("--session", "params", "set_params", params)
        result = self.run_cli("--session", "params", "get_params")
        # First line is the SESSION: marker; second line is the JSON payload.
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "SESSION:params")
        loaded = json.loads(lines[1])
        self.assertEqual(loaded["topic"], "测试")

    def test_set_params_rejects_invalid(self) -> None:
        self.run_cli("--session", "invalid-params", "start")
        result = self.run_cli(
            "--session", "invalid-params", "set_params",
            json.dumps({"topic": "测试"}, ensure_ascii=False),
            ok=False,
        )
        self.assertIn("min_sources", result.stderr)

    def test_params_immutable(self) -> None:
        self.run_cli("--session", "immutable", "start")
        self.set_params("immutable")
        result = self.run_cli(
            "--session", "immutable", "set_params",
            json.dumps({"topic": "changed", "min_sources": 10, "keywords_zh": ["x"], "keywords_en": ["y"]}),
            ok=False,
        )
        self.assertIn("immutable", result.stderr)

    def test_full_workflow(self) -> None:
        self.run_cli("--session", "full", "start")
        self.set_params("full")
        report = self.write_valid_report()
        result = self.run_cli("--session", "full", "done", "--report", str(report))
        self.assertIn("STATE:DONE", result.stdout)
        self.assertIn("REPORT:", result.stdout)
        # get_phase now emits "SESSION:<id>" + phase value on separate lines.
        phase_output = self.run_cli("--session", "full", "get_phase").stdout
        phase_value = [line for line in phase_output.splitlines() if not line.startswith("SESSION:")][0]
        self.assertEqual(phase_value, "DONE")

    def test_done_validates_report(self) -> None:
        self.run_cli("--session", "validate", "start")
        self.set_params("validate")
        bad_report = Path(self.temp_dir.name) / "bad.md"
        bad_report.write_text("# 错误\n\n无内容\n", encoding="utf-8")
        result = self.run_cli(
            "--session", "validate", "done", "--report", str(bad_report), ok=False
        )
        self.assertIn("validation failed", result.stderr)
        phase_output = self.run_cli("--session", "validate", "get_phase").stdout
        phase_value = [line for line in phase_output.splitlines() if not line.startswith("SESSION:")][0]
        self.assertEqual(phase_value, "STARTED")

    def test_done_requires_params(self) -> None:
        self.run_cli("--session", "no-params", "start")
        report = self.write_valid_report("no-params.md")
        result = self.run_cli(
            "--session", "no-params", "done", "--report", str(report), ok=False
        )
        self.assertIn("not set", result.stderr)

    def test_done_rejects_duplicate(self) -> None:
        self.run_cli("--session", "double-done", "start")
        self.set_params("double-done")
        report = self.write_valid_report("double-done.md")
        self.run_cli("--session", "double-done", "done", "--report", str(report))
        result = self.run_cli(
            "--session", "double-done", "done", "--report", str(report), ok=False
        )
        self.assertIn("already completed", result.stderr)

    def test_done_rejects_wrong_topic(self) -> None:
        self.run_cli("--session", "wrong-topic", "start")
        self.set_params("wrong-topic")
        report = self.write_valid_report("wrong-topic.md", topic="完全不同的主题")
        result = self.run_cli(
            "--session", "wrong-topic", "done", "--report", str(report), ok=False
        )
        self.assertIn("主题", result.stderr)

    def test_sessions_isolated(self) -> None:
        self.run_cli("--session", "sess-a", "start")
        self.set_params("sess-a")
        self.run_cli("--session", "sess-b", "start")
        # get_phase now emits "SESSION:<id>" + phase value; extract the
        # phase value (the non-SESSION: line) for comparison.
        def _phase_for(session: str) -> str:
            out = self.run_cli("--session", session, "get_phase").stdout
            return [line for line in out.splitlines() if not line.startswith("SESSION:")][0]
        self.assertEqual(_phase_for("sess-a"), "STARTED")
        self.assertEqual(_phase_for("sess-b"), "STARTED")

    def test_check_works(self) -> None:
        self.run_cli("--session", "checkme", "start")
        result = self.run_cli("--session", "checkme", "check")
        self.assertIn("INTEGRITY:OK", result.stdout)

    def test_rejects_path_traversal_session(self) -> None:
        result = self.run_cli("--session", "../escape", "start", ok=False)
        self.assertIn("session id must match", result.stderr)


if __name__ == "__main__":
    unittest.main()
