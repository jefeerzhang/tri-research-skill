"""Stub ``requests`` so the SerpApi required-gate probe passes offline in tests.

The gate (``required_backends``) reuses ``SerpApiBackend.probe``, which calls
``requests.get(SERPAPI_BASE_URL, ...)``. ``required_backend_cli_env`` puts this
directory on ``PYTHONPATH`` (prepended before site-packages), so the stub shadows
the real ``requests`` inside the subprocess and the probe returns a fake 200 —
exactly like the ``exa_py`` / ``sciverse`` stub SDKs. This is NOT an
``ALLOW_DEGRADED`` env toggle: production runs never have this directory on
``PYTHONPATH``, so the real probe executes.

The surface is wider than ``get()`` on purpose: shadowing ``requests`` also
hides it from third-party packages imported in the same process (``tavily``
evaluates ``requests.Session`` in a class-body annotation at import time), and
an AttributeError there escapes as a traceback from ``state_machine start``.
Names below only need to exist, not to work.
"""

from __future__ import annotations


class _Response:
    status_code = 200

    def json(self) -> dict:
        return {"organic_results": []}


class Session:
    """Import-time placeholder; only ``requests.get`` is ever called here."""

    def get(self, *_args, **_kwargs) -> _Response:
        return _Response()


class _Exceptions:
    class RequestException(ConnectionError):
        pass

    class SSLError(RequestException):
        pass


exceptions = _Exceptions()


def get(*_args, **_kwargs) -> _Response:
    return _Response()
