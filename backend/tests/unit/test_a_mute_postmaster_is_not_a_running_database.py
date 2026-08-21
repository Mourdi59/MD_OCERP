# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""A listen socket is not a database, and the readiness probe has to know that.

A released build announced "Embedded PostgreSQL ready" and then failed every
connection it made in the next breath. The cluster it attached to was a
postmaster left alive by an earlier run that had died after starting it: the
process still held its listen socket, so a bare ``connect`` succeeded and the
probe reported a healthy database, while nothing behind that socket could serve
a session.

These tests pin both halves of the answer. The probe has to speak the protocol
rather than open a socket, and the recovery has to end a postmaster that only
listens - detection alone would leave the user exactly as stuck, with a better
worded failure.

The three states are deliberately distinguished, because two of them must never
be acted on: a cluster replaying WAL has not opened its socket yet, and a
cluster too busy to take another client answers with an error, which is an
answer. Only "accepts and says nothing" is the broken one.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.core import embedded_pg


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _write_pidfile(pgdata: Path, pid: int, port: int) -> None:
    """Write a postmaster.pid in PostgreSQL's own layout.

    Line 4 is the port and line 6 is the first ``listen_addresses`` entry, which
    is what the probe reads to decide whether to try TCP at all. Line 5 is the
    unix socket directory, left empty here so the TCP branch is the one under
    test on every platform.
    """
    pgdata.mkdir(parents=True, exist_ok=True)
    (pgdata / "postmaster.pid").write_text(
        f"{pid}\n{pgdata}\n{int(time.time())}\n{port}\n\n127.0.0.1\n  1234567 0\n",
        encoding="utf-8",
    )


class _FakeServer:
    """A socket that behaves like a postmaster in one of three ways."""

    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour
        self.port = _free_port()
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(8)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                self._sock.settimeout(0.3)
                conn, _ = self._sock.accept()
            except OSError:
                continue
            with conn:
                if self.behaviour == "mute":
                    # Accept and drop it. This is the shipped failure: the TCP
                    # handshake completes, so a bare connect is satisfied, and
                    # the client's startup packet is answered by a reset.
                    continue
                if self.behaviour == "silent":
                    # Accept and hold it open saying nothing, the other way a
                    # wedged server looks from outside.
                    time.sleep(2.0)
                    continue
                try:
                    conn.recv(1024)
                except OSError:
                    continue
                if self.behaviour == "authenticating":
                    conn.sendall(b"R\x00\x00\x00\x08\x00\x00\x00\x00")
                elif self.behaviour == "erroring":
                    # "the database system is starting up" - a refusal, and
                    # therefore proof that a live server is there to refuse.
                    body = b"SFATAL\x00C57P03\x00Mthe database system is starting up\x00\x00"
                    conn.sendall(b"E" + (len(body) + 4).to_bytes(4, "big") + body)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        self._sock.close()


@pytest.fixture
def server(request: pytest.FixtureRequest):
    srv = _FakeServer(request.param)
    yield srv
    srv.close()


