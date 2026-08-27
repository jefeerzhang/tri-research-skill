"""Wiring tests for ticket #7 — Exa/Tavily via Registry.

- Registry must expose exa/tavily after search_backends import
- Thin shims keep legacy JSON shape (checked via existing tests, plus spot check)
- Registry batch still returns uniform per-query list/error shape
- Global --no-proxy flag is present on both backends
"""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _search_registry import REGISTRY  # noqa: E402
import search_backends  # noqa: E402,F401 — triggers REGISTRY registration for exa/tavily


class RegistryWiringTests(unittest.TestCase):
    def test_exa_and_tavily_registered(self) -> None:
        backs = REGISTRY.list_backends()
        self.assertIn("exa", backs)
        self.assertIn("tavily", backs)
        self.assertEqual(REGISTRY.get("exa").env_key, "EXA_API_KEY")
        self.assertEqual(REGISTRY.get("tavily").env_key, "TAVILY_API_KEY")

    def test_global_no_proxy_flag_present(self) -> None:
        for name in ("exa", "tavily"):
            spec = REGISTRY.get(name)
            flags = list(spec.backend.global_flags)  # type: ignore[attr-defined]
            self.assertTrue(any(f.dest == "no_proxy" for f in flags), f"{name} missing --no-proxy")

    def test_batch_uniform_shape_via_registry_fake(self) -> None:
        # Use registry's own batch with a fake backend to prove uniform shape
        from _search_registry import BackendSpec, SearchBackendRegistry
        import _search_cli

        class Fake(_search_cli.Backend):
            name = "Fake2"
            help = "fake2"
            sdk = object()
            missing_sdk_message = "x"
            env_key = "FAKE2_KEY"
            client_factory = staticmethod(lambda k: object())
            flags = ()

            def probe(self, client):  # type: ignore[override]
                return True

            def search(self, client, query, options):  # type: ignore[override]
                if query == "bad":
                    raise RuntimeError("HTTP 400 Bad Request")
                return {"results": [{"title": "ok", "url": "https://example.com"}]}

        reg = SearchBackendRegistry()
        reg.register(BackendSpec(name="fake2", backend=Fake(), env_key="FAKE2_KEY"))
        import os

        os.environ["FAKE2_KEY"] = "k"
        try:
            out = reg.batch_search("fake2", ["bad", "good"])
            self.assertIn("error", out["bad"])  # type: ignore[typeddict-item]
            self.assertIsInstance(out["good"], list)
        finally:
            os.environ.pop("FAKE2_KEY", None)
