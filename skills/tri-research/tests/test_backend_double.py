"""One Backend test double, and no test may restate a production default.

候选 9. The architectural review rated the doubled ``Backend`` test doubles
"Speculative" — six modules each declare their own subclass. Reading them
side by side shows the duplication is not cosmetic: it has already drifted
into the exact silent-drift class this repo keeps closing.

* Six modules re-declare the same optional wiring (``sdk = object()``,
  ``missing_sdk_message``, ``flags = ()``, ``probe``/``search`` bodies).
* Six of those assignments restate a value that is **already** the production
  default: ``max_attempts = 3`` (×3), ``circuit_threshold = 5`` (×2),
  ``circuit_cooldown = 60.0`` (×2). Nothing reads them — the tests that care
  set the value on the *instance* (``_registry_with_fake(circuit_threshold=2)``).
  So they are pure copies of a number that lives in ``Backend``: change the
  production default and these doubles keep exercising the old one.

The fix is one shared base with a narrow declaration. It sets only the two
knobs a test *must* override — ``retry_backoff`` and ``call_timeout``, or the
suite would sleep 0.5s per retry and hang 30s on a stuck double — and leaves
every other optional field at whatever ``Backend`` says, so a default change
reaches the tests instead of being shadowed.

The four single-adapter hooks (``search_handler`` and friends) are deliberately
left alone: ADR-0002 keeps SerpApi on its own dialect on purpose, so removing
them would reopen a recorded decision rather than clean up an accident.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TRI_SCRIPTS = TESTS_DIR.parent / "scripts"
if str(TRI_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TRI_SCRIPTS))

import _search_cli  # noqa: E402

from _test_helpers import SHARED_FAKE_BACKEND_NAME  # noqa: E402

# Optional tuning fields a double may legitimately want to override. These are
# read by the shared retry/circuit machinery, so "what is the default" is a
# question about ``Backend`` alone — a double restating it is a second home.
TUNING_FIELDS = (
    "max_attempts",
    "retry_backoff",
    "call_timeout",
    "circuit_threshold",
    "circuit_cooldown",
)


def _backend_doubles() -> list[tuple[str, ast.ClassDef]]:
    """Every class in the test suite that subclasses the shared ``Backend``."""
    found: list[tuple[str, ast.ClassDef]] = []
    for path in sorted(TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(getattr(base, "attr", None) == "Backend" for base in node.bases):
                found.append((path.name, node))
    return found


class SharedFakeBackendTests(unittest.TestCase):
    def test_the_shared_double_is_importable_and_usable(self) -> None:
        from _test_helpers import FakeBackend

        backend = FakeBackend()
        self.assertEqual(backend.name, "Fake")
        self.assertTrue(backend.probe(object()))
        self.assertEqual(backend.search(object(), "q", {}), {"results": []})
        self.assertIsInstance(backend, _search_cli.Backend)

    def test_the_shared_double_keeps_tests_fast(self) -> None:
        """The one thing a double must override: it may not wait on the clock.

        Production waits 0.5s between retries and 30s per call. A double that
        inherited those would turn a unit test into a sleep, so these two are
        the double's own values rather than copies of anything.
        """
        from _test_helpers import FakeBackend

        backend = FakeBackend()
        self.assertEqual(backend.retry_backoff, 0.0)
        self.assertEqual(backend.call_timeout, 5.0)
        self.assertLess(backend.retry_backoff, _search_cli.Backend.retry_backoff)
        self.assertLess(backend.call_timeout, _search_cli.Backend.call_timeout)

    def test_the_shared_double_declares_a_present_sdk(self) -> None:
        """``sdk = object()`` is a deliberate truthy stub, not a copy.

        ``Backend.require_setup`` short-circuits on ``sdk is None`` with
        SdkMissing, so a double that omitted it would test the SDK-missing
        branch instead of the branch it was written for.
        """
        from _test_helpers import FakeBackend

        backend = FakeBackend()
        self.assertIsNotNone(backend.sdk)
        self.assertTrue(backend.require_setup(cli_key="fake"))


class BackendDoubleConsolidationTests(unittest.TestCase):
    def test_every_double_derives_from_the_shared_base(self) -> None:
        """One Backend double. Subclasses declare only what they vary.

        Direct inheritance is the rule: a chain would reintroduce a second
        place where the optional wiring is spelled out.
        """
        offenders: list[str] = []
        for filename, node in _backend_doubles():
            if any(getattr(base, "id", None) == SHARED_FAKE_BACKEND_NAME for base in node.bases):
                continue
            offenders.append(f"{filename}::{node.name}")
        self.assertEqual(
            offenders,
            [],
            f"这些 Backend 替身没有直接继承 _test_helpers.{SHARED_FAKE_BACKEND_NAME}"
            f"（应继承它，只声明自己变化的部分）: {offenders}",
        )

    def test_no_double_restates_a_production_default(self) -> None:
        """The defect this file exists for: a copied number is a second home."""
        defaults = {name: getattr(_search_cli.Backend, name) for name in TUNING_FIELDS}
        offenders: list[str] = []
        for filename, node in _backend_doubles():
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for target in stmt.targets:
                    field = getattr(target, "id", None)
                    if field not in TUNING_FIELDS:
                        continue
                    try:
                        value = ast.literal_eval(stmt.value)
                    except ValueError:
                        continue  # a computed value is not a copy
                    if value == defaults[field]:
                        offenders.append(
                            f"{filename}::{node.name} 的 {field}={value!r} 与 Backend 默认相同（删掉它，让生产默认值直达测试）"
                        )
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
