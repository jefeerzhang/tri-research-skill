"""Shared CLI skeleton for the tri-research search-backend wrappers.

Canonical home of the Machine Backend CLI (ADR-0015). Skill scripts keep a
compatibility shim at ``scripts/_search_cli.py`` so ``import _search_cli``
still works; serpapi imports this package instead of a sibling scripts path.

exa_search.py and tavily_search.py were near-duplicates (~180 lines each):
the same check / search / batch_search command shapes, the same JSON-error
discipline, the same argparse layout — differing only in SDK import, key
env var, client factory, search flags, result normalization and one extra
command each. The duplicated parts are exactly the parts most likely to
drift: error messages, availability-probe behavior, exit codes. Drift had
already happened (e.g. Exa's `check` tracebacked on a probe failure while
Tavily's returned JSON).

This module keeps one implementation of the shared skeleton; each backend
file declares a `Backend` spec (module, env key, client factory, flags,
extra commands) and inherits everything else. Contract: the CLI surface
each backend exposes is unchanged (same subcommands and flags, same JSON
output shapes), so sub-agents and the regression tests keep working.

Transient failures (timeout, connection, 429, 5xx) are retried with
backoff behind `search` / `batch_search`. Repeated exhausted failures
open a per-backend circuit so later calls fail fast. The circuit is
process-level (in-memory on the ``Backend`` instance); a new CLI process
starts closed. `check` applies timeout but not retry. Missing SDK / missing
key still fail immediately.

Extra commands (`answer` / `contents` / `extract`) can be declared
*managed* (see `Command.managed`): `run_managed_command` then owns their
whole lifecycle — client setup via `Backend.client()`, `invoke`, error-JSON
printing and exit codes — so each command body declares nothing but its SDK
call and result shaping. Unmanaged commands keep the historical bare
`(args)` contract, which is what backends with their own error discipline
(SerpApi) rely on.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from collections.abc import Mapping, Sequence as AbcSequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, NoReturn, Sequence, TypeVar

from tri_research_runtime.errors import (
    CircuitOpenError,
    ClientSetupError,
    CommandError,
    KeyMissing,
    SdkMissing,
)
from tri_research_runtime.key_provider import KeyProvider

_T = TypeVar("_T")


def json_error(message: str) -> NoReturn:
    """Print a JSON error and exit 1 — the wrapper contract for failures."""
    print(json.dumps({"error": message}, ensure_ascii=False))
    sys.exit(1)


def _backend_api_key(backend: Backend, cli_key: str | None = None) -> str | None:
    """Resolve a backend API key via KeyProvider (cli > env > backend .env).

    Centralised here so `client` / `check` / managed commands share one key
    seam. The `.env` location is the backend's own declaration
    (`Backend.env_file`) — this module and KeyProvider know no skill
    directory layouts (ADR-0004). KeyProvider lives in this package so the
    old `_search_registry` cycle is gone.
    """
    return KeyProvider.resolve(cli_key, backend.env_key, backend.env_file)


class BackendRequirementLevel(StrEnum):
    """Executable three-tier necessity (CONTEXT.md ``BackendRequirementLevel``).

    The Required gate walks descriptors whose ``requirement`` is
    ``REQUIRED`` (ADR-0011). ``RECOMMENDED`` / ``OPTIONAL`` are declared on
    the same field so promoting a backend is a data change, not a new
    branch in ``require_required_backends``.
    """

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class Flag:
    """A search flag shared by the `search` and `batch_search` commands.

    Flags are declared once per backend and attached to both subcommands,
    which keeps the two parsers from drifting (Tavily's `batch_search` used
    to lack the include/exclude-domains flags its `search` had).
    """

    __slots__ = ("dest", "args", "help", "type", "choices", "default", "action")

    def __init__(
        self,
        dest: str,
        args: tuple[str, ...],
        help: str,
        *,
        type: type | None = None,
        choices: list[str] | None = None,
        default: Any = None,
        action: str | None = None,
    ) -> None:
        self.dest = dest
        self.args = args
        self.help = help
        self.type = type
        self.choices = choices
        self.default = default
        self.action = action

    def add_to(self, parser: argparse.ArgumentParser) -> None:
        kwargs: dict[str, Any] = {"dest": self.dest, "help": self.help, "default": self.default}
        if self.action is not None:
            kwargs["action"] = self.action
        if self.type is not None:
            kwargs["type"] = self.type
        if self.choices is not None:
            kwargs["choices"] = self.choices
        parser.add_argument(*self.args, **kwargs)


class Command:
    """A backend-specific subcommand (e.g. Exa `answer`).

    Two execution contracts live here:

    - Unmanaged (``managed=False``, the default): ``run(args)`` is called
      with the bare namespace and owns everything itself. SerpApi's
      entries stay on this contract deliberately (ADR-0002).
    - Managed (``managed=True``): ``run(client, args)`` is invoked by
      :func:`run_managed_command`, which resolves the key, checks the SDK,
      builds the client, wraps the call in `invoke` and prints the result
      (or the error JSON). ``echo`` supplies the identifying fields
      (`{"query": ...}` / `{"url": ...}`) merged into every error payload
      so the published error shape stays byte-identical.
    """

    __slots__ = ("name", "help", "add_args", "run", "managed", "echo")

    def __init__(
        self,
        name: str,
        help: str,
        add_args: Callable[[argparse.ArgumentParser], None],
        run: Callable[..., Any],
        *,
        managed: bool = False,
        echo: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.help = help
        self.add_args = add_args
        self.run = run
        self.managed = managed
        self.echo = echo


class Backend:
    """Declarative spec wiring a search SDK into the shared CLI.

    Subclasses override the static fields (sdk / env_key / client_factory /
    flags) and implement `probe` and `search`; the shared command handlers
    below do the rest.
    """

    name: str = ""
    help: str = ""
    sdk: Any = None  # imported SDK module; None when missing
    missing_sdk_message: str = ""  # JSON error when sdk is None
    env_key: str = ""  # API key environment variable
    client_factory: Callable[[str], Any] = None
    # Immutable defaults: a class-level list shared across subclasses would
    # leak runtime appends (e.g. registering an extra command) to every
    # other backend. Subclasses may still assign their own sequence.
    flags: Sequence[Flag] = ()  # flags attached to search/batch_search
    global_flags: Sequence[Flag] = ()  # flags attached to the root parser
    commands: Sequence[Command] = ()  # extra subcommands
    results_key: str = "results"  # key of the result list in search() output
    # The backend's own .env location, declared by each backend; None means
    # env-only. KeyProvider reads only what it is handed — no skill-layout
    # knowledge anywhere (ADR-0004).
    env_file: Path | None = None
    # Necessity + start-gate shape live on the Backend, not BackendSpec
    # (Spec is Registry identity only; a second copy would drift, ADR-0008).
    requirement: BackendRequirementLevel = BackendRequirementLevel.OPTIONAL
    # ADR-0007 narrow exception: only SerpApi probes at start. Exa / Tavily
    # stay K+S (or unused, for optional) with no start-time network call.
    start_probe: bool = False
    apply_url: str = ""
    verify_cmd: str = ""
    configure_hint: str = ""
    search_handler: Callable[[Any, argparse.Namespace], None] | None = None
    batch_search_handler: Callable[[Any, argparse.Namespace], None] | None = None
    search_args_builder: Callable[[argparse.ArgumentParser], None] | None = None
    batch_search_args_builder: Callable[[argparse.ArgumentParser], None] | None = None
    max_attempts: int = 3
    retry_backoff: float = 0.5
    call_timeout: float = 30.0
    circuit_threshold: int = 5
    circuit_cooldown: float = 60.0
    # Process-level circuit (ADR-0015): counters live on this instance in
    # this process only. A new CLI invocation starts closed. Not shared
    # across processes, hosts, or skills; isolation is a follow-up.
    _circuit_failures: int = 0
    _circuit_opened_at: float | None = None

    def api_key(self, *, cli_key: str | None = None) -> str:
        """Resolve this backend's key (cli > env > its own ``.env``); raise if absent.

        The half of :meth:`client` that stands alone for backends whose client
        is only a key holder and whose real SDK dependency is touched later
        (SerpApi: ``requests`` is needed at fetch time, not build time).
        """
        api_key = _backend_api_key(self, cli_key)
        if not api_key:
            raise KeyMissing(f"{self.env_key} not set")
        return api_key

    def require_setup(self, *, cli_key: str | None = None) -> str:
        """SDK present and key resolvable. Returns the key; does not build.

        The assembly *judgment* shared by :meth:`client` and :meth:`readiness`
        (ADR-0011). The Required gate is K+S (ADR-0006), not "SDK client
        constructed" — constructing Exa() at ``start`` would demand a real
        SDK class the stubs do not provide.
        """
        if self.sdk is None:
            raise SdkMissing(self.missing_sdk_message)
        return self.api_key(cli_key=cli_key)

    def client(self, *, cli_key: str | None = None) -> Any:
        """Set up the SDK client: SDK present -> key resolvable -> build.

        The one home of that sequence in the repo; every command path
        (search / batch_search / check / managed commands / Registry / the
        Required gate's SerpApi probe) goes through here and translates
        :class:`ClientSetupError` into its own output dialect. Order is load
        bearing: the SDK check must precede ``client_factory``, otherwise a
        missing SDK turns into a traceback instead of a documented error
        (ADR-0002) — and an unset key cannot be fixed into a working client
        while the SDK is still missing.
        """
        return self.client_factory(self.require_setup(cli_key=cli_key))

    def readiness(self) -> list[str]:
        """Gap strings for the Required gate; empty means this backend is ready.

        Assembly judgment is :meth:`require_setup` (same SDK → key rules as
        :meth:`client`). Backends with ``start_probe`` then build a client
        and reuse ``probe`` under the same timeout as ``check``. The gate's
        dialect is a collected gap list, not a raise.
        """
        try:
            if self.start_probe:
                client = self.client()
            else:
                self.require_setup()
                return []
        except ClientSetupError as exc:
            return [f"{self.name}: {exc}"]
        try:
            ok = run_with_timeout(lambda: self.probe(client), self.call_timeout)
        except Exception as exc:  # noqa: BLE001 — probe failure surfaces as a gap
            return [f"{self.name}: probe failed: {exc}"]
        if not ok:
            return [f"{self.name}: probe failed"]
        return []

    def probe(self, client: Any) -> bool:
        """Run a trivial query; return True on success, raise on failure."""
        raise NotImplementedError

    def search(self, client: Any, query: str, options: dict[str, Any]) -> dict[str, Any]:
        """Run one query; return the JSON-ready output dict (without 'query')."""
        raise NotImplementedError


def search_options(backend: Backend, args: argparse.Namespace) -> dict[str, Any]:
    """Collect declared flags that were actually passed into a kwargs dict."""
    return {flag.dest: getattr(args, flag.dest) for flag in backend.flags if getattr(args, flag.dest) is not None}


def run_with_timeout(fn: Callable[[], _T], timeout: float) -> _T:
    """Run ``fn`` on a daemon thread; raise TimeoutError if it exceeds timeout.

    Daemon threads are required: a worker-pool shutdown(wait=True) would
    block the CLI for the remainder of a hung SDK call, which is the
    failure mode this timeout exists to prevent. Windows has no SIGALRM.
    """
    result: dict[str, _T] = {}
    error: dict[str, BaseException] = {}
    done = threading.Event()

    def worker() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
            error["exc"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    if not done.wait(timeout):
        raise TimeoutError(f"timed out after {timeout}s")
    if "exc" in error:
        raise error["exc"]
    return result["value"]


def _circuit_allow(backend: Backend) -> None:
    opened_at = backend._circuit_opened_at
    if opened_at is None:
        return
    cooldown = backend.circuit_cooldown
    if time.monotonic() - opened_at >= cooldown:
        return
    name = backend.name or "backend"
    raise CircuitOpenError(f"circuit open for {name}")


def _circuit_success(backend: Backend) -> None:
    backend._circuit_failures = 0
    backend._circuit_opened_at = None


def _circuit_exhausted(backend: Backend) -> None:
    backend._circuit_failures += 1
    threshold = backend.circuit_threshold
    if backend._circuit_failures >= threshold:
        backend._circuit_opened_at = time.monotonic()


def _http_status(exc: BaseException) -> int | None:
    message = str(exc)
    match = re.search(r"\bHTTP\s+(\d{3})\b", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (CircuitOpenError, CommandError)):
        return False
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, ConnectionError):
        return True
    status = _http_status(exc)
    if status == 429 or (status is not None and status >= 500):
        return True
    if status is not None and 400 <= status < 500:
        return False
    exit_code = getattr(exc, "exit_code", None)
    if exit_code in (1, 2, 4, 5):
        return False
    if exit_code == 3:
        return True
    message = str(exc).lower()
    return any(token in message for token in ("timeout", "timed out", "connection", "rate limit", "ssl"))


def invoke(backend: Backend, fn: Callable[[], _T]) -> _T:
    """Run ``fn`` with timeout, retry, and circuit. Public for SerpApi handlers."""
    max_attempts = backend.max_attempts
    retry_backoff = backend.retry_backoff
    call_timeout = backend.call_timeout
    last_error: BaseException | None = None
    for attempt in range(max_attempts):
        _circuit_allow(backend)
        try:
            value = run_with_timeout(fn, call_timeout)
        except CircuitOpenError:
            raise
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException as exc:
            last_error = exc
            if not _is_retryable(exc) or attempt + 1 >= max_attempts:
                if _is_retryable(exc):
                    _circuit_exhausted(backend)
                raise
            delay = retry_backoff * (2**attempt)
            if delay > 0:
                time.sleep(delay)
            continue
        _circuit_success(backend)
        return value
    assert last_error is not None
    raise last_error


def check(backend: Backend) -> None:
    """Availability probe: always prints JSON, never a traceback."""
    try:
        client = backend.client()
    except Exception as exc:
        # Broad on purpose: a ClientSetupError carries its own user-facing
        # text, and a client_factory that raises must still print
        # {"available": false} instead of the traceback `check` promises
        # never to emit.
        print(json.dumps({"available": False, "error": str(exc)}))
        return
    try:
        ok = run_with_timeout(lambda: backend.probe(client), backend.call_timeout)
    except Exception as exc:
        print(json.dumps({"available": False, "error": str(exc)}))
        return
    print(json.dumps({"available": bool(ok)}))


def clear_proxy_vars() -> None:
    """Drop proxy env vars for this process only (opt-in via --no-proxy).

    The single home of the proxy tuple: registry, backends and SerpApi all
    delegate here (see tests/test_host_helpers.py consolidation gate).
    """
    for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(_p, None)


def wants_no_proxy(args: argparse.Namespace) -> bool:
    """Read the global ``--no-proxy`` flag.

    ``getattr`` default: backends declare ``--no-proxy`` as a global flag, but
    a bare ``Namespace`` (tests, programmatic callers) need not carry it.
    """
    return bool(getattr(args, "no_proxy", False))


def _maybe_clear_proxy(args: argparse.Namespace) -> None:
    if wants_no_proxy(args):
        clear_proxy_vars()


# ---------------------------------------------------------------------------
# Result truncation — the limits both search lanes share
# ---------------------------------------------------------------------------

SNIPPET_LIMIT = 500
CONTENT_LIMIT = 5000
CITATION_TEXT_LIMIT = 1000  # Exa managed `answer` citation text
EXTRACT_CONTENT_LIMIT = 20000  # Tavily managed `extract` page content


def truncate(text: str | None, limit: int) -> str:
    """Clip a result field to ``limit`` characters; missing or empty becomes "".

    The single home of the limits: a backend that hard-coded its own width
    made the same result read differently depending on which lane fetched it
    (CLI vs Registry), and the metadata in the output then lied about it.
    """
    if not text:
        return ""
    return text[:limit]


def _add_ledger_session_flags(parser: argparse.ArgumentParser) -> None:
    """``--session`` binds a successful search to the Evidence Ledger (ADR-0010)."""
    parser.add_argument(
        "--session",
        default=None,
        help="Research Session id; on success, append seen rows to the Evidence Ledger (ADR-0010)",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="State directory used with --session (TRI_RESEARCH_STATE_DIR / temp if omitted)",
    )


def bind_successful_search_to_ledger(
    backend: Backend,
    args: argparse.Namespace,
    hits_by_query: Mapping[str, AbcSequence[Any]],
) -> None:
    """After a successful search/batch, optionally append ``seen`` rows (ADR-0010).

    No-op without ``--session``. With ``--session``, a ledger write failure
    fails the CLI (JSON error + exit 1): do not return success with a missing
    ledger. Custom ``search_handler`` / ``batch_search_handler`` (SerpApi)
    must call this themselves — the default path cannot see their result lists.
    """
    session = getattr(args, "session", None)
    if not session:
        return
    try:
        from evidence import StateStore, append_seen_hits, default_state_dir

        state_dir = getattr(args, "state_dir", None)
        store = StateStore(Path(state_dir) if state_dir is not None else default_state_dir())
        append_seen_hits(
            store,
            session,
            backend=backend.name,
            hits_by_query=hits_by_query,
        )
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as exc:
        json_error(f"evidence ledger write failed: {exc}")


def search(backend: Backend, args: argparse.Namespace) -> None:
    _maybe_clear_proxy(args)
    if backend.search_handler is not None:
        backend.search_handler(backend, args)
        return
    try:
        client = backend.client()
    except ClientSetupError as exc:
        json_error(str(exc))
    try:
        output = invoke(
            backend,
            lambda: backend.search(client, args.query, search_options(backend, args)),
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc), "query": args.query}, ensure_ascii=False))
        sys.exit(1)
    output["query"] = args.query
    bind_successful_search_to_ledger(
        backend,
        args,
        {args.query: output.get(backend.results_key, [])},
    )
    print(json.dumps(output, ensure_ascii=False))


def batch_search(backend: Backend, args: argparse.Namespace) -> None:
    _maybe_clear_proxy(args)
    if backend.batch_search_handler is not None:
        backend.batch_search_handler(backend, args)
        return
    try:
        client = backend.client()
    except ClientSetupError as exc:
        # Decided once, before the loop: a missing key is not a query outcome,
        # and N per-query error dicts with a 0 exit code hid it.
        json_error(str(exc))
    all_results: dict[str, Any] = {}
    hits_by_query: dict[str, list[Any]] = {}
    for query in args.query:
        try:
            output = invoke(
                backend,
                lambda q=query: backend.search(client, q, search_options(backend, args)),
            )
            results = output.get(backend.results_key, [])
            all_results[query] = results
            hits_by_query[query] = results
        except Exception as exc:
            all_results[query] = {"error": str(exc)}
    bind_successful_search_to_ledger(backend, args, hits_by_query)
    print(json.dumps(all_results, ensure_ascii=False))


def _emit_command_error(command: Command, args: argparse.Namespace, message: str) -> NoReturn:
    """Print the legacy error shape ({"error": msg, **echo}) and exit 1.

    Errors keep the historical default (ASCII-escaped) encoding while
    success payloads are printed with ensure_ascii=False. Typed as
    ``NoReturn`` because it always exits: callers rely on control never
    falling through to a client build with a missing key or SDK.
    """
    payload: dict[str, Any] = {"error": message}
    if command.echo is not None:
        payload.update(command.echo(args))
    print(json.dumps(payload))
    sys.exit(1)


def run_managed_command(backend: Backend, command: Command, args: argparse.Namespace) -> None:
    """Skeleton-owned lifecycle for a managed extra command.

    Order is load bearing: proxy first, then :meth:`Backend.client` (which
    checks the SDK before ``client_factory`` — ADR-0002), then the call.
    """
    _maybe_clear_proxy(args)
    try:
        client = backend.client()
    except ClientSetupError as exc:
        _emit_command_error(command, args, str(exc))
    try:
        output = invoke(backend, lambda: command.run(client, args))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:
        _emit_command_error(command, args, str(exc))
    print(json.dumps(output, ensure_ascii=False))


def build_parser(backend: Backend) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=backend.help)
    for flag in backend.global_flags:
        flag.add_to(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Check availability")

    search_p = subparsers.add_parser("search", help=f"Search the web via {backend.name}")
    if backend.search_args_builder is not None:
        backend.search_args_builder(search_p)
    else:
        search_p.add_argument("query", help="Search query")
        for flag in backend.flags:
            flag.add_to(search_p)

    batch_p = subparsers.add_parser("batch_search", help="Batch search multiple queries")
    if backend.batch_search_args_builder is not None:
        backend.batch_search_args_builder(batch_p)
    else:
        batch_p.add_argument("--query", action="append", required=True, help="Query (can repeat)")
        for flag in backend.flags:
            flag.add_to(batch_p)

    _add_ledger_session_flags(search_p)
    _add_ledger_session_flags(batch_p)

    for command in backend.commands:
        command_p = subparsers.add_parser(command.name, help=command.help)
        command.add_args(command_p)
    return parser


def run(backend: Backend, argv: list[str] | None = None) -> int:
    parser = build_parser(backend)
    args = parser.parse_args(argv)
    if args.command == "check":
        # The global --no-proxy flag must take effect here too: without this
        # the probe ran with proxy env vars intact, so SSL-breaking proxies
        # kept producing false "unavailable" JSON (the CLI diverged from
        # REGISTRY.check(no_proxy=True), which has always cleared).
        _maybe_clear_proxy(args)
        check(backend)
    elif args.command == "search":
        search(backend, args)
    elif args.command == "batch_search":
        batch_search(backend, args)
    else:
        for command in backend.commands:
            if command.name == args.command:
                if command.managed:
                    run_managed_command(backend, command, args)
                else:
                    command.run(args)
                return 0
        parser.print_help()
        return 2
    return 0
