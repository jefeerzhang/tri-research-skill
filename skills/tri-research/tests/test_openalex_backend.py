"""OpenAlex Machine Backend (issue #31).

Seams (agreed in the spec): ``Backend.search`` / ``Backend.probe`` through the
shared CLI skeleton and the Registry, with a fake client standing in for HTTP.
The default suite never touches ``api.openalex.org``.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _search_cli  # noqa: E402
import search_backends  # noqa: E402

OPENALEX = search_backends.OPENALEX_BACKEND


class FakeOpenAlexClient:
    """Records the query params a real client would send; returns canned JSON."""

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload if payload is not None else {"results": []}
        self.calls: list[dict] = []

    def get_works(self, params: dict) -> dict:
        self.calls.append(dict(params))
        return self.payload


def _work(**overrides) -> dict:
    work = {
        "id": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.7717/peerj.4375",
        "display_name": "The state of OA",
        "publication_date": "2018-02-13",
        "relevance_score": 42.5,
        "cited_by_count": 777,
        "open_access": {"is_oa": True},
        "primary_location": {"landing_page_url": "https://peerj.com/articles/4375"},
        "abstract_inverted_index": {"Despite": [0], "growing": [1], "interest": [2]},
    }
    work.update(overrides)
    return work


class SearchResultMappingTests(unittest.TestCase):
    def search(self, work: dict, query: str = "open access") -> dict:
        client = FakeOpenAlexClient({"results": [work]})
        return OPENALEX.search(client, query, {})

    def test_hit_is_normalized_to_the_shared_result_shape(self) -> None:
        hit = self.search(_work())["results"][0]
        self.assertEqual(hit["title"], "The state of OA")
        self.assertEqual(hit["url"], "https://peerj.com/articles/4375")
        self.assertEqual(hit["snippet"], "Despite growing interest")
        self.assertEqual(hit["published_date"], "2018-02-13")
        self.assertEqual(hit["score"], 42.5)
        self.assertEqual(
            hit["engine_meta"],
            {
                "openalex_id": "https://openalex.org/W2741809807",
                "doi": "https://doi.org/10.7717/peerj.4375",
                "cited_by_count": 777,
                "is_oa": True,
            },
        )


    def test_url_falls_back_landing_page_then_doi_then_openalex_id(self) -> None:
        no_landing = _work(primary_location={"landing_page_url": None})
        self.assertEqual(self.search(no_landing)["results"][0]["url"], "https://doi.org/10.7717/peerj.4375")
        bare = _work(primary_location=None, doi=None)
        self.assertEqual(self.search(bare)["results"][0]["url"], "https://openalex.org/W2741809807")

    def test_snippet_falls_back_to_title_without_abstract(self) -> None:
        hit = self.search(_work(abstract_inverted_index=None))["results"][0]
        self.assertEqual(hit["snippet"], "The state of OA")

    def test_abstract_is_rebuilt_in_word_order(self) -> None:
        index = {"world": [1, 3], "hello": [0, 2]}
        hit = self.search(_work(abstract_inverted_index=index))["results"][0]
        self.assertEqual(hit["snippet"], "hello world hello world")


class SearchParamsTests(unittest.TestCase):
    def sent(self, query: str = "labor", **options) -> dict:
        client = FakeOpenAlexClient()
        OPENALEX.search(client, query, options)
        return client.calls[0]

    def test_query_goes_to_the_search_parameter(self) -> None:
        self.assertEqual(self.sent("AI 就业")["search"], "AI 就业")

    def test_num_results_maps_to_per_page_within_the_api_bounds(self) -> None:
        self.assertEqual(self.sent(num_results=7)["per_page"], 7)
        self.assertEqual(self.sent(num_results=500)["per_page"], 100)
        self.assertEqual(self.sent(num_results=0)["per_page"], 1)

    def test_year_range_oa_and_type_combine_into_one_filter(self) -> None:
        params = self.sent(from_year=2020, to_year=2024, open_access=True, work_type="article")
        self.assertEqual(
            sorted(params["filter"].split(",")),
            [
                "from_publication_date:2020-01-01",
                "is_oa:true",
                "to_publication_date:2024-12-31",
                "type:article",
            ],
        )

    def test_no_filter_parameter_when_no_filter_flags(self) -> None:
        self.assertNotIn("filter", self.sent())
        self.assertNotIn("filter", self.sent(open_access=False))


def run_cli(argv: list[str]) -> tuple[dict, int]:
    buf = io.StringIO()
    code = 0
    with redirect_stdout(buf):
        try:
            code = int(_search_cli.run(OPENALEX, argv) or 0)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return json.loads(buf.getvalue()), code


class KeylessEnvMixin:
    """No OPENALEX_* in env, and a ``.env`` that cannot exist on this machine."""

    def setUp(self) -> None:
        super().setUp()
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for var in ("OPENALEX_API_KEY", "OPENALEX_MAILTO"):
            os.environ.pop(var, None)
        missing_env = mock.patch.object(OPENALEX, "env_file", Path(__file__).parent / "_no_such_dir" / ".env")
        missing_env.start()
        self.addCleanup(missing_env.stop)


class AnonymousAccessTests(KeylessEnvMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.keys_seen: list[str] = []
        self.client = FakeOpenAlexClient({"results": [_work()]})

        def factory(key: str) -> FakeOpenAlexClient:
            self.keys_seen.append(key)
            return self.client

        patcher = mock.patch.object(OPENALEX, "client_factory", factory)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_check_reports_available_without_a_key(self) -> None:
        out, code = run_cli(["check"])
        self.assertEqual((out, code), ({"available": True}, 0))

    def test_search_succeeds_without_a_key(self) -> None:
        out, code = run_cli(["search", "open access"])
        self.assertEqual(code, 0)
        self.assertEqual(out["query"], "open access")
        self.assertEqual(out["results"][0]["url"], "https://peerj.com/articles/4375")
        self.assertEqual(self.keys_seen, [""])

    def test_batch_search_succeeds_without_a_key(self) -> None:
        out, code = run_cli(["batch_search", "--query", "a", "--query", "b"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out), ["a", "b"])
        self.assertEqual(out["a"][0]["title"], "The state of OA")

    def test_cli_filter_flags_reach_the_request(self) -> None:
        run_cli(["search", "q", "--from-year", "2020", "--open-access", "--num-results", "3"])
        params = self.client.calls[0]
        self.assertEqual(params["per_page"], 3)
        self.assertEqual(sorted(params["filter"].split(",")), ["from_publication_date:2020-01-01", "is_oa:true"])

    def test_global_no_proxy_flag_clears_proxy_env_for_the_run(self) -> None:
        os.environ["HTTPS_PROXY"] = "http://proxy.invalid:8080"
        out, code = run_cli(["--no-proxy", "check"])
        self.assertEqual((out, code), ({"available": True}, 0))
        self.assertNotIn("HTTPS_PROXY", os.environ)

    def test_key_from_env_is_handed_to_the_client(self) -> None:
        os.environ["OPENALEX_API_KEY"] = "env-key"
        run_cli(["search", "q"])
        self.assertEqual(self.keys_seen, ["env-key"])


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class HttpClientTests(KeylessEnvMixin, unittest.TestCase):
    """The real client's wire contract, with ``urlopen`` stubbed."""

    def make_client(self, key: str = ""):
        return OPENALEX.client_factory(key)

    def requests_for(self, key: str = "") -> list:
        sent: list = []

        def fake_urlopen(request, timeout=None):
            sent.append(request)
            return FakeResponse({"results": []})

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            self.make_client(key).get_works({"search": "AI 就业", "per_page": 5})
        return sent

    def test_anonymous_request_hits_works_search_without_credentials(self) -> None:
        (request,) = self.requests_for()
        self.assertTrue(request.full_url.startswith("https://api.openalex.org/works?"))
        self.assertIn("search=AI+%E5%B0%B1%E4%B8%9A", request.full_url)
        self.assertIn("per_page=5", request.full_url)
        self.assertNotIn("api_key", request.full_url)
        self.assertIsNone(request.get_header("Authorization"))

    def test_key_is_sent_as_a_bearer_token_not_in_the_url(self) -> None:
        (request,) = self.requests_for("secret-key")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertNotIn("secret-key", request.full_url)

    def test_mailto_from_env_identifies_the_caller(self) -> None:
        os.environ["OPENALEX_MAILTO"] = "me@example.org"
        (request,) = self.requests_for()
        self.assertIn("mailto=me%40example.org", request.full_url)

    def test_rate_limit_429_is_retried_through_the_shared_skeleton(self) -> None:
        import urllib.error

        calls: list[int] = []

        def flaky_urlopen(request, timeout=None):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
            return FakeResponse({"results": [_work()]})

        client = self.make_client()
        with mock.patch("urllib.request.urlopen", flaky_urlopen), mock.patch.object(OPENALEX, "retry_backoff", 0.0):
            out = _search_cli.invoke(OPENALEX, lambda: OPENALEX.search(client, "q", {}))
        self.assertEqual(len(calls), 2)
        self.assertEqual(out["num_results"], 1)

    def test_client_error_is_not_retried(self) -> None:
        import urllib.error

        calls: list[int] = []

        def bad_request(request, timeout=None):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

        client = self.make_client()
        with mock.patch("urllib.request.urlopen", bad_request), mock.patch.object(OPENALEX, "retry_backoff", 0.0):
            with self.assertRaises(RuntimeError) as ctx:
                _search_cli.invoke(OPENALEX, lambda: OPENALEX.search(client, "q", {}))
        self.assertEqual(len(calls), 1)
        self.assertIn("HTTP 400", str(ctx.exception))


