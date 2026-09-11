"""Shared exceptions for the tri-research runtime (ADR-0015).

CLI dialects still render these themselves: the package only owns the types.
"""

from __future__ import annotations


class StateError(RuntimeError):
    """A state-machine / evidence-ledger operation failed.

    Lives in this leaf module so both execution forms of state_machine.py
    (as ``__main__`` and as the ``state_machine`` module imported by
    evidence.py) share ONE class: a StateError raised inside evidence must
    be caught by state_machine's ``except StateError`` even when it
    imported state_machine a second time under its module name.
    """


class CircuitOpenError(RuntimeError):
    """Raised when a backend circuit is open; not retryable, fail-fast.

    The circuit is process-level (counters on the ``Backend`` instance in
    this process). A new CLI invocation starts closed. Not shared across
    processes, hosts, or skills (ADR-0015).
    """


class ClientSetupError(RuntimeError):
    """The SDK client could not be set up; ``str(exc)`` is the user-facing text.

    Raised rather than printed so every caller keeps its own dialect (JSON
    error + exit 1, ``{"available": false}``, a collected gap string, or a
    bare raise) while the *conditions* stay defined in exactly one place —
    ``Backend.client``.
    """


class KeyMissing(ClientSetupError):
    """No API key from cli / env / the backend's own declared ``.env``."""


class SdkMissing(ClientSetupError):
    """The backend's SDK module failed to import, so no client can exist."""


class CommandError(RuntimeError):
    """Domain failure raised by a managed command body; never retried."""
