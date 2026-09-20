"""Shared HTTP client factory.

httpx ships its own bundled CA store (via certifi) and, unlike `requests`
or the stdlib `ssl` module, does *not* automatically honor SSL_CERT_FILE /
REQUESTS_CA_BUNDLE. That's invisible on a normal machine (both stores agree)
and breaks hard behind a TLS-intercepting proxy that injects its own CA
(common in sandboxed dev environments, corporate networks, and CI runners).

This factory checks the standard env vars a proxied environment sets and
points httpx at that CA bundle when present, falling back to httpx's default
(certifi) otherwise — so the same code works unmodified on a bare machine
and behind a proxy that requires a custom root CA.
"""

from __future__ import annotations

import os
import ssl

import httpx

_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


def _resolve_verify() -> ssl.SSLContext | bool:
    """Return an SSL context trusting the environment's CA bundle, or True.

    Never returns False: verification is never disabled, only pointed at a
    different (still validating) trust store.
    """
    for var in _CA_ENV_VARS:
        path = os.environ.get(var)
        if path and os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return True  # httpx default: use its bundled certifi store


def make_client(*, timeout: float = 15.0, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers=headers or {}, verify=_resolve_verify())
