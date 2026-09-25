"""Required Backend gate (Exa + SciVerse K+S; SerpApi Key + probe).

Seam: ``require_required_backends`` and ``StateStore.start_session`` behavior
when the gate fails (no session / active pointer written). ADR-0011: the
gate walks ``requirement=required`` descriptors; changing a backend's
``requirement`` field is enough to include or exclude it.
"""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _test_helpers import load_module, patch_required_backends

import _search_cli  # noqa: E402 — _test_helpers puts scripts/ on sys.path
from _search_cli import BackendRequirementLevel  # noqa: E402
from search_backends import EXA_BACKEND, TAVILY_BACKEND  # noqa: E402

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"


class _FakeSerpApiBackend(_search_cli.Backend):
    """Minimal stand-in for SerpApiBackend, used to isolate the gate seam.

    `_get_serpapi_backend` is patched to return one of these so the real
    ``serpapi_cli`` is never imported and the probe never touches the network.
    Subclassing the shared ``Backend`` is deliberate: the gate assembles the
    client through ``Backend.client()``, so a duck-typed stand-in would drift
    from what production actually does.
    """

    name = "SerpApi"
    env_key = "SERPAPI_KEY"
    env_file = Path("serpapi.env")
    sdk = object()  # truthy → treat as "requests" installed
    missing_sdk_message = "requests not installed"
    call_timeout = 60.0
    requirement = BackendRequirementLevel.REQUIRED
    start_probe = True
    apply_url = "https://serpapi.com/dashboard"
    verify_cmd = "python skills/serpapi/scripts/serpapi_cli.py check"
    configure_hint = f"export {env_key}=<key> ({apply_url})"

    def __init__(self, probe_return: bool = True, probe_error: Exception | None = None, sdk: object = object()) -> None:
        self._probe_return = probe_return
        self._probe_error = probe_error
        self.sdk = sdk

    def client_factory(self, _api_key: str) -> object:
        return object()

    def probe(self, _client: object) -> bool:
        if self._probe_error is not None:
            raise self._probe_error
        return self._probe_return


class RequiredBackendsGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rb = load_module(SCRIPTS_DIR / "required_backends.py", "required_backends_gate_test")
        self.serpapi = _FakeSerpApiBackend()
        self._serpapi_patch = mock.patch.object(self.rb, "_get_serpapi_backend", return_value=self.serpapi)
        self._serpapi_patch.start()
        self.addCleanup(self._serpapi_patch.stop)
        # Exa readiness now goes through Backend.client(); without a real
        # exa_py the singleton's sdk is None. Pin a dummy so key-only tests
        # are not short-circuited by SdkMissing.
        self._exa_sdk_patch = mock.patch.object(EXA_BACKEND, "sdk", object())
        self._exa_sdk_patch.start()
        self.addCleanup(self._exa_sdk_patch.stop)

    def test_ready_when_keys_and_sdks_present(self) -> None:
        with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
            with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                self.rb.require_required_backends()  # does not raise

    def test_missing_exa_key_raises(self) -> None:
        def resolve(_cli, env_key, _env_file=None):
            # Only Exa missing; SciVerse + SerpApi resolve ok.
            return None if env_key == EXA_BACKEND.env_key else "k"

        with mock.patch.object(self.rb.KeyProvider, "resolve", side_effect=resolve):
            with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("EXA_API_KEY not set", msg)
        self.assertIn("dashboard.exa.ai", msg)

    def test_missing_sciverse_sdk_raises(self) -> None:
        def importable(name: str) -> bool:
            return name != self.rb.SCIVERSE_READINESS.sdk_module

        with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
            with mock.patch.object(self.rb, "_sdk_importable", side_effect=importable):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        self.assertIn("sciverse SDK not installed", str(ctx.exception))
        self.assertIn("sciverse.space/docs#auth", str(ctx.exception))

    def test_missing_serpapi_key_raises(self) -> None:
        def resolve(_cli, env_key, _env_file=None):
            # SerpApi key missing; Exa + SciVerse resolve ok.
            return None if env_key == self.serpapi.env_key else "k"

        with mock.patch.object(self.rb.KeyProvider, "resolve", side_effect=resolve):
            with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("SERPAPI_KEY not set", msg)
        self.assertIn("serpapi.com/dashboard", msg)
        # User story: failure names where to apply + how to verify.
        self.assertIn("verify:", msg)
        self.assertIn("serpapi_cli.py", msg)

    def test_serpapi_probe_failure_raises(self) -> None:
        with mock.patch.object(
            self.rb,
            "_get_serpapi_backend",
            return_value=_FakeSerpApiBackend(probe_error=RuntimeError("HTTP 401: API key not valid")),
        ):
            with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
                with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                    with self.assertRaises(self.rb.StateError) as ctx:
                        self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("SerpApi: probe failed", msg)
        self.assertIn("HTTP 401", msg)

    def test_serpapi_probe_false_raises(self) -> None:
        with mock.patch.object(self.rb, "_get_serpapi_backend", return_value=_FakeSerpApiBackend(probe_return=False)):
            with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
                with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                    with self.assertRaises(self.rb.StateError) as ctx:
                        self.rb.require_required_backends()
        self.assertIn("SerpApi: probe failed", str(ctx.exception))

    def test_serpapi_sdk_missing_raises(self) -> None:
        # SerpApi's "SDK" is `requests`; when absent the gate must name the SDK gap.
        with mock.patch.object(self.rb, "_get_serpapi_backend", return_value=_FakeSerpApiBackend(sdk=None)):
            with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
                with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                    with self.assertRaises(self.rb.StateError) as ctx:
                        self.rb.require_required_backends()
        self.assertIn("SerpApi: requests not installed", str(ctx.exception))

    def test_serpapi_skill_not_importable_is_a_gap_not_traceback(self) -> None:
        # A missing / broken sibling skill is a readiness gap like any other:
        # `start` must answer with the ERROR: line, not a ModuleNotFoundError
        # traceback, and it must still report the other backends' checks.
        with mock.patch.object(
            self.rb, "_get_serpapi_backend", side_effect=ImportError("No module named 'serpapi_cli'")
        ):
            with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
                with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                    with self.assertRaises(self.rb.StateError) as ctx:
                        self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("SerpApi: skill not importable", msg)
        self.assertIn("serpapi_cli", msg)
        self.assertIn("serpapi.com/dashboard", msg)  # the guide still names where to apply

    def test_lists_all_gaps_in_one_error(self) -> None:
        with mock.patch.object(EXA_BACKEND, "sdk", None):
            with mock.patch.object(self.rb.KeyProvider, "resolve", return_value=None):
                with mock.patch.object(self.rb, "_sdk_importable", return_value=False):
                    with self.assertRaises(self.rb.StateError) as ctx:
                        self.rb.require_required_backends()
        msg = str(ctx.exception)
        # Exa goes through client(): SDK missing short-circuits before the key.
        self.assertIn("exa-py not installed", msg)
        self.assertIn("SCIVERSE_API_TOKEN not set", msg)
        self.assertIn("sciverse SDK not installed", msg)
        self.assertIn("SERPAPI_KEY not set", msg)

    def test_backend_requirement_contract_is_declarative(self) -> None:
        cli = load_module(SCRIPTS_DIR / "_search_cli.py", "search_cli_requirement_contract")
        self.assertEqual(
            [level.value for level in cli.BackendRequirementLevel], ["required", "recommended", "optional"]
        )
        backend = cli.Backend()
        self.assertEqual(backend.requirement, cli.BackendRequirementLevel.OPTIONAL)
        self.assertEqual(backend.readiness(), [])

    def test_declared_required_backends_are_collected_through_readiness(self) -> None:
        cli = load_module(SCRIPTS_DIR / "_search_cli.py", "search_cli_required_collection")
        required = cli.BackendRequirementLevel.REQUIRED
        ready = mock.Mock(name="ready")
        ready.name = "Ready"
        ready.requirement = required
        ready.readiness.return_value = []
        broken = mock.Mock(name="broken")
        broken.name = "Broken"
        broken.requirement = required
        broken.readiness.return_value = ["Broken: unavailable"]
        with mock.patch.object(self.rb, "declared_backends", return_value=[ready, broken]):
            with mock.patch.object(self.rb.SCIVERSE_READINESS, "readiness", return_value=[]):
                with self.assertRaises(self.rb.StateError) as ctx:
                    self.rb.require_required_backends()
        msg = str(ctx.exception)
        self.assertIn("Broken: unavailable", msg)
        # The guide names every required descriptor, not just the broken ones.
        self.assertIn("Ready:", msg)
        ready.readiness.assert_called_once()

    def test_machine_backends_declare_requirement_levels(self) -> None:
        backends = load_module(SCRIPTS_DIR / "search_backends.py", "search_backends_requirement_contract")
        cli = load_module(SCRIPTS_DIR / "_search_cli.py", "search_cli_requirement_levels")
        self.assertEqual(backends.EXA_BACKEND.requirement, cli.BackendRequirementLevel.REQUIRED)
        self.assertEqual(backends.TAVILY_BACKEND.requirement, cli.BackendRequirementLevel.OPTIONAL)


