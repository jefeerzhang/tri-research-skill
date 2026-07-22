"""Regression tests for module-level imports.

Bug fixed: state_machine.py used `from validate_report import validate as
validate_report` (implicit relative import). That import only resolves when
Python prepends the script's directory to sys.path[0], which happens for
direct script execution but NOT for:
  - importlib.util.spec_from_file_location (how external tools / future
    pytest setups / programmatic callers load a single script)
  - `python -m` style execution
  - any package-mode invocation

These tests pin the contract: state_machine.py must be loadable as a module
from any cwd, without the caller having to add scripts/ to sys.path.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).parents[3]
SCRIPT = REPO / "skills" / "tri-research" / "scripts" / "state_machine.py"
SAMPLE = REPO / "examples" / "DEEP_RESEARCH_人工智能与劳动分配_2026-07-21.md"


def _load_module(cwd: str) -> types.ModuleType:
    """Load state_machine.py via importlib, after chdir(cwd)."""
    old = os.getcwd()
    try:
        os.chdir(cwd)
        spec = importlib.util.spec_from_file_location("sm_under_test_xyz", str(SCRIPT))
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(old)


class ModuleImportTests(unittest.TestCase):
    def test_loadable_via_importlib_without_syspath_hack(self) -> None:
        """Loading state_machine.py via importlib from a different cwd must
        succeed — no implicit reliance on sys.path[0] being the scripts dir."""
        with tempfile.TemporaryDirectory() as other_cwd:
            _load_module(other_cwd)  # must not raise ModuleNotFoundError

    def test_loadable_via_subprocess_with_clean_pythonpath(self) -> None:
        """A subprocess running state_machine.py with an empty PYTHONPATH
        and a different cwd must be able to import the module without the
        caller manually inserting scripts/ into PYTHONPATH."""
        with tempfile.TemporaryDirectory() as other_cwd:
            loader = (
                "import importlib.util;"
                f"spec = importlib.util.spec_from_file_location("
                f"'sm_subprocess_test', {str(SCRIPT)!r});"
                "mod = importlib.util.module_from_spec(spec);"
                "spec.loader.exec_module(mod);"
                "print('IMPORT_OK')"
            )
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, "-c", loader],
                capture_output=True,
                text=True,
                env=env,
                cwd=other_cwd,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=(
                    f"state_machine.py failed to import from a different cwd.\n"
                    f"stdout={result.stdout}\nstderr={result.stderr}"
                ),
            )
            self.assertIn("IMPORT_OK", result.stdout)

    def test_full_workflow_via_importlib_from_other_cwd(self) -> None:
        """End-to-end: load state_machine.py via importlib from a different
        cwd and drive start → set_params → done → check. This exercises the
        very `from validate_report import` statement that was broken, and
        also pins that the validator (validate_report) is reachable from
        the importlib-loaded module."""
        if not SAMPLE.is_file():
            self.skipTest(f"sample report not found: {SAMPLE}")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as other_cwd:
            mod = _load_module(other_cwd)
            store = mod.StateStore(Path(other_cwd) / "state")
            session = "regression-importlib"

            def make_args(command: str, **kwargs):
                return argparse_namespace(command, session=session, state_dir=store.state_dir, **kwargs)

            # start
            self.assertEqual(mod.run(make_args("start")), 0)
            # set_params
            params = json.dumps({
                "topic": "人工智能与劳动分配",
                "min_sources": 12,
                "keywords_zh": ["人工智能", "劳动分配"],
                "keywords_en": ["artificial intelligence", "labor allocation"],
            }, ensure_ascii=False)
            self.assertEqual(mod.run(make_args("set_params", params_json=params)), 0)
            # done
            self.assertEqual(
                mod.run(make_args("done", report=SAMPLE, min_sources=12)),
                0,
                msg="done step failed — validate_report likely not reachable",
            )
            # check
            self.assertEqual(mod.run(make_args("check")), 0)

            data = store.load(session)
            self.assertEqual(data["phase"], "DONE")
            self.assertTrue(data["report_validation"]["sha256"])


def argparse_namespace(command: str, **kwargs) -> object:
    """Tiny argparse.Namespace replacement (avoid importing argparse at
    module top just for this)."""
    ns = type("Args", (), {})()
    ns.command = command
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


if __name__ == "__main__":
    unittest.main()
