# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Which asyncio event loop the HTTP server runs on.

On Windows the server runs on asyncio's selector loop instead of the proactor
loop that uvicorn picks there by default. Linux and macOS are untouched: they
keep whatever uvicorn chooses (uvloop when installed, else the selector loop,
which is what this module picks on Windows too).

Why: CPython's proactor loop closes the LISTENING socket when one accept fails.
``BaseProactorEventLoop._start_serving`` (Lib/asyncio/proactor_events.py in
3.12) catches any ``OSError`` from the accept future, logs "Accept failed on a
socket" and calls ``sock.close()`` on the listener, and nothing ever opens it
again. The process stays up, the port answers "connection refused", and to a
desktop user the app is frozen until it is restarted. A single client that
resets its connection while it waits in the listen backlog is enough: Windows
then completes the next ``AcceptEx`` with ``ERROR_NETNAME_DELETED`` (WinError
64). Browsers do exactly that when the server is slow to accept, which is when
it happened in the field: a test server logged the WinError 64 at 11:45:08 and
never accepted another connection.

The selector loop has no such path. ``BaseSelectorEventLoop._accept_connection``
re-raises an unexpected accept error into the event loop's exception handler,
which logs it, and the listener stays registered and open. Measured on Windows
11 / CPython 3.12.11 with one reset client in the backlog: the proactor loop
closed the listener and refused the next client; the selector loop served it.
``backend/tests/unit/test_the_windows_server_loop_survives_a_reset_client.py``
replays that with real sockets.

What the selector loop gives up on Windows, checked before choosing it:

* asyncio subprocesses (``create_subprocess_exec`` / ``_shell``) are not
  supported. ``backend/app`` uses none; every child process goes through the
  blocking ``subprocess`` module.
* ``select()`` is limited to 512 sockets per set on Windows. The desktop
  sidecar serves one person on 127.0.0.1 and is nowhere near it. A LAN server
  started with ``serve --host 0.0.0.0`` on Windows (the documented Task
  Scheduler setup in docs/install/autostart/) would fail loudly above roughly
  500 concurrent sockets, where the proactor loop goes deaf on the first reset
  client. Linux servers and the Docker image are not affected by either.
* Nothing else: the test suite has run asyncpg on this loop under Windows for
  a long time (see ``backend/tests/conftest.py``), and uvicorn itself uses it
  on Windows whenever it runs with ``--reload`` or ``--workers``.
"""

from __future__ import annotations

import asyncio
import logging
import sys

logger = logging.getLogger(__name__)


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Create the event loop the server runs on under Windows.

    uvicorn calls this with no arguments through ``asyncio.Runner`` when it is
    named in ``loop=`` (see :func:`uvicorn_loop_option`).

    Returns:
        A new ``asyncio.SelectorEventLoop``.
    """
    return asyncio.SelectorEventLoop()


def uvicorn_loop_option() -> str:
    """Return the ``loop=`` value to pass to ``uvicorn.run`` on this platform.

    Off Windows this is ``"auto"``, uvicorn's own default, so nothing changes
    there. On Windows it is the import string of :func:`selector_loop_factory`,
    built from the function itself so a rename cannot leave a stale string
    behind. The caller has imported this module to call this function, so
    uvicorn's ``import_from_string`` always resolves it, frozen bundle included.

    uvicorn reads a ``module:callable`` loop value as a loop factory from 0.36
    on (``Config.get_loop_factory``). Older releases, still allowed by the
    ``>=0.32`` pin, raise on a value they do not know, so there the server
    starts on uvicorn's default loop as before and a warning says why.

    Returns:
        The value for ``uvicorn.run(..., loop=...)``.
    """
    if sys.platform != "win32":
        return "auto"

    import uvicorn

    if not hasattr(uvicorn.Config, "get_loop_factory"):
        logger.warning(
            "uvicorn %s cannot take a custom event loop; the server keeps the proactor loop, which "
            "stops accepting connections after a client resets one. Upgrade uvicorn to 0.36 or later.",
            getattr(uvicorn, "__version__", "?"),
        )
        return "auto"
    return f"{selector_loop_factory.__module__}:{selector_loop_factory.__qualname__}"
