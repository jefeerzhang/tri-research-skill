"""SearchBackendRegistry — deep Module for Web Search Backends.

Expand step (ticket #6): provides Registry, SearchResult, KeyProvider and
BackendSpec without wiring any real backend. Old thin shims (exa_search /
tavily_search / serpapi_cli) keep working via _search_cli directly.

Interface is the test surface: registry.search / batch_search / check
return SearchResult lists, not raw SDK dicts. Caller learns one shape.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# Reuse skeleton mechanism (invoke / circuit / _run_with_timeout / Flag) — do
# not duplicate. Registry is policy; _search_cli is mechanism.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import _search_cli  # noqa: E402

# ---------------------------------------------------------------------------
# SearchResult — saturated small interface (B)
# ---------------------------------------------------------------------------

_SNIPPET_LIMIT = 500
_CONTENT_LIMIT = 5000


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


def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return ""
    return text[:limit]


def _to_search_result(raw: dict[str, Any]) -> SearchResult:
    """Map a backend raw dict to SearchResult with uniform truncation."""
    # Backends differ: Exa uses title/url/snippet/published_date,
    # Tavily uses title/url/snippet/content/score,
    # SerpApi uses title/link/snippet, Fake uses title/url.
    url = raw.get("url") or raw.get("link") or ""
    title = raw.get("title") or ""
    snippet = _truncate(raw.get("snippet") or raw.get("text") or "", _SNIPPET_LIMIT)
    content = raw.get("content")
    if content is not None:
        content = _truncate(content, _CONTENT_LIMIT) or None
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
# KeyProvider — cli > env > .env seam
# ---------------------------------------------------------------------------


def _key_from_env_file(env_path: Path, env_key: str) -> str | None:
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, value = line.partition("=")
                if sep and key.strip() == env_key:
                    return value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


def clear_proxy_vars() -> None:
    for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(_p, None)


class KeyProvider:
    """Resolve API key with priority cli > env > the caller-declared .env.

    Per spec C1 grill; the .env location is handed in by the caller
    (``Backend.env_file``) — layout knowledge lives with each backend,
    not here (ADR-0004).
    """

    @staticmethod
    def resolve(
        cli_key: str | None,
        env_key: str,
        env_file: Path | None = None,
    ) -> str | None:
        if cli_key:
            return cli_key
        env = os.environ.get(env_key)
        if env:
            return env
        # The caller declares where its own .env lives (Backend.env_file);
        # this module knows nothing about any skill's directory layout
        # (ADR-0004).
        if env_file is not None:
            v = _key_from_env_file(env_file, env_key)
            if v:
                return v
        return None


# ---------------------------------------------------------------------------
# BackendSpec — declarative spec consumed by Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendSpec:
    name: str
    backend: _search_cli.Backend
    env_key: str
    # Optional overrides; None means use backend's own defaults
    call_timeout: float | None = None
    max_attempts: int | None = None
    retry_backoff: float | None = None
    circuit_threshold: int | None = None
    circuit_cooldown: float | None = None


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
        # Apply per-backend overrides to the underlying Backend instance so
        # _search_cli.invoke reads the correct tuning without extra branching.
        b = spec.backend
        if spec.call_timeout is not None:
            b.call_timeout = spec.call_timeout
        if spec.max_attempts is not None:
            b.max_attempts = spec.max_attempts
        if spec.retry_backoff is not None:
            b.retry_backoff = spec.retry_backoff
        if spec.circuit_threshold is not None:
            b.circuit_threshold = spec.circuit_threshold
        if spec.circuit_cooldown is not None:
            b.circuit_cooldown = spec.circuit_cooldown
        self._backends[key] = spec

    def get(self, name: str) -> BackendSpec:
        key = name.lower()
        if key not in self._backends:
            raise KeyError(f"backend not registered: {name}")
        return self._backends[key]

    def list_backends(self) -> list[str]:
        return sorted(self._backends.keys())

    # -- key / proxy helpers ------------------------------------------------
    def _resolve_backend(
        self, name: str, cli_key: str | None = None, no_proxy: bool = False
    ) -> tuple[_search_cli.Backend, str]:
        spec = self.get(name)
        backend = spec.backend
        if no_proxy:
            clear_proxy_vars()
        api_key = KeyProvider.resolve(cli_key, spec.env_key, spec.backend.env_file)
        if not api_key:
            raise RuntimeError(f"{spec.env_key} not set")
        # Ensure backend sees the same key via env for its client() path, but
        # do not mutate os.environ globally — pass via client_factory directly.
        return backend, api_key

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
        backend, api_key = self._resolve_backend(name, cli_key, no_proxy)
        opts = options or {}
        # Build a lightweight client without going through backend.client()'s
        # env lookup — use the resolved key directly.
        client = backend.client_factory(api_key) if backend.sdk is not None else None
        if client is None and backend.sdk is None:
            raise RuntimeError(backend.missing_sdk_message or f"{name} SDK not installed")

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
        if backend.sdk is None:
            return {"available": False, "error": backend.missing_sdk_message}
        if no_proxy:
            clear_proxy_vars()
        api_key = KeyProvider.resolve(cli_key, spec.env_key, spec.backend.env_file)
        if not api_key:
            return {"available": False, "error": f"{spec.env_key} not set"}
        try:
            ok = _search_cli._run_with_timeout(
                lambda: backend.probe(backend.client_factory(api_key)),
                getattr(backend, "call_timeout", 30.0),
            )
        except Exception as exc:  # noqa: BLE001 — probe must never traceback
            return {"available": False, "error": str(exc)}
        return {"available": bool(ok)}


# Global singleton — search_backends registers Exa/Tavily on import
REGISTRY = SearchBackendRegistry()
