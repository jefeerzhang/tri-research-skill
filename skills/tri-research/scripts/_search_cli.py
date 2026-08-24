"""Shared CLI skeleton for the tri-research search-backend wrappers.

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
open a per-backend circuit so later calls fail fast. `check` applies
timeout but not retry. Missing SDK / missing key still fail immediately.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Sequence, TypeVar

_T = TypeVar("_T")


def json_error(message: str) -> None:
    """Print a JSON error and exit 1 — the wrapper contract for failures."""
    print(json.dumps({"error": message}, ensure_ascii=False))
    sys.exit(1)


class CircuitOpenError(RuntimeError):
    """Raised when a backend circuit is open; not retryable, fail-fast."""


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
    """An extra backend-specific subcommand (e.g. Exa `answer`)."""

    __slots__ = ("name", "help", "add_args", "run")

    def __init__(
        self,
        name: str,
        help: str,
        add_args: Callable[[argparse.ArgumentParser], None],
        run: Callable[[argparse.Namespace], None],
    ) -> None:
        self.name = name
        self.help = help
        self.add_args = add_args
        self.run = run


class Backend:
    """Declarative spec wiring a search SDK into the shared CLI.

    Subclasses override the static fields (sdk / env_key / client_factory /
    flags) and implement `probe` and `search`; the shared command handlers
    below do the rest.
    """

    name: str = ""
    help: str = ""
    sdk: Any = None                       # imported SDK module; None when missing
    missing_sdk_message: str = ""         # JSON error when sdk is None
    env_key: str = ""                     # API key environment variable
    client_factory: Callable[[str], Any] = None
    # Immutable defaults: a class-level list shared across subclasses would
    # leak runtime appends (e.g. registering an extra command) to every
    # other backend. Subclasses may still assign their own sequence.
    flags: Sequence[Flag] = ()            # flags attached to search/batch_search
    global_flags: Sequence[Flag] = ()     # flags attached to the root parser
    commands: Sequence[Command] = ()      # extra subcommands
    results_key: str = "results"          # key of the result list in search() output
    search_handler: Callable[[Any, argparse.Namespace], None] | None = None
    batch_search_handler: Callable[[Any, argparse.Namespace], None] | None = None
    search_args_builder: Callable[[argparse.ArgumentParser], None] | None = None
    batch_search_args_builder: Callable[[argparse.ArgumentParser], None] | None = None
    max_attempts: int = 3
    retry_backoff: float = 0.5
    call_timeout: float = 30.0
    circuit_threshold: int = 5
    circuit_cooldown: float = 60.0
    _circuit_failures: int = 0
    _circuit_opened_at: float | None = None

    def client(self) -> Any:
        """Build the SDK client, honoring the wrapper's JSON-error contract."""
        if self.sdk is None:
            json_error(self.missing_sdk_message)
        api_key = os.environ.get(self.env_key)
        if not api_key:
            json_error(f"{self.env_key} not set")
        return self.client_factory(api_key)

    def probe(self, client: Any) -> bool:
        """Run a trivial query; return True on success, raise on failure."""
        raise NotImplementedError

    def search(
        self, client: Any, query: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        """Run one query; return the JSON-ready output dict (without 'query')."""
        raise NotImplementedError


def search_options(backend: Backend, args: argparse.Namespace) -> dict[str, Any]:
    """Collect declared flags that were actually passed into a kwargs dict."""
    return {
        flag.dest: getattr(args, flag.dest)
        for flag in backend.flags
        if getattr(args, flag.dest) is not None
    }


def _run_with_timeout(fn: Callable[[], _T], timeout: float) -> _T:
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
    cooldown = getattr(backend, "circuit_cooldown", 60.0)
    if time.monotonic() - opened_at >= cooldown:
        return
    name = backend.name or "backend"
    raise CircuitOpenError(f"circuit open for {name}")


def _circuit_success(backend: Backend) -> None:
    backend._circuit_failures = 0
    backend._circuit_opened_at = None


def _circuit_exhausted(backend: Backend) -> None:
    backend._circuit_failures += 1
    threshold = getattr(backend, "circuit_threshold", 5)
    if backend._circuit_failures >= threshold:
        backend._circuit_opened_at = time.monotonic()


def _http_status(exc: BaseException) -> int | None:
    message = str(exc)
    match = re.search(r"\bHTTP\s+(\d{3})\b", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, CircuitOpenError):
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
    return any(
        token in message
        for token in ("timeout", "timed out", "connection", "rate limit", "ssl")
    )


def invoke(backend: Backend, fn: Callable[[], _T]) -> _T:
    """Run ``fn`` with timeout, retry, and circuit. Public for SerpApi handlers."""
    max_attempts = getattr(backend, "max_attempts", 3)
    retry_backoff = getattr(backend, "retry_backoff", 0.5)
    call_timeout = getattr(backend, "call_timeout", 30.0)
    last_error: BaseException | None = None
    for attempt in range(max_attempts):
        _circuit_allow(backend)
        try:
            value = _run_with_timeout(fn, call_timeout)
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
            delay = retry_backoff * (2 ** attempt)
            if delay > 0:
                time.sleep(delay)
            continue
        _circuit_success(backend)
        return value
    assert last_error is not None
    raise last_error


def check(backend: Backend) -> None:
    """Availability probe: always prints JSON, never a traceback."""
    if backend.sdk is None:
        print(json.dumps({"available": False, "error": backend.missing_sdk_message}))
        return
    api_key = os.environ.get(backend.env_key)
    if not api_key:
        print(json.dumps({"available": False, "error": f"{backend.env_key} not set"}))
        return
    try:
        ok = _run_with_timeout(
            lambda: backend.probe(backend.client_factory(api_key)),
            getattr(backend, "call_timeout", 30.0),
        )
    except Exception as exc:
        print(json.dumps({"available": False, "error": str(exc)}))
        return
    print(json.dumps({"available": bool(ok)}))


def search(backend: Backend, args: argparse.Namespace) -> None:
    if backend.search_handler is not None:
        backend.search_handler(backend, args)
        return
    client = backend.client()
    try:
        output = invoke(
            backend,
            lambda: backend.search(client, args.query, search_options(backend, args)),
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc), "query": args.query}, ensure_ascii=False))
        sys.exit(1)
    output["query"] = args.query
    print(json.dumps(output, ensure_ascii=False))


def batch_search(backend: Backend, args: argparse.Namespace) -> None:
    if backend.batch_search_handler is not None:
        backend.batch_search_handler(backend, args)
        return
    client = backend.client()
    all_results: dict[str, Any] = {}
    for query in args.query:
        try:
            output = invoke(
                backend,
                lambda q=query: backend.search(client, q, search_options(backend, args)),
            )
            all_results[query] = output.get(backend.results_key, [])
        except Exception as exc:
            all_results[query] = {"error": str(exc)}
    print(json.dumps(all_results, ensure_ascii=False))


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

    for command in backend.commands:
        command_p = subparsers.add_parser(command.name, help=command.help)
        command.add_args(command_p)
    return parser


def run(backend: Backend, argv: list[str] | None = None) -> int:
    parser = build_parser(backend)
    args = parser.parse_args(argv)
    if args.command == "check":
        check(backend)
    elif args.command == "search":
        search(backend, args)
    elif args.command == "batch_search":
        batch_search(backend, args)
    else:
        for command in backend.commands:
            if command.name == args.command:
                command.run(args)
                return 0
        parser.print_help()
        return 2
    return 0
