"""Stub ``requests`` so the SerpApi required-gate probe passes offline in tests.

The gate (``required_backends``) reuses ``SerpApiBackend.probe``, which calls
``requests.get(SERPAPI_BASE_URL, ...)``. ``required_backend_cli_env`` puts this
directory on ``PYTHONPATH`` (prepended before site-packages), so the stub shadows
the real ``requests`` inside the subprocess and the probe returns a fake 200 —
exactly like the ``exa_py`` / ``sciverse`` stub SDKs. This is NOT an
``ALLOW_DEGRADED`` env toggle: production runs never have this directory on
``PYTHONPATH``, so the real probe executes.

Only the probe path is exercised here; ``requests.get`` never raises, so the
``except requests.exceptions.*`` clauses in ``_serpapi_fetch`` are not evaluated.
"""

from __future__ import annotations


class _Response:
    status_code = 200

    def json(self) -> dict:
        return {"organic_results": []}


def get(*_args, **_kwargs) -> _Response:
    return _Response()
