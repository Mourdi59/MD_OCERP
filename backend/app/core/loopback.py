"""Is this request coming from the machine the server runs on.

Two endpoints answer only to the local desktop shell - the first-run bootstrap
that auto-provisions the workspace owner, and the shutdown request the launcher
sends on its way out - and both of them are dangerous exactly to the degree that
somebody else can reach them. That makes this check a security guard, and a
security guard written twice is a security guard that can be right in one copy
and wrong in the other, so it lives here once.
"""

from __future__ import annotations

import os

from fastapi import Request

#: Hosts the desktop sidecar may legitimately be reached on. The Tauri shell
#: talks to the bundled backend over 127.0.0.1, so anything else is a remote
#: caller that must never reach a desktop-only path.
LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})


def running_under_pytest() -> bool:
    """True when this process is a pytest run.

    The ASGI test transport can leave ``request.client`` unset, so the loopback
    guard would otherwise reject every test call. Only the ``client is None``
    case is relaxed under this marker - a real server with a missing client
    (which would be unusual) is still rejected.
    """
    return "PYTEST_CURRENT_TEST" in os.environ


def is_loopback_request(request: Request) -> bool:
    """Return True when the request originates from the local loopback.

    Args:
        request: The incoming request.

    Returns:
        ``True`` for a client on this machine. ``request.client`` is ``None``
        under the ASGI test transport; that case is treated as loopback only
        when running under pytest, and rejected otherwise.
    """
    client = request.client
    if client is None:
        return running_under_pytest()
    return client.host in LOOPBACK_HOSTS