class RegistryWiringTests(KeylessEnvMixin, unittest.TestCase):
    def test_registered_as_a_machine_backend(self) -> None:
        from _search_registry import REGISTRY

        self.assertIn("openalex", REGISTRY.list_backends())
        self.assertIs(REGISTRY.get("openalex").backend, OPENALEX)
        self.assertEqual(OPENALEX.env_key, "OPENALEX_API_KEY")

    def test_registry_search_returns_uniform_results_without_a_key(self) -> None:
        from _search_registry import REGISTRY

        client = FakeOpenAlexClient({"results": [_work()]})
        with mock.patch.object(OPENALEX, "client_factory", lambda key: client):
            results = REGISTRY.search("openalex", "open access", {"num_results": 2})
        (hit,) = results
        self.assertEqual(hit.title, "The state of OA")
        self.assertEqual(hit.url, "https://peerj.com/articles/4375")
        self.assertEqual(hit.score, 42.5)
        self.assertEqual(hit.published_date, "2018-02-13")
        self.assertEqual(hit.engine_meta["cited_by_count"], 777)
        self.assertEqual(client.calls[0]["per_page"], 2)

    def test_registry_check_is_available_without_a_key(self) -> None:
        from _search_registry import REGISTRY

        with mock.patch.object(OPENALEX, "client_factory", lambda key: FakeOpenAlexClient()):
            self.assertEqual(REGISTRY.check("openalex"), {"available": True})


