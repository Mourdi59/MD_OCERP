# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko
"""A cluster counts as ready when it answers, not when a function returns.

Attaching to an embedded cluster reads the cluster's own files. A data
directory left describing a postmaster that no longer exists therefore hands
back a perfectly well formed server object pointing at a port where nothing is
listening. The stage that announces the database then fires on the strength of
that object, and the very next connection fails, so the user is told the local
database is ready and the application server is not, in the same breath. Two
users on two different data directories saw exactly that pair of statements.

The recovery path already proved readiness by opening a socket. The happy path
did not, which is the whole defect: the check existed and was wired only to the
branch where something had already gone visibly wrong.

Second iteration, and the reason several cases here changed shape. Wiring the
probe everywhere was not enough, because the probe itself answered the wrong
question. Opening a socket proves a process is holding a port, not that a
database is behind it, and those come apart in the case that actually reaches
users: a run that dies after starting the cluster leaves the postmaster alive,
and a live postmaster keeps its listen socket whether or not it can still serve.
A user on a released build hit exactly that. The ready stage passed instantly,
by attaching to a postmaster an earlier crash had orphaned, and every connection
after it died mid-handshake with a reset.

So readiness is now decided by speaking the protocol and reading a reply, and a
bare listener is no longer a stand-in for a healthy cluster anywhere in this
file - it is the broken state. One case here asserted the opposite outright and
has been inverted rather than removed, since the question it asked was the right
one and only its expected answer was wrong.

The blind spot of this file: it stubs the attach, so it tests the decision this
module makes about a returned server, not pixeltable's behaviour when it
returns one. Whether a real cluster comes back after the retry clears the
leftovers is covered where a real cluster is started.
"""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from app.core.embedded_pg import (
    _boot_once,
    _cluster_answers,
    _listens_on_tcp,
    _unix_socket_path,
)