class RequiredDescriptorsDataDrivenTests(unittest.TestCase):
    """Adding or changing ``requirement`` is a data change, not a walker edit."""

    def setUp(self) -> None:
        self.rb = load_module(SCRIPTS_DIR / "required_backends.py", "required_backends_data_driven")
        self._serpapi_patch = mock.patch.object(self.rb, "_get_serpapi_backend", return_value=_FakeSerpApiBackend())
        self._serpapi_patch.start()
        self.addCleanup(self._serpapi_patch.stop)

    def test_required_names_are_exa_serpapi_sciverse(self) -> None:
        names = tuple(d.name for d in self.rb.iter_required_descriptors())
        self.assertEqual(names, ("Exa", "SerpApi", "SciVerse"))

    def test_tavily_is_on_the_list_but_optional(self) -> None:
        all_names = tuple(d.name for d in self.rb.iter_readiness_descriptors())
        self.assertIn("Tavily", all_names)
        self.assertEqual(TAVILY_BACKEND.requirement, BackendRequirementLevel.OPTIONAL)
        self.assertNotIn("Tavily", tuple(d.name for d in self.rb.iter_required_descriptors()))

    def test_anysearch_is_not_a_machine_descriptor(self) -> None:
        names = {d.name for d in self.rb.iter_readiness_descriptors()}
        self.assertNotIn("AnySearch", names)

    def test_sciverse_is_not_in_the_registry(self) -> None:
        from _search_registry import REGISTRY

        self.assertNotIn("sciverse", [n.lower() for n in REGISTRY.list_backends()])
        self.assertIn("SciVerse", tuple(d.name for d in self.rb.iter_required_descriptors()))
        self.assertIs(self.rb.iter_required_descriptors()[-1], self.rb.SCIVERSE_READINESS)

    def test_promoting_optional_backend_joins_the_gate(self) -> None:
        original = TAVILY_BACKEND.requirement
        original_sdk = TAVILY_BACKEND.sdk
        TAVILY_BACKEND.requirement = BackendRequirementLevel.REQUIRED
        TAVILY_BACKEND.sdk = None
        try:
            self.assertIn("Tavily", tuple(d.name for d in self.rb.iter_required_descriptors()))
            with mock.patch.object(EXA_BACKEND, "sdk", object()):
                with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
                    with mock.patch.object(self.rb, "_sdk_importable", return_value=True):
                        with self.assertRaises(self.rb.StateError) as ctx:
                            self.rb.require_required_backends()
            self.assertIn("Tavily", str(ctx.exception))
        finally:
            TAVILY_BACKEND.requirement = original
            TAVILY_BACKEND.sdk = original_sdk

    def test_demoting_required_backend_leaves_the_gate(self) -> None:
        original = EXA_BACKEND.requirement
        EXA_BACKEND.requirement = BackendRequirementLevel.OPTIONAL
        try:
            names = tuple(d.name for d in self.rb.iter_required_descriptors())
            self.assertNotIn("Exa", names)
        finally:
            EXA_BACKEND.requirement = original

    def test_exa_readiness_shares_client_setup_judgment(self) -> None:
        with mock.patch.object(EXA_BACKEND, "sdk", None):
            self.assertEqual(EXA_BACKEND.readiness(), ["Exa: exa-py not installed"])
        with mock.patch.object(EXA_BACKEND, "sdk", object()):
            with mock.patch.object(self.rb.KeyProvider, "resolve", return_value=None):
                self.assertEqual(EXA_BACKEND.readiness(), ["Exa: EXA_API_KEY not set"])
            with mock.patch.object(EXA_BACKEND, "client_factory") as factory:
                with mock.patch.object(self.rb.KeyProvider, "resolve", return_value="k"):
                    self.assertEqual(EXA_BACKEND.readiness(), [])
                factory.assert_not_called()

    def test_gate_source_does_not_hand_roll_exa_ks(self) -> None:
        source = (SCRIPTS_DIR / "required_backends.py").read_text(encoding="utf-8")
        self.assertNotIn("ALLOW_DEGRADED", source)
        self.assertNotIn("EXA_SDK", source)
        self.assertNotIn('find_spec("exa_py")', source)
        # Pin the *call site*, not just the definition: a gate that re-filters
        # declared_backends() by hand would keep this file's text passing while
        # bypassing the descriptor view ADR-0011 makes authoritative.
        gate = inspect.getsource(self.rb.require_required_backends)
        self.assertIn("iter_required_descriptors()", gate)
        self.assertNotIn("BackendRequirementLevel", gate)


class StartSessionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sm = load_module(SCRIPTS_DIR / "state_machine.py", "sm_required_gate_test")
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.state_dir = Path(self.tmp.name) / "state"
        self.store = self.sm.StateStore(self.state_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_start_fails_without_writing_session(self) -> None:
        with mock.patch.object(
            self.sm,
            "require_required_backends",
            side_effect=self.sm.StateError("required backends not ready: test"),
        ):
            with self.assertRaises(self.sm.StateError):
                self.store.start_session("blocked")
        self.assertFalse((self.state_dir / "blocked.json").exists())
        self.assertFalse((self.state_dir / "active-session").exists())

    def test_start_succeeds_when_gate_patched(self) -> None:
        with patch_required_backends(self.sm):
            data = self.store.start_session("ok-session")
        self.assertEqual(data["phase"], "STARTED")
        self.assertTrue((self.state_dir / "ok-session.json").exists())


if __name__ == "__main__":
    unittest.main()
