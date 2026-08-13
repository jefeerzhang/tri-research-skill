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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable


def json_error(message: str) -> None:
    """Print a JSON error and exit 1 — the wrapper contract for failures."""
    print(json.dumps({"error": message}, ensure_ascii=False))
    sys.exit(1)


class Flag:
    """A search flag shared by the `search` and `batch_search` commands.

    Flags are declared once per backend and attached to both subcommands,
    which keeps the two parsers from drifting (Tavily's `batch_search` used
    to lack the include/exclude-domains flags its `search` had).
    """

    __slots__ = ("dest", "args", "help", "type", "choices", "default")

    def __init__(
        self,
        dest: str,
        args: tuple[str, ...],
        help: str,
        *,
        type: type | None = None,
        choices: list[str] | None = None,
        default: Any = None,
    ) -> None:
        self.dest = dest
        self.args = args
        self.help = help
        self.type = type
        self.choices = choices
        self.default = default

    def add_to(self, parser: argparse.ArgumentParser) -> None:
        kwargs: dict[str, Any] = {"dest": self.dest, "help": self.help, "default": self.default}
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
        run: Callable[[Any, argparse.Namespace], None],
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
    flags: list[Flag] = []
    commands: list[Command] = []          # extra subcommands
    results_key: str = "results"          # key of the result list in search() output

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
        ok = backend.probe(backend.client_factory(api_key))
    except Exception as exc:
        print(json.dumps({"available": False, "error": str(exc)}))
        return
    print(json.dumps({"available": bool(ok)}))


def search(backend: Backend, args: argparse.Namespace) -> None:
    client = backend.client()
    try:
        output = backend.search(client, args.query, search_options(backend, args))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "query": args.query}, ensure_ascii=False))
        sys.exit(1)
    output["query"] = args.query
    print(json.dumps(output, ensure_ascii=False))


def batch_search(backend: Backend, args: argparse.Namespace) -> None:
    client = backend.client()
    all_results: dict[str, Any] = {}
    for query in args.query:
        try:
            output = backend.search(client, query, search_options(backend, args))
            all_results[query] = output.get(backend.results_key, [])
        except Exception as exc:
            all_results[query] = {"error": str(exc)}
    print(json.dumps(all_results, ensure_ascii=False))


def build_parser(backend: Backend) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=backend.help)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Check availability")

    search_p = subparsers.add_parser("search", help=f"Search the web via {backend.name}")
    search_p.add_argument("query", help="Search query")
    for flag in backend.flags:
        flag.add_to(search_p)

    batch_p = subparsers.add_parser("batch_search", help="Batch search multiple queries")
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
                command.run(backend.client(), args)
                return 0
        parser.print_help()
        return 2
    return 0
