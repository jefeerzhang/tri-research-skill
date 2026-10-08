"""ADR-0015: the shared runtime is an importable package, not a path hack."""

from __future__ import annotations

import ast
import re
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

    def test_package_exports_the_shared_clock(self) -> None:
        """候选 5：``now_iso`` 是共享时钟原语，其家与格式都只有一个。

        它此前住在 ``scripts/_common.py``（一个以报告来源下限自述的模块），
        调用方无从预期。现在与 errors / 截断上限并列，并在此钉住格式。
        """
        import tri_research_runtime as runtime

        self.assertTrue(hasattr(runtime, "now_iso"), "运行时包未导出 now_iso")
        stamp = runtime.now_iso()
        # UTC ISO-8601，分钟精度：YYYY-MM-DDTHH:MM+00:00
        self.assertRegex(stamp, re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+00:00$"), stamp)

        import _common

        self.assertFalse(
            hasattr(_common, "now_iso"),
            "_common 不应再持有 now_iso：时钟的家是 tri_research_runtime.clock",
        )

    def test_package_search_cli_declares_one_named_interface(self) -> None:
        """候选 7：包模块必须有 ``__all__``。

        没有它，``import *`` 把 stdlib 与 typing 一并当接口泄露出去——实测
        shim 曾暴露 45 个公开名，其中 16 个是 ``argparse`` / ``json`` /
        ``threading`` / ``Path`` / ``TypeVar`` 之类。
        """
        from tri_research_runtime import search_cli as pkg

        self.assertTrue(hasattr(pkg, "__all__"), "tri_research_runtime.search_cli 缺少 __all__")
        self.assertTrue(pkg.__all__, "__all__ 不得为空")
        missing = [name for name in pkg.__all__ if not hasattr(pkg, name)]
        self.assertEqual(missing, [], f"__all__ 列了但模块没有的名字: {missing}")
        self.assertEqual(sorted(pkg.__all__), sorted(set(pkg.__all__)), "__all__ 不得有重复项")

    def test_shim_exposes_exactly_the_package_interface(self) -> None:
        """shim 只做两件事：引导 + 转交。接口的家是包的 ``__all__``。

        此前 shim 把同一接口声明两次（``import *`` 加一份手写清单），两处都没有
        权威性，而手写那份已经漂移过一次。
        """
        from tri_research_runtime import search_cli as pkg

        import _search_cli

        exported = {name for name in dir(_search_cli) if not name.startswith("_")}
        exported.discard("annotations")  # `from __future__ import annotations`
        self.assertEqual(
            exported,
            set(pkg.__all__),
            "shim 的导出面必须恰好等于包的 __all__（既不得多出 stdlib，也不得少）",
        )

    def test_every_shim_attribute_used_in_repo_is_declared(self) -> None:
        """仓库里实际用到的 ``_search_cli`` 属性访问，必须已在 ``__all__`` 声明。

        枚举式闸门（与 test_host_helpers 同类）：接口不能在没有调用点察觉的情况下
        被缩小。此前 shim 的手写清单已漂移过一次——``batch_search`` 被调用却没写
        进清单，只靠 ``import *`` 侥幸可用。
        """
        from tri_research_runtime import search_cli as pkg

        pattern = re.compile(r"_search_cli\.([A-Za-z_][A-Za-z0-9_]*)")
        folders = (TRI_ROOT / "scripts", TRI_ROOT.parent / "serpapi" / "scripts", TRI_ROOT / "tests")

        used: set[str] = set()
        for folder in folders:
            for path in sorted(folder.glob("*.py")):
                for match in pattern.finditer(path.read_text(encoding="utf-8")):
                    used.add(match.group(1))
        used.discard("py")  # 文件名 `_search_cli.py` 的后缀，不是属性

        undeclared = sorted(used - set(pkg.__all__))
        self.assertEqual(undeclared, [], f"这些属性在用但未在 __all__ 声明: {undeclared}")


if __name__ == "__main__":
    unittest.main()