class OpenAlexLedgerBindTests(KeylessEnvMixin, unittest.TestCase):
    """Issue #32: research-path ``--session`` writes ``seen`` rows as OpenAlex."""

    def setUp(self) -> None:
        super().setUp()
        import tempfile

        import state_machine

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "state"
        self.state_dir.mkdir()
        self.store = state_machine.StateStore(self.state_dir)
        with mock.patch.object(state_machine, "require_required_backends", lambda: None):
            self.store.start_session("oa-sess")
        self.client = FakeOpenAlexClient({"results": [_work()]})
        factory = mock.patch.object(OPENALEX, "client_factory", lambda key: self.client)
        factory.start()
        self.addCleanup(factory.stop)

    def records(self, session: str = "oa-sess") -> list[dict]:
        path = self.state_dir / f"{session}.evidence.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def search(self, extra: list[str], *, session: str | None = "oa-sess") -> tuple[dict, int]:
        argv = ["search", "open access"]
        if session:
            argv.extend(["--session", session, "--state-dir", str(self.state_dir)])
        argv.extend(extra)
        return run_cli(argv)

    def test_search_with_session_writes_openalex_seen_row(self) -> None:
        out, code = self.search([])
        self.assertEqual(code, 0, out)
        (row,) = self.records()
        self.assertEqual(row["kind"], "seen")
        self.assertEqual(row["backend"], "OpenAlex")
        self.assertEqual(row["query"], "open access")
        self.assertEqual(row["url"], "https://peerj.com/articles/4375")
        self.assertEqual(row["title"], "The state of OA")
        self.assertIn("ts", row)

    def test_batch_search_with_session_writes_each_query(self) -> None:
        out, code = run_cli(
            [
                "batch_search",
                "--query",
                "q1",
                "--query",
                "q2",
                "--session",
                "oa-sess",
                "--state-dir",
                str(self.state_dir),
            ]
        )
        self.assertEqual(code, 0, out)
        rows = self.records()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["query"] for r in rows}, {"q1", "q2"})
        self.assertTrue(all(r["backend"] == "OpenAlex" for r in rows))

    def test_without_session_does_not_write_ledger(self) -> None:
        out, code = self.search([], session=None)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.state_dir / "oa-sess.evidence.jsonl").exists())

    def test_unknown_session_fails_closed(self) -> None:
        out, code = self.search([], session="ghost")
        self.assertNotEqual(code, 0)
        self.assertIn("evidence ledger write failed", out["error"])
        self.assertEqual(self.records("ghost"), [])

    def test_empty_hits_succeed_without_ledger_file(self) -> None:
        self.client.payload = {"results": []}
        out, code = self.search([])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.records(), [])


class CliEntryPointTests(unittest.TestCase):
    def test_script_exposes_search_with_openalex_flags(self) -> None:
        import subprocess

        script = SCRIPT_DIR / "openalex_search.py"
        result = subprocess.run(
            [sys.executable, str(script), "search", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ("--from-year", "--to-year", "--open-access", "--type", "--session"):
            self.assertIn(flag, result.stdout)


if __name__ == "__main__":
    unittest.main()