def _write_pidfile(pgdata: Path, port: int, *, pid: int | None = None) -> Path:
    """Write a postmaster.pid in PostgreSQL's own eight line shape."""
    pidfile = pgdata / "postmaster.pid"
    pidfile.write_text(
        "\n".join(
            [
                str(pid if pid is not None else os.getpid()),
                str(pgdata),
                str(int(time.time())),
                str(port),
                str(pgdata),
                "127.0.0.1",
                "",
                "ready",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return pidfile


def _a_port_nobody_listens_on() -> int:
    """Bind a loopback port, read it, and let it go again."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _StubPgserver:
    """Stands in for pixeltable, which hands back a handle without checking it."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_server(self, path: str) -> object:
        self.calls.append(path)
        return object()


class _AnsweringServer:
    """A listener that answers a StartupMessage the way a live postmaster does.

    A bare ``listen`` used to be an adequate stand-in for a healthy cluster here,
    because readiness was decided by whether a connection could be opened. It is
    not one any more, and that is not a change of convenience: a socket that
    accepts and never speaks is now the *broken* state this module has to catch,
    so using it to represent a healthy cluster would assert the defect.

    Answers with an ErrorResponse rather than an authentication request, to pin
    the deliberate half of the rule: a refusal proves a server is there to
    refuse, and a cluster that says "starting up" or "too many clients" is alive.
    """

    def __init__(self, family: int = socket.AF_INET, address: object | None = None) -> None:
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        if family == socket.AF_INET:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("127.0.0.1", 0))
            self.port = int(self._sock.getsockname()[1])
        else:
            self._sock.bind(str(address))
            self.port = 0
        self._sock.listen(8)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        body = b"SFATAL\x00C57P03\x00Mthe database system is starting up\x00\x00"
        reply = b"E" + (len(body) + 4).to_bytes(4, "big") + body
        while not self._stop.is_set():
            try:
                self._sock.settimeout(0.3)
                conn, _ = self._sock.accept()
            except OSError:
                continue
            with conn:
                try:
                    conn.recv(1024)
                    conn.sendall(reply)
                except OSError:
                    continue

    def __enter__(self) -> _AnsweringServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        self._sock.close()


def test_a_closed_port_is_not_an_answer() -> None:
    assert _cluster_answers.__doc__  # the helper is documented, not incidental
    pgdata = Path(os.environ.get("TEMP", ".")) / "does-not-matter"
    assert _cluster_answers(pgdata, 0.0) is False


def test_an_open_socket_alone_is_not_an_answer(tmp_path: Path) -> None:
    """Reversed on evidence: this case used to assert the bug.

    It read "an open socket is an answer", which was the rule the module had and
    the reason it shipped a false ready. A postmaster keeps its listen socket
    for as long as the process lives, so a run that died after starting the
    cluster leaves one that accepts and cannot serve. A real user's launcher
    attached to exactly that, announced the database ready, and then failed
    every connection it made.

    Kept rather than deleted, and inverted, because the case is the right one to
    ask; only the expected answer was wrong.
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        # A pid nothing owns: this must not reach the path that stops a process.
        _write_pidfile(tmp_path, int(listener.getsockname()[1]), pid=999_999_999)
        assert _cluster_answers(tmp_path, 1.0) is False


def test_a_server_that_answers_is_an_answer(tmp_path: Path) -> None:
    """The other half, now that answering means speaking rather than accepting."""
    with _AnsweringServer() as server:
        _write_pidfile(tmp_path, server.port, pid=999_999_999)
        assert _cluster_answers(tmp_path, 5.0) is True


def test_a_pidfile_port_with_nothing_behind_it_is_not_an_answer(tmp_path: Path) -> None:
    _write_pidfile(tmp_path, _a_port_nobody_listens_on())
    started = time.monotonic()
    assert _cluster_answers(tmp_path, 1.0) is False
    assert time.monotonic() - started < 10.0, "the probe must not outstay the window it was given"


def test_a_server_that_does_not_answer_is_not_returned_as_a_live_cluster(tmp_path: Path) -> None:
    """The defect itself, through the function the boot path calls."""
    _write_pidfile(tmp_path, _a_port_nobody_listens_on())
    stub = _StubPgserver()

    server, exc = _boot_once(cast(ModuleType, stub), tmp_path, tmp_path, None, time.monotonic() + 3.0)

    assert stub.calls, "the attach was never attempted, so this test proves nothing"
    assert server is None, (
        "A cluster was reported live on the strength of the attach returning. The caller then "
        "announces the local database ready and the first connection fails, which is the pair of "
        "statements the user reads on the diagnostics screen."
    )
    assert isinstance(exc, ConnectionError)
    assert "nothing answered" in str(exc)


def test_a_server_that_answers_is_returned(tmp_path: Path) -> None:
    """The opposite mistake would refuse every healthy boot."""
    with _AnsweringServer() as server:
        _write_pidfile(tmp_path, server.port, pid=999_999_999)
        stub = _StubPgserver()

        returned, exc = _boot_once(cast(ModuleType, stub), tmp_path, tmp_path, None, time.monotonic() + 10.0)

    assert returned is not None, "A healthy cluster was refused"
    assert exc is None


def test_a_healthy_attach_is_not_slowed_down(tmp_path: Path) -> None:
    """The probe is on the path of every desktop start, so it has to be cheap.

    Guards the cost of the handshake specifically. Proving readiness by speaking
    the protocol reads one byte more than opening a socket did, and this is the
    assertion that keeps that from turning into a wait every user pays.
    """
    with _AnsweringServer() as server:
        _write_pidfile(tmp_path, server.port, pid=999_999_999)
        started = time.monotonic()
        _boot_once(cast(ModuleType, _StubPgserver()), tmp_path, tmp_path, None, time.monotonic() + 10.0)
        elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"proving readiness cost {elapsed:.1f}s on a healthy cluster"


def _write_unix_only_pidfile(pgdata: Path, port: int, socket_dir: Path) -> None:
    """A pidfile in the shape PostgreSQL writes where it has no TCP listener.

    Line 5 names the unix socket directory and line 6, the first
    ``listen_addresses`` entry, is empty. That is what pixeltable-pgserver
    produces on Linux and macOS, and it is the shape the ready probe met in CI.
    """
    (pgdata / "postmaster.pid").write_text(
        "\n".join(
            [
                str(os.getpid()),
                str(pgdata),
                str(int(time.time())),
                str(port),
                str(socket_dir),
                "",
                "",
                "ready",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_a_unix_only_cluster_is_never_asked_for_a_tcp_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression that took the PostgreSQL lane red.

    pixeltable-pgserver starts the postmaster with no TCP listener on Linux and
    macOS: the server log says "listening on Unix socket" and nothing else. A
    probe that asks 127.0.0.1 therefore reports a cluster that is up, healthy
    and serving as dead, and the bounded retry then tears it down and rebuilds
    it twice more before giving up. The knowledge was already in this module,
    thirty lines above the probe, where a comment says get_uri() returns TCP on
    Windows and a unix socket elsewhere.

    Asserted as "does not ask" rather than "answers", so the case holds on a
    machine with no unix sockets at all.
    """

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("asked for a TCP connection on a cluster that has no TCP listener")

    monkeypatch.setattr(socket, "create_connection", _refuse)
    _write_unix_only_pidfile(tmp_path, 5432, tmp_path)

    assert _cluster_answers(tmp_path, 0.0) is False


def test_a_unix_socket_that_answers_is_enough(tmp_path: Path) -> None:
    """And the other half: a unix socket that speaks makes the cluster ready.

    This case runs only where PostgreSQL uses unix sockets, which is the
    platform the PostgreSQL lane runs on and not the one this file is usually
    edited on. It answers the protocol for the same reason the TCP cases do: a
    bare ``listen`` is now the broken state, so a stand-in that only listened
    would take the lane red on Linux while passing as a skip on Windows.
    """
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("no unix domain sockets on this platform")

    port = 5432
    # The socket goes somewhere short. A unix address carries its whole path
    # inside a fixed field - 104 bytes on macOS, 108 on Linux - and pytest's
    # tmp_path on a macOS runner has already spent most of that on this test's
    # own name before the socket file is appended, so binding raised
    # "AF_UNIX path too long" and every macOS shard failed on it. Only the
    # socket directory moves: the pidfile stays in tmp_path, and its fifth line
    # is what names the socket directory, so the code under test is asked the
    # same question it was asked before.
    sock_dir = Path(tempfile.mkdtemp(prefix="oe-sock-", dir="/tmp" if os.path.isdir("/tmp") else None))
    sock_path = sock_dir / f".s.PGSQL.{port}"
    # Assert the address fits rather than discovering it did not from an OSError
    # that names no limit. 100 leaves room under the smaller of the two caps.
    assert len(str(sock_path).encode("utf-8")) < 100, f"socket address is too long to bind: {sock_path}"
    try:
        with _AnsweringServer(family=socket.AF_UNIX, address=sock_path):
            _write_unix_only_pidfile(tmp_path, port, sock_dir)

            assert _cluster_answers(tmp_path, 5.0) is True
    finally:
        sock_path.unlink(missing_ok=True)
        shutil.rmtree(sock_dir, ignore_errors=True)


def test_the_socket_is_the_one_postgresql_names(tmp_path: Path) -> None:
    """``<socket dir>/.s.PGSQL.<port>``, and nothing where there is no socket."""
    _write_unix_only_pidfile(tmp_path, 54321, tmp_path / "sockets")
    assert _unix_socket_path(tmp_path) == tmp_path / "sockets" / ".s.PGSQL.54321"

    # The Windows shape: line 5 empty, because there are no unix sockets there.
    _write_pidfile(tmp_path, 54321)
    assert _unix_socket_path(tmp_path) is not None  # helper writes a socket dir
    (tmp_path / "postmaster.pid").write_text(
        "\n".join([str(os.getpid()), str(tmp_path), "0", "54321", "", "127.0.0.1", "", "ready"]) + "\n",
        encoding="utf-8",
    )
    assert _unix_socket_path(tmp_path) is None


def test_a_pidfile_too_short_to_answer_does_not_rule_tcp_out(tmp_path: Path) -> None:
    """Absent information is not evidence of absence.

    A pidfile being written while the postmaster starts is truncated, and a
    probe that reads "no listen address" out of a line that has not been written
    yet would skip the only family a Windows cluster has.
    """
    (tmp_path / "postmaster.pid").write_text(
        "\n".join([str(os.getpid()), str(tmp_path), "0", "54321"]) + "\n",
        encoding="utf-8",
    )
    assert _listens_on_tcp(tmp_path) is True
