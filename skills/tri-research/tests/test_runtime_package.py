"""ADR-0015: the shared runtime is an importable package, not a path hack."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

TRI_ROOT = Path(__file__).parents[1]
REPO_ROOT = TRI_ROOT.parents[1]
RUNTIME_SRC = TRI_ROOT / "src"
SERPAPI_CLI = TRI_ROOT.parent / "serpapi" / "scripts" / "serpapi_cli.py"
_SCRIPTS = str(TRI_ROOT / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
_SRC = str(RUNTIME_SRC)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


class RuntimePackageTests(unittest.TestCase):
    def test_package_exports_backend_keyprovider_and_state_error(self) -> None:
        import tri_research_runtime as runtime
        import _common
        import _search_cli
        import _search_registry

        self.assertTrue(hasattr(runtime, "Backend"))
        self.assertTrue(hasattr(runtime, "KeyProvider"))
        self.assertTrue(hasattr(runtime, "StateError"))
        self.assertTrue(hasattr(runtime, "SNIPPET_LIMIT"))
        self.assertTrue(hasattr(runtime, "CITATION_TEXT_LIMIT"))
        self.assertTrue(hasattr(runtime, "EXTRACT_CONTENT_LIMIT"))

        self.assertIs(runtime.StateError, _common.StateError)
        self.assertIs(runtime.KeyProvider, _search_registry.KeyProvider)
        self.assertIs(runtime.Backend, _search_cli.Backend)

    def test_pyproject_points_at_skill_src(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "tri-research-runtime"', text)
        self.assertIn('where = ["skills/tri-research/src"]', text)

    def test_serpapi_imports_the_package_not_loose_search_cli(self) -> None:
        source = SERPAPI_CLI.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertIn("tri_research_runtime", imported)
        self.assertNotIn("_search_cli", imported)

    def test_key_provider_source_knows_no_skill_layout(self) -> None:
        text = (RUNTIME_SRC / "tri_research_runtime" / "key_provider.py").read_text(encoding="utf-8")
        self.assertNotIn("serpapi", text.lower())
        self.assertNotIn("tri-research", text.lower())
        self.assertNotIn("parents[", text)


if __name__ == "__main__":
    unittest.main()