@pytest.mark.parametrize("server", ["mute", "silent"], indirect=True)
def test_a_socket_that_opens_and_never_speaks_is_not_a_running_database(
    server: _FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression. Both shapes of a wedged server read as ``mute``.

    The bare-connect assertion below is the point: it is what the probe used to
    do, it passes against this server, and that is precisely how a launcher came
    to announce a database that could not answer.
    """
    monkeypatch.setattr(embedded_pg, "_PROBE_REPLY_SECONDS", 0.5)
    _write_pidfile(tmp_path, pid=999_999_999, port=server.port)

    with socket.create_connection(("127.0.0.1", server.port), timeout=2):
        pass  # The old probe's whole test, and it succeeds here.

    assert embedded_pg._probe_cluster(tmp_path) == embedded_pg._MUTE
    assert embedded_pg._accepts_a_connection(tmp_path) is False


@pytest.mark.parametrize("server", ["authenticating"], indirect=True)
def test_a_server_that_speaks_the_protocol_is_reported_answering(server: _FakeServer, tmp_path: Path) -> None:
    _write_pidfile(tmp_path, pid=999_999_999, port=server.port)

    assert embedded_pg._probe_cluster(tmp_path) == embedded_pg._ANSWERING
    assert embedded_pg._accepts_a_connection(tmp_path) is True


@pytest.mark.parametrize("server", ["erroring"], indirect=True)
def test_a_refusal_counts_as_alive(server: _FakeServer, tmp_path: Path) -> None:
    """A cluster that says "starting up" or "too many clients" is alive.

    This is the guard against the opposite and larger mistake. Reading an error
    reply as death would let the recovery path end a healthy cluster that was
    merely busy, or one still finishing its own start.
    """
    _write_pidfile(tmp_path, pid=999_999_999, port=server.port)

    assert embedded_pg._probe_cluster(tmp_path) == embedded_pg._ANSWERING


def test_nothing_listening_reads_as_closed_not_mute(tmp_path: Path) -> None:
    """A cluster still replaying WAL has no socket open, and must not be touched.

    ``closed`` is the state the patient recovery wait already handles, so it has
    to stay distinguishable from ``mute``; collapsing the two would put a
    recovering database on the path that stops one.
    """
    _write_pidfile(tmp_path, pid=999_999_999, port=_free_port())

    assert embedded_pg._probe_cluster(tmp_path) == embedded_pg._CLOSED


@pytest.mark.parametrize("server", ["authenticating", "erroring"], indirect=True)
def test_the_recovery_refuses_a_cluster_that_answers(server: _FakeServer, tmp_path: Path) -> None:
    """The safety property, asserted with a pid that is alive and is ours.

    If the guard were ever wrong in this direction the test process itself would
    be the thing it ended, which is the most direct way to state that a cluster
    which answers is never stopped.
    """
    import os

    _write_pidfile(tmp_path, pid=os.getpid(), port=server.port)

    assert embedded_pg._stop_mute_postmaster(tmp_path) is False
    assert (tmp_path / "postmaster.pid").exists()


def test_the_recovery_refuses_when_the_pid_is_already_gone(tmp_path: Path) -> None:
    _write_pidfile(tmp_path, pid=999_999_999, port=_free_port())

    assert embedded_pg._stop_mute_postmaster(tmp_path) is False


def _pid_listening_on(psutil, port: int, spawned_pid: int) -> int | None:
    """The pid holding *port*, asked of the machine and then of our own process.

    The machine-wide socket table is the direct question and the only one that
    can answer without assuming who the listener is. macOS refuses it: psutil
    needs root for a system-wide ``net_connections`` there and raises
    ``AccessDenied`` instead, which is not "no listener" and must not be read
    as one. Every macOS shard of the backend matrix failed on that raise.

    So the fallback asks the processes we started ourselves, which the same
    platform does allow, walking the spawned child and its descendants. The
    indirection is why this is a fallback rather than the primary: a virtualenv
    launcher re-executes, so the listener can be a grandchild, and PostgreSQL's
    postmaster is its own listener, so a pidfile names the owner. Naming the
    owner is what the guard under test checks, which is why the test has to
    name it rather than assume it is the pid Popen returned.

    Returns the pid, or None when neither route can name one, which the caller
    turns into a skip rather than a failure.
    """
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == psutil.CONN_LISTEN and getattr(conn.laddr, "port", None) == port and conn.pid:
                return conn.pid
    except (psutil.AccessDenied, PermissionError):
        pass

    try:
        spawned = psutil.Process(spawned_pid)
        candidates = [spawned, *spawned.children(recursive=True)]
    except psutil.Error:
        return None
    for proc in candidates:
        # psutil 6 renamed ``Process.connections`` to ``net_connections`` and
        # kept the old name as a deprecated alias. Ask for whichever this
        # installation has rather than pinning the suite to one of them.
        reader = getattr(proc, "net_connections", None) or getattr(proc, "connections", None)
        if reader is None:
            return None
        try:
            for conn in reader(kind="inet"):
                if conn.status == psutil.CONN_LISTEN and getattr(conn.laddr, "port", None) == port:
                    return proc.pid
        except (psutil.Error, PermissionError):
            continue
    return None


def test_the_recovery_stops_a_real_process_that_only_listens(tmp_path: Path) -> None:
    """End to end on the half that makes the user's machine start again.

    A child process holds a socket open and never speaks, exactly as the
    orphaned postmaster did, and is named by a pidfile the way PostgreSQL names
    one. The assertion is that the process is gone and the pidfile with it, so
    the next boot attempt starts a cluster instead of attaching to this one.
    """
    port = _free_port()
    child = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "import socket,time\n"
                "s=socket.socket()\n"
                "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)\n"
                f"s.bind(('127.0.0.1',{port}))\n"
                "s.listen(8)\n"
                "time.sleep(120)\n"
            ),
        ],
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("the stand-in listener never came up")

        # The pid that HOLDS the port, which is not always the pid Popen
        # returned: a virtualenv launcher re-executes, so the listener can be a
        # grandchild. PostgreSQL's postmaster is its own listener, so a pidfile
        # names the owner - and naming the owner is exactly what the guard
        # checks, so the test has to name it too rather than assume.
        psutil = pytest.importorskip("psutil")
        owner = _pid_listening_on(psutil, port, child.pid)
        if owner is None:
            pytest.skip("the socket table does not name a listener for this port on this machine")

        _write_pidfile(tmp_path, pid=owner, port=port)
        assert embedded_pg._probe_cluster(tmp_path) == embedded_pg._MUTE

        assert embedded_pg._stop_mute_postmaster(tmp_path) is True
        assert not psutil.pid_exists(owner)
        assert not (tmp_path / "postmaster.pid").exists()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
