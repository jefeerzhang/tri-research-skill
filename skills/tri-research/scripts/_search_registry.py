"""SearchBackendRegistry — deep Module for Web Search Backends.

Expand step (ticket #6): provides Registry, SearchResult, KeyProvider and
BackendSpec without wiring any real backend. Old thin shims (exa_search /
tavily_search / serpapi_cli) keep working via _search_cli directly.

Interface is the test surface: registry.search / batch_search / check
return SearchResult lists, not raw SDK dicts. Caller learns one shape.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Reuse skeleton mechanism (invoke / circuit / run_with_timeout / Flag) — do
# not duplicate. Registry is policy; search_cli is mechanism. KeyProvider is
# re-exported from tri_research_runtime (ADR-0015).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _runtime  # noqa: F401, E402 — puts src/ on sys.path
import _search_cli  # noqa: E402
from _search_cli import CONTENT_LIMIT, SNIPPET_LIMIT, truncate  # noqa: E402
from tri_research_runtime.key_provider import KeyProvider  # noqa: E402, F401
from tri_research_runtime.key_provider import key_from_env_file as _key_from_env_file  # noqa: E402, F401

# ---------------------------------------------------------------------------
# SearchResult — saturated small interface (B)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """Saturated result. Missing fields are None; truncation is uniform."""

    title: str
    url: str
    snippet: str
    content: str | None = None
    score: float | None = None
    published_date: str | None = None
    engine_meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }
        if self.content is not None:
            d["content"] = self.content
        if self.score is not None:
            d["score"] = self.score
        if self.published_date is not None:
            d["published_date"] = self.published_date
        if self.engine_meta is not None:
            d["engine_meta"] = self.engine_meta
        return d


def _to_search_result(raw: dict[str, Any]) -> SearchResult:
    """Map a backend raw dict to SearchResult with uniform truncation."""
    # Backends differ: Exa uses title/url/snippet/published_date,
    # Tavily uses title/url/snippet/content/score,
    # SerpApi uses title/link/snippet, Fake uses title/url.
    url = raw.get("url") or raw.get("link") or ""
    title = raw.get("title") or ""
    snippet = truncate(raw.get("snippet") or raw.get("text") or "", SNIPPET_LIMIT)
    content = raw.get("content")
    if content is not None:
        content = truncate(content, CONTENT_LIMIT) or None
    score = raw.get("score")
    try:
        score_val: float | None = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_val = None
    published = raw.get("published_date") or raw.get("publishedDate") or None
    # Preserve extra backend meta without leaking raw keys to caller as top-level
    engine_meta = raw.get("engine_meta")
    if engine_meta is None:
        # Collect known meta that backends return alongside results
        meta_keys = ("autoprompt_string", "search_depth", "category", "engine")
        meta = {k: raw[k] for k in meta_keys if k in raw}
        engine_meta = meta or None
    return SearchResult(
        title=str(title),
        url=str(url),
        snippet=snippet,
        content=content,
        score=score_val,
        published_date=str(published) if published else None,
        engine_meta=engine_meta,
    )


# ---------------------------------------------------------------------------
# BackendSpec — declarative spec consumed by Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendSpec:
    """Declarative spec consumed by Registry: which backend, plus identity.

    Carries no key material or env-var name: ``env_key`` / ``env_file`` are
    the backend's own declaration and the single source read by
    ``Backend.client()``. A second copy here would be free to disagree.

    Tuning knobs live on the Backend instance itself (call_timeout /
    max_attempts / retry_backoff / circuit_threshold / circuit_cooldown);
    tests and callers set them via setattr — no override surface here.
    """

    name: str
    backend: _search_cli.Backend


# ---------------------------------------------------------------------------
# Registry — deep Module
# ---------------------------------------------------------------------------


class SearchBackendRegistry:
    """Programmatic seam for all Web Search Backends.

    The agent-facing CLI surface is `_search_cli` (exa_search.py /
    tavily_search.py / serpapi_cli.py); this registry serves programmatic
    callers with uniform SearchResult shapes (search / batch_search /
    check, exercised by the registry tests). The shape-preserving
    `search_raw` bridge was removed in ADR-0003 — zero callers repo-wide;
    reintroduce it from git history only if the CLI ever migrates onto
    this seam. Deletion test: remove one adapter, callers do not
    re-introduce flag/mapping complexity.
    """

    def __init__(self) -> None:
        self._backends: dict[str, BackendSpec] = {}
        # Global flags shared by all backends (per grill: --no-proxy universal)
        self.global_flags: Sequence[_search_cli.Flag] = (
            _search_cli.Flag("no_proxy", ("--no-proxy",), "Clear proxy env vars for this run", action="store_true"),
        )

    # -- registration -------------------------------------------------------
    def register(self, spec: BackendSpec) -> None:
        key = spec.name.lower()
        if key in self._backends:
            raise ValueError(f"backend already registered: {spec.name}")
        self._backends[key] = spec

    def get(self, name: str) -> BackendSpec:
        key = name.lower()
        if key not in self._backends:
            raise KeyError(f"backend not registered: {name}")
        return self._backends[key]

    def list_backends(self) -> list[str]:
        return sorted(self._backends.keys())

    # -- search -------------------------------------------------------------
    def search(
        self,
        name: str,
        query: str,
        options: dict[str, Any] | None = None,
        *,
        cli_key: str | None = None,
        no_proxy: bool = False,
    ) -> list[SearchResult]:
        """Search one query, return uniform SearchResult list (or raise)."""
        backend = self.get(name).backend
        if no_proxy:
            _search_cli.clear_proxy_vars()
        # Proxy / key / SDK rules live in Backend.client(); ClientSetupError
        # subclasses RuntimeError, so programmatic callers keep catching one
        # exception family.
        client = backend.client(cli_key=cli_key)
        opts = options or {}

        def _call() -> dict[str, Any]:
            return backend.search(client, query, opts)

        raw = _search_cli.invoke(backend, _call)
        # Normalize: backend.search returns {"results": [raw...], ...}
        raws = raw.get(backend.results_key, []) if isinstance(raw, dict) else []
        results: list[SearchResult] = []
        for r in raws:
            if isinstance(r, dict):
                results.append(_to_search_result(r))
            else:
                # Exa returns objects; search_backends normalizes to dicts, but
                # FakeBackend already returns dicts. Be defensive.
                results.append(_to_search_result({"title": str(r), "url": ""}))
        return results

    def batch_search(
        self,
        name: str,
        queries: Sequence[str],
        options: dict[str, Any] | None = None,
        *,
        cli_key: str | None = None,
        no_proxy: bool = False,
    ) -> dict[str, list[SearchResult] | dict[str, str]]:
        """Batch search: per-query list[Result] or {"error": str}."""
        opts = options or {}
        out: dict[str, list[SearchResult] | dict[str, str]] = {}
        for q in queries:
            try:
                out[q] = self.search(name, q, opts, cli_key=cli_key, no_proxy=no_proxy)
            except _search_cli.ClientSetupError:
                # A broken bootstrap is not a query outcome: repeating it once
                # per query turns one actionable failure into N identical
                # error dicts. Fails fast, like the CLI lane.
                raise
            except Exception as exc:  # noqa: BLE001 — per-query isolation
                out[q] = {"error": str(exc)}
        return out

    def check(self, name: str, *, cli_key: str | None = None, no_proxy: bool = False) -> dict[str, Any]:
        """Availability probe: always returns JSON, never traceback."""
        try:
            spec = self.get(name)
        except KeyError as exc:
            return {"available": False, "error": str(exc)}
        backend = spec.backend
        if no_proxy:
            _search_cli.clear_proxy_vars()
        try:
            # One bootstrap with the CLI lane's semantics: Backend.client()
            # decides what "unavailable before the first request" means
            # (missing SDK, unresolvable key), and its message is the same
            # text this method used to build by hand.
            client = backend.client(cli_key=cli_key)
            ok = _search_cli.run_with_timeout(
                lambda: backend.probe(client),
                backend.call_timeout,
            )
        except Exception as exc:  # noqa: BLE001 — probe must never traceback
            return {"available": False, "error": str(exc)}
        return {"available": bool(ok)}


# Global singleton — search_backends registers Exa/Tavily on import
REGISTRY = SearchBackendRegistry()
