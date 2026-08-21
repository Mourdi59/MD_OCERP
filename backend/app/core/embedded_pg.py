# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Optional embedded PostgreSQL runtime - a real PG16 in-process, no Docker.

Boots a PostgreSQL 16 cluster from the ``pixeltable-pgserver`` wheel (bundled PG
binaries) and points the app's ``DATABASE_URL`` / ``DATABASE_SYNC_URL`` at it, so
the whole app runs on PostgreSQL with zero external setup. This is the default
runtime; the operator opts out only by supplying an external ``DATABASE_URL`` or
setting ``OE_USE_EMBEDDED_PG`` to a falsy value (see :func:`is_requested`).

The cluster's data directory is ``<data_dir>/pgdata`` so it survives restarts.
On first boot ``initdb`` runs once (a few seconds); subsequent boots attach to the
existing cluster.

Ordering contract
~~~~~~~~~~~~~~~~~
``app.database`` builds the SQLAlchemy engine from ``settings.database_url`` at
*import time*. :func:`boot` therefore MUST run before the first ``from app...``
import that pulls in ``app.database`` (and before ``get_settings()`` is cached).
The CLI calls it from ``_setup_env``, which every command runs before importing
any app module - so the contract holds for ``serve``/``init-db``/``seed``.

Single-process only: run ONE uvicorn worker with embedded PG (the default). For
multi-worker deployments use an external PostgreSQL and set ``DATABASE_URL``
directly.
"""

from __future__ import annotations

import logging
import os
import socket
import struct
import subprocess
import time
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

logger = logging.getLogger(__name__)

# How far the recorded postmaster start time may sit from the actual creation
# time of the process holding that PID before we call the PID recycled. The
# two are written within the same second on a healthy cluster, so this is
# generous rather than tight; it only has to separate the same process from a
# different one.
_PID_START_TOLERANCE_SECONDS = 10.0

# How long a cluster that has just been handed back as ready gets to answer a
# connection before we treat it as absent. A healthy one answers on the first
# try, and a genuinely recovering one never reaches here because get_server()
# raises and the recovery path waits it out on the patient budget instead.
_READY_PROBE_SECONDS = 20.0

#: Module-level handle to the running server, kept so :func:`shutdown` can stop it.
_server = None

#: Set by :func:`retain` when something outside the application owns the cluster's
#: lifetime, so an application shutdown inside that owner's run leaves it running.
_retained = False

#: Set by :func:`boot` when it can name the reason it refused to start. The CLI
#: prints this in place of its generic "reinstall and try again" advice, which is
#: wrong for the failures we can diagnose precisely - see
#: :func:`data_dir_version_conflict`, where reinstalling makes the mismatch worse
#: rather than better. ``None`` means "no specific diagnosis", not "no failure".
_fatal_detail: str | None = None

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

#: Support contact surfaced (in the log) when embedded PostgreSQL cannot start.
_CONTACT_EMAIL = "info@datadrivenconstruction.io"


def emit_stage(stage: str, status: str, detail: str = "") -> None:
    """Emit one machine-readable boot-progress marker on stdout (and the log).

    The desktop launcher (Tauri shell) pumps the sidecar's stdout into its own
    diagnostic log and parses these ``STAGE:`` lines to drive the visible boot
    checklist, so the user always sees which step is running and exactly where a
    startup failure happened. The format is deliberately simple and stable:

        ``STAGE:<stage>:<status>[:<detail>]``

    where ``stage`` is a short identifier (``pg``, ``migrate``, ``server`` ...),
    ``status`` is one of ``start`` / ``progress`` / ``done`` / ``fail``, and the
    optional ``detail`` is free human text (no newlines, no colons are required
    to be escaped because the consumer splits on the first three only).

    Best effort: never raises, so progress reporting can never break startup.
    """
    try:
        clean_detail = detail.replace("\n", " ").replace("\r", " ").strip()
        line = f"STAGE:{stage}:{status}"
        if clean_detail:
            line += f":{clean_detail}"
        # stdout is the transport the launcher watches; flush so the marker is
        # delivered immediately rather than sitting in a block buffer.
        print(line, flush=True)
        logger.info(line)
    except Exception:  # noqa: BLE001
        pass


def is_requested() -> bool:
    """True when the app should run on the embedded PostgreSQL cluster.

    Embedded PostgreSQL is the **default** runtime - a fresh
    ``openconstructionerp serve`` boots a real in-process PG16 (no Docker). The
    operator opts out in either of two ways, checked in order:

    * an explicit ``DATABASE_URL`` in the environment - "use my own database",
      so we never override it with an embedded cluster;
    * ``OE_USE_EMBEDDED_PG`` set to a falsy value (``0``/``false``/``no``/``off``)
      - explicit opt-out (typically paired with an external PG set via
      ``DATABASE_URL``, which is also covered by the rule above).

    Otherwise (the default, and any truthy ``OE_USE_EMBEDDED_PG``) it returns
    ``True``. An explicit truthy ``OE_USE_EMBEDDED_PG`` wins over an ambient
    ``DATABASE_URL`` (the two together are contradictory; the explicit flag is
    the clearer intent).
    """
    explicit = os.environ.get("OE_USE_EMBEDDED_PG", "").strip().lower()
    if explicit in _TRUTHY:
        return True
    if os.environ.get("DATABASE_URL", "").strip():
        return False
    if explicit in _FALSY:
        return False
    return True


def is_running() -> bool:
    """True once :func:`boot` has successfully started a cluster this process."""
    return _server is not None


def last_fatal_detail() -> str | None:
    """Return the specific reason the last :func:`boot` refused, when it had one.

    :func:`boot` never raises and reports failure as ``False``, which tells the
    caller that something went wrong and nothing about what. For the failures it
    can actually name it also records the explanation here, so the CLI can print
    that instead of the generic advice it would otherwise give. ``None`` means
    boot had no specific diagnosis to offer, not that it succeeded.
    """
    return _fatal_detail


def boot(data_dir: Path | str) -> bool:
    """Boot embedded PostgreSQL and point DATABASE_URL/DATABASE_SYNC_URL at it.

    Idempotent (a second call is a no-op once running). Never raises: on any
    failure it logs and returns ``False``. There is no SQLite fallback, so a
    ``False`` here is fatal at the CLI layer (``_setup_env`` exits with an
    actionable message). Returns ``True`` on success.
    """
    global _server, _fatal_detail
    if _server is not None:
        return True
    _fatal_detail = None

    try:
        import pixeltable_pgserver as pgserver
        from sqlalchemy.engine import make_url
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "embedded PostgreSQL requested but pixeltable-pgserver is not importable "
            "(reinstall the package: pip install --upgrade --force-reinstall "
            "openconstructionerp, or install pixeltable-pgserver directly): %r",
            exc,
        )
        return False

    pgdata = Path(data_dir).expanduser() / "pgdata"
    try:
        pgdata.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("embedded PostgreSQL data dir unavailable at %s: %r", pgdata, exc)
        return False

    # Settle major-version compatibility before anything touches the cluster.
    # The postmaster would refuse this directory anyway, but it refuses from
    # inside the retry loop below, where the reason is buried under three
    # attempts and reported as "the local database could not be started" - and
    # the generic advice attached to that failure is to reinstall, which on a
    # version bump is what caused it. Answering here means the user is told
    # which two versions disagree while every byte of their data is still on
    # disk, and is offered the recoveries that keep it before the one that does
    # not. A directory we cannot read a version from is not a conflict, so a
    # fresh install (no PG_VERSION yet) walks straight past this.
    conflict = data_dir_version_conflict(pgdata)
    if conflict is not None:
        _fatal_detail = conflict.message
        # The stage detail names both versions, not just the fact that they
        # differ. This is the desktop app's failure - a bundled-PG bump is what
        # strands an existing cluster - and on the desktop the only surface the
        # user sees is the launcher checklist, which renders this string. The
        # paragraph below it goes to the log file, which somebody stuck on a
        # window that will not open is not reading.
        emit_stage(
            "pg",
            "fail",
            f"The local database was created by PostgreSQL {conflict.found}; "
            f"this build ships PostgreSQL {conflict.expected}",
        )
        logger.error("%s", conflict.message)
        return False

    # pixeltable-pgserver hard-codes a 10s ``pg_ctl start -w`` timeout
    # (postgres_server.py). After an unclean shutdown (force-kill, crash, power
    # loss) PostgreSQL replays its WAL on the next boot. On a large cluster that
    # replay also fsyncs every file in the data directory, which can take SEVERAL
    # MINUTES (observed ~140s on a 1.2 GB cluster on Windows). The 10s pg_ctl
    # wait therefore always times out, and pixeltable's pidfile parser then
    # raises AssertionError because, while recovery is in progress, PostgreSQL
    # writes only the first lines of postmaster.pid (the port/status lines are
    # added once it is ready) -- so the file does not yet have the 8 lines the
    # parser asserts on. Both failures mean a fixed-attempt retry gives up long
    # before recovery finishes, the sidecar exits, and the desktop window shows
    # nothing.
    #
    # The robust fix: launch the postmaster ourselves once, then WAIT for the
    # cluster to actually accept connections (probing the real port, not the
    # fragile pidfile) for a generous window, and only then hand off to
    # get_server(), which now simply attaches to the already-running, ready
    # postmaster (no pg_ctl, no timeout, complete pidfile).
    resolved_pgdata = pgdata.expanduser().resolve()

    try:
        from pixeltable_pgserver.postgres_server import PostgresServer as _PS
    except Exception:  # noqa: BLE001
        _PS = None

    # A leftover postmaster.pid whose process is gone (the usual aftermath of a
    # force-kill) makes pixeltable take its slower "found a pid file but server
    # not running" path; clearing it first keeps boot on the clean-start path.
    _clear_stale_pidfile(resolved_pgdata)

    # Embedded PG must initialise with an ASCII-safe locale. PostgreSQL's initdb
    # rejects a locale *name* that contains non-ASCII characters, and the bundled
    # initdb otherwise inherits the operating-system locale. On a Turkish Windows
    # box that locale is "Turkish_Türkiye.1254": initdb aborts with `locale name
    # ... contains non-ASCII characters`, then pixeltable crashes a second time
    # decoding that CP1254 error text as UTF-8, and the cluster is left stuck
    # "Recovering the local database" forever. Force the C locale for every PG
    # child process, and pre-create the cluster ourselves with an explicit
    # --locale=C so pixeltable's own (locale-inheriting) initdb is skipped: on
    # Windows env vars do NOT override the OS locale that initdb reads.
    #
    # Order matters. Pre-creating the cluster is also what gives us a
    # postgresql.conf to write before the postmaster first starts, which the
    # settings below need to be effective on a fresh machine. All three are
    # no-ops once the cluster exists and is configured.
    _apply_ascii_locale_env()
    _pre_initialize_cluster(resolved_pgdata)
    _apply_server_settings(resolved_pgdata)

    emit_stage("pg", "start", "Starting embedded PostgreSQL")

    # Window for the whole bring-up, including a possibly slow crash recovery.
    # Override with OE_PG_BOOT_TIMEOUT (seconds) for very large clusters or slow
    # disks. 600s comfortably covers multi-minute fsync-based recovery. This is
    # the PATIENT budget a genuinely recovering cluster gets; it is SHARED across
    # the bounded retry below, so retrying never multiplies the total wait.
    boot_timeout = _int_env("OE_PG_BOOT_TIMEOUT", 600)
    deadline = time.monotonic() + boot_timeout

    # Bounded retry around the bring-up. A transient failure to come up (a brief
    # file lock, an antivirus scan mid-start, a leftover "server does not shut
    # down" pidfile) is retried a few times with a short backoff before we give
    # up, so one flaky start becomes a clean retry instead of an opaque crash.
    # Capped by OE_PG_BOOT_ATTEMPTS (default 3, hard-limited to 1..5) so we never
    # loop forever; the only added wait is the short backoff between attempts. A
    # genuinely recovering cluster never reaches a second attempt - _boot_once
    # waits it out patiently within the shared deadline and returns success.
    attempts = min(max(_int_env("OE_PG_BOOT_ATTEMPTS", 3), 1), 5)
    srv: object | None = None
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        # A leftover pidfile from a dead postmaster (force-kill / crash / the
        # "server does not shut down" case) pushes pixeltable onto its slow path;
        # clear it before every attempt so each retry starts from a clean state.
        _clear_stale_pidfile(resolved_pgdata)
        srv, last_exc = _boot_once(pgserver, pgdata, resolved_pgdata, _PS, deadline)
        if srv is not None:
            break
        if attempt < attempts and time.monotonic() < deadline:
            backoff = min(1.5 * attempt, 3.0)
            logger.warning(
                "embedded PostgreSQL bring-up attempt %d/%d failed (%r); retrying in %.1fs",
                attempt,
                attempts,
                last_exc,
                backoff,
            )
            emit_stage(
                "pg",
                "progress",
                f"Restarting the local database (attempt {attempt + 1} of {attempts})",
            )
            time.sleep(backoff)

    if srv is None:
        emit_stage("pg", "fail", _pg_failure_detail(resolved_pgdata, last_exc))
        logger.error(
            "embedded PostgreSQL failed to start at %s after %d attempt(s): %r. The real "
            "cause is in the PostgreSQL log at %s and the launcher log at %s. If this keeps "
            "happening, reinstall the package or send those two logs to %s.",
            pgdata,
            attempts,
            last_exc,
            resolved_pgdata / "log",
            _launcher_log_path(),
            _CONTACT_EMAIL,
        )
        return False

    emit_stage("pg", "done", "Embedded PostgreSQL ready")

    try:
        # get_uri() is portable: TCP loopback on Windows, a unix socket on
        # Linux/macOS. Swap only the SQLAlchemy driver - never hand-parse it.
        base = make_url(srv.get_uri())

        # Pin a TCP loopback host to the IPv4 literal 127.0.0.1.
        #
        # On Windows the embedded postmaster is launched by pixeltable-pgserver
        # with ``-h "127.0.0.1"``, so it listens on IPv4 loopback ONLY (never on
        # IPv6 ``::1``). But get_uri() can hand back a loopback *name*
        # ("localhost") read from postmaster.pid, and on Windows "localhost" may
        # resolve to ``::1`` first - a Windows 11 upgrade can flip the resolver
        # to prefer IPv6. asyncpg then dials ``::1``, where nothing is listening,
        # and the first startup connection is refused with WinError 1225 even
        # though the cluster is up and healthy. That is exactly the reported
        # failure: the "Embedded PostgreSQL ready" stage passed (our readiness
        # probe in _wait_until_connectable connects to 127.0.0.1 explicitly), yet
        # "Starting the application server" died on the first asyncpg connect.
        # Rewriting a loopback host to 127.0.0.1 makes the app URL agree with the
        # address the server actually listens on and with the readiness probe.
        #
        # This only touches the TCP (Windows) embedded path: on Linux/macOS
        # get_uri() returns a unix-socket URI whose host is None (the socket dir
        # lives in the query string), so the guard below is skipped and that path
        # is unchanged. An external/remote DATABASE_URL the operator set never
        # reaches here - boot() runs solely for the embedded cluster.
        if (base.host or "").lower() in {"localhost", "::1", "ip6-localhost", "127.0.0.1"}:
            base = base.set(host="127.0.0.1")

        async_url = base.set(drivername="postgresql+asyncpg")
        sync_url = base.set(drivername="postgresql+psycopg2")
        os.environ["DATABASE_URL"] = async_url.render_as_string(hide_password=False)
        os.environ["DATABASE_SYNC_URL"] = sync_url.render_as_string(hide_password=False)
    except Exception as exc:  # noqa: BLE001
        logger.error("embedded PostgreSQL booted but URL wiring failed: %r", exc)
        try:
            srv.cleanup()
        except Exception:  # noqa: BLE001
            pass
        return False

    _server = srv
    logger.info("embedded PostgreSQL ready (data dir: %s)", pgdata)
    return True


def _boot_once(
    pgserver: ModuleType,
    pgdata: Path,
    resolved_pgdata: Path,
    ps_cls: type | None,
    deadline: float,
) -> tuple[object | None, Exception | None]:
    """One embedded-PostgreSQL bring-up attempt, sharing the overall ``deadline``.

    Returns ``(server, None)`` as soon as ``get_server()`` hands back a live
    cluster, or ``(None, last_exc)`` when this attempt could not bring one up.

    A ``get_server()`` failure is triaged before we decide how long to wait:

    * If a **live postmaster** owns the data dir, the cluster is replaying WAL
      (slow crash recovery), so we wait it out patiently until the shared
      deadline, then re-attach - the existing, deliberate behaviour.
    * If **no live postmaster** is there, the bring-up genuinely failed (a
      missing binary, an antivirus lock, a half-written data dir). We return at
      once so the caller can reset and retry, instead of blocking the whole
      recovery window on a cluster that never started - the old code's opaque
      multi-minute hang on exactly this class of transient failure.
    """
    last_exc: Exception | None = None
    probe = 0
    while time.monotonic() < deadline:
        probe += 1
        try:
            server = pgserver.get_server(str(pgdata))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # The first get_server() launches the postmaster, which keeps
            # recovering in the background even though pg_ctl/the parser raised.
            # Evict the half-built handle pixeltable cached (keyed by resolved
            # pgdata) so the next get_server() re-reads the cluster state.
            if ps_cls is not None:
                try:
                    ps_cls._instances.pop(resolved_pgdata, None)
                except Exception:  # noqa: BLE001
                    pass

            # No live postmaster => not a slow recovery but a hard/transient
            # bring-up failure. Fail this attempt fast so the caller can fully
            # reset (clear leftovers) and retry within the shared window.
            if not _postmaster_recovering(resolved_pgdata):
                return None, last_exc

            remaining = int(deadline - time.monotonic())
            logger.warning(
                "embedded PostgreSQL not ready yet (probe %d, %ds left); crash recovery "
                "may be replaying WAL -- waiting: %r",
                probe,
                max(remaining, 0),
                exc,
            )
            emit_stage(
                "pg",
                "progress",
                f"Recovering the local database, this can take a few minutes ({max(remaining, 0)}s left)",
            )

            # Wait for the postmaster to actually accept connections (recovery
            # complete). When it does, loop straight back into get_server(),
            # which now attaches cleanly. If it never does within the window we
            # return the failure so the caller can decide whether to retry.
            if not _wait_until_connectable(resolved_pgdata, deadline):
                return None, last_exc
            # A short floor between get_server() retries: if the port is already
            # open but get_server() still raised (a brief pidfile race), this
            # keeps the loop from spinning hot while the pidfile finishes.
            time.sleep(1.0)
        else:
            # get_server() returning means we were handed a server object. It
            # does not mean a server is there. Attaching reads the cluster's own
            # files, so a data directory left describing a postmaster that no
            # longer exists hands back a perfectly well formed handle onto a
            # port where nothing is listening, and the caller then announces the
            # database ready and fails to connect to it in the same breath. That
            # pair of statements is what a user actually saw, twice, on two
            # different data directories.
            #
            # So the happy path proves it the same way the recovery path already
            # does, by opening a socket. On a healthy boot the first connect
            # succeeds and this costs nothing measurable; when it does not, the
            # cluster is not there whatever the files say, and saying so here
            # lets the caller's retry clear the leftovers and start one.
            probe_window = min(_READY_PROBE_SECONDS, max(deadline - time.monotonic(), 0.0))
            if _cluster_answers(resolved_pgdata, probe_window):
                return server, None
            port = _port_from_pidfile(resolved_pgdata)
            last_exc = ConnectionError(
                f"the cluster at {resolved_pgdata} was handed back as ready but nothing answered "
                f"on port {port} within {probe_window:.0f}s"
            )
            logger.warning("embedded PostgreSQL attached but did not answer: %s", last_exc)
            # A cluster that accepts and never speaks is a postmaster left alive
            # by a run that died after starting it. Nothing else in this module
            # can clear it: the pidfile names a live process, so the stale-pidfile
            # sweep correctly leaves it alone, and every retry attaches straight
            # back onto it. Stopping it here is what turns this from a clearer
            # error into a machine that starts, which is the difference the user
            # actually experiences.
            _stop_mute_postmaster(resolved_pgdata)
            # Drop the handle pixeltable cached for this data directory, or the
            # next attempt is given the same unusable one straight back.
            if ps_cls is not None:
                try:
                    ps_cls._instances.pop(resolved_pgdata, None)
                except Exception:  # noqa: BLE001
                    pass
            return None, last_exc
    return None, last_exc


def _int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back on parse errors."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _read_pidfile_pid(pgdata: Path) -> int | None:
    """Return the postmaster PID recorded in ``postmaster.pid``, or ``None``."""
    pidfile = pgdata / "postmaster.pid"
    try:
        first = pidfile.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
        return int(first)
    except (OSError, IndexError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    """Best-effort check whether a process with ``pid`` currently exists."""
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        # Without psutil, assume the process may be alive so we never delete a
        # pidfile for a live postmaster.
        return True


def _read_pidfile_start_time(pgdata: Path) -> float | None:
    """Return the postmaster start time recorded in ``postmaster.pid``.

    Line three of the file is the epoch second at which the postmaster started,
    written by PostgreSQL itself. It is what lets us tell the process that wrote
    this file apart from whatever holds that PID now.
    """
    pidfile = pgdata / "postmaster.pid"
    try:
        lines = pidfile.read_text(encoding="utf-8", errors="ignore").splitlines()
        return float(lines[2].strip())
    except (OSError, IndexError, ValueError):
        return None


def _pid_was_recycled(pid: int, recorded_start: float | None) -> bool:
    """True when ``pid`` is alive but is demonstrably not the process that wrote the pidfile.

    Operating systems reuse process identifiers, and Windows reuses them quickly.
    Asking only whether the number is alive therefore answers a different
    question than the one that matters: a pidfile left behind by a force-killed
    postmaster keeps naming a number, and once the system hands that number to
    an unrelated service the file starts describing a process that has nothing
    to do with this cluster. Measured on a real machine: a pidfile written in
    July named a PID held by a licensing service, the check saw a live process,
    kept the file, and the cluster reported itself ready on a port where nothing
    was listening. The backend then refused to start with a connection error,
    and the user was told the database was ready and the server was not.

    Only positive evidence of recycling counts, because the opposite mistake is
    far worse: deleting the pidfile of a genuinely live postmaster invites a
    second one onto the same data directory. Anything unreadable or uncertain
    therefore answers no and the file is kept.
    """
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return False
    try:
        proc = psutil.Process(pid)
        created = proc.create_time()
        name = (proc.name() or "").lower()
    except Exception:  # noqa: BLE001
        # Gone, or we are not allowed to look. Either way this is not evidence.
        return False
    if recorded_start is not None:
        # The recorded time is the stronger signal and answers on its own, so a
        # process whose creation matches it is the one that wrote the file even
        # if we could not make sense of its name.
        return abs(created - recorded_start) > _PID_START_TOLERANCE_SECONDS
    # With no time to compare against, a name we can read that is not a
    # postmaster settles it instead.
    return bool(name) and "postgres" not in name and "postmaster" not in name


def _clear_stale_pidfile(pgdata: Path) -> None:
    """Delete ``postmaster.pid`` when the process it names is gone or is no longer it.

    A force-kill or crash leaves the pidfile behind, and the installer's own
    hooks force-kill the sidecar and its children on every install and every
    uninstall, so this is the ordinary aftermath of upgrading rather than a rare
    accident. PostgreSQL itself refuses to start while a pidfile names a live
    process, and pixeltable takes a slower path for one that names a dead PID,
    so clearing it keeps boot on the clean-start path.

    Never removes a pidfile whose postmaster is still alive. A PID that is alive
    but belongs to something else is treated as gone, because that is what it
    is.
    """
    pidfile = pgdata / "postmaster.pid"
    if not pidfile.exists():
        return
    pid = _read_pidfile_pid(pgdata)
    if pid is None:
        return
    recycled = _pid_was_recycled(pid, _read_pidfile_start_time(pgdata))
    if _pid_alive(pid) and not recycled:
        return
    reason = f"pid {pid} belongs to another process" if recycled else f"dead pid {pid}"
    try:
        pidfile.unlink()
        logger.info("removed stale postmaster.pid (%s) in %s", reason, pgdata)
    except OSError as exc:
        logger.warning("could not remove stale postmaster.pid in %s: %r", pgdata, exc)


def _pg_ctl_path() -> Path | None:
    """The bundled ``pg_ctl``, or ``None`` when it cannot be located.

    Lives in the same ``pginstall/bin`` directory as initdb and the postmaster,
    so it is present wherever they are, including the frozen desktop bundle.
    """
    try:
        from pixeltable_pgserver.utils import POSTGRES_BIN_PATH
    except Exception:  # noqa: BLE001
        return None
    exe = Path(POSTGRES_BIN_PATH) / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
    return exe if exe.is_file() else None


def _owns_the_blocked_port(pid: int, pgdata: Path) -> bool:
    """Whether ``pid`` actually holds the port this cluster's pidfile names.

    The identity question asked causally rather than by reputation. "Is this
    process called postgres" is a guess about a name; "is this the process
    holding the port we cannot use" is the thing that matters, and it is the
    reason we would end it at all.

    Falls back to the process name where the socket table cannot be read: a
    unix-socket cluster has no inet listener to find, and macOS often refuses
    the socket table to a non-root caller. Both readings fail CLOSED, unlike
    :func:`_pid_alive` which fails open. The asymmetry is deliberate - failing
    open there means keeping a pidfile, failing open here means killing a
    process we could not identify.
    """
    port = _port_from_pidfile(pgdata)
    if port is None:
        return False
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return False

    # The system-wide socket table, deliberately, not ``Process.net_connections``.
    # Measured on Windows: the per-process view returns an EMPTY LIST for a
    # process whose handle we do not hold, without raising. That reads as "owns
    # no ports" and is indistinguishable from a true negative, so a check built
    # on it would quietly answer "not the owner" for every cluster on the
    # platform where this defect happens, and hand the whole decision to the
    # name guess below. The system-wide call names the owning pid correctly.
    try:
        for conn in psutil.net_connections(kind="inet"):
            if getattr(conn, "status", None) != psutil.CONN_LISTEN:
                continue
            if getattr(getattr(conn, "laddr", None), "port", None) != port:
                continue
            # Somebody owns this port. If it is our pid the identification is
            # positive; if it is another process then the pidfile is not
            # describing the thing blocking us, and stopping it would be wrong.
            return conn.pid == pid
    except Exception:  # noqa: BLE001
        pass

    # No inet listener found, or the table could not be read. A unix-socket
    # cluster legitimately has no TCP listener, so fall back to asking what the
    # process is. Still fails closed when even that cannot be answered.
    try:
        return "postgres" in psutil.Process(pid).name().lower()
    except Exception:  # noqa: BLE001
        return False


def _stop_mute_postmaster(pgdata: Path) -> bool:
    """Stop a postmaster that holds the port and no longer answers on it.

    This is the recovery half of the mute case, and without it the detection is
    only a better error message. A previous run that died after starting the
    cluster leaves the postmaster alive; the pidfile keeps naming a live process
    so :func:`_clear_stale_pidfile` correctly refuses to touch it, pixeltable
    attaches to it instantly, and every retry attaches to the same unusable
    server. The user is stuck until they reboot, and reinstalling does not help
    because nothing about the installation is wrong. That is the shape of a real
    report: a release crashed after bringing the cluster up, the next release
    fixed the crash, and the machines the first one had already poisoned still
    could not start.

    Only ever called once :func:`_probe_cluster` has answered ``mute``, and it
    re-asks here rather than trusting the caller, because this is the one place
    in the module that ends a process. The three states it must not act on all
    fail that check:

    * A cluster replaying WAL has not opened its listen socket, so it probes
      ``closed`` and is waited out patiently exactly as before.
    * A cluster too busy to take another client answers "sorry, too many clients
      already", which is an answer, so it probes ``answering``.
    * A cluster that is merely slow answers late, and the reply budget is set
      for that.

    Ending a postmaster is the same event as the crash PostgreSQL is designed to
    survive: the next start replays WAL and comes up consistent. A fast shutdown
    is tried first anyway, because it checkpoints and spares the user a recovery
    they would otherwise sit through.
    """
    pid = _read_pidfile_pid(pgdata)
    if pid is None or not _pid_alive(pid):
        return False
    if _probe_cluster(pgdata) != _MUTE:
        return False
    # Operating systems reuse process identifiers, and Windows reuses them
    # quickly. A pidfile left behind by a force-killed postmaster keeps naming a
    # number, and once the system hands that number to an unrelated service the
    # file describes a process that has nothing to do with this cluster. Every
    # other reader in this module already refuses on that evidence; the one that
    # ends a process must refuse on it hardest, because being wrong here does
    # not mean a failed boot, it means killing a stranger.
    if _pid_was_recycled(pid, _read_pidfile_start_time(pgdata)):
        logger.warning("refusing to stop pid %s for %s: it no longer belongs to this cluster", pid, pgdata)
        return False
    if not _owns_the_blocked_port(pid, pgdata):
        logger.warning("refusing to stop pid %s for %s: it does not hold the port this cluster names", pid, pgdata)
        return False

    logger.warning(
        "the postmaster at %s (pid %s) holds its port and does not answer on it; stopping it so a "
        "working cluster can be started in its place",
        pgdata,
        pid,
    )
    emit_stage("pg", "progress", "Clearing a database left behind by an earlier run")

    pg_ctl = _pg_ctl_path()
    if pg_ctl is not None:
        for mode, wait in (("fast", 20), ("immediate", 15)):
            try:
                subprocess.run(  # noqa: S603
                    [str(pg_ctl), "-D", str(pgdata), "-m", mode, "-w", "-t", str(wait), "stop"],
                    capture_output=True,
                    text=True,
                    timeout=wait + 10,
                    check=False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("pg_ctl stop -m %s failed at %s: %r", mode, pgdata, exc)
            if not _pid_alive(pid):
                logger.info("stopped the unresponsive postmaster (pid %s) with pg_ctl -m %s", pid, mode)
                _clear_stale_pidfile(pgdata)
                return True

    # pg_ctl is the right tool and it is bundled, but a postmaster wedged badly
    # enough to stop answering can also be wedged badly enough to ignore it.
    try:
        import psutil

        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not stop the unresponsive postmaster (pid %s) at %s: %r", pid, pgdata, exc)
        return False

    if _pid_alive(pid):
        return False
    logger.info("stopped the unresponsive postmaster (pid %s)", pid)
    _clear_stale_pidfile(pgdata)
    return True


def _postmaster_recovering(pgdata: Path) -> bool:
    """True when a live postmaster owns ``pgdata`` (start or crash recovery in progress).

    ``get_server()`` can raise while PostgreSQL is still replaying WAL: the
    postmaster process is alive and has written its pidfile, but it has not yet
    opened its listen socket, so that case must be waited out patiently. A
    bring-up that never produced a live postmaster (a missing binary, an
    antivirus lock, a half-written data dir) has no live pid here, so the caller
    can fail fast and retry instead of blocking the whole recovery window.

    Conservative by design: with no pidfile the answer is ``False`` (retry), and
    when process liveness cannot be determined (:func:`_pid_alive` has no psutil)
    it stays ``True``, preserving the historical patient-wait behaviour.
    """
    pid = _read_pidfile_pid(pgdata)
    if pid is None:
        return False
    return _pid_alive(pid)


#: Locale overrides forced onto every embedded-PG child process. PostgreSQL's
#: initdb rejects locale *names* that contain non-ASCII characters; the C locale
#: is always ASCII and deterministic, which is exactly what an internal app
#: cluster wants (byte-order collation, no linguistic surprises).
_ASCII_LOCALE_ENV = {
    "LC_ALL": "C",
    "LANG": "C",
    "LC_CTYPE": "C",
    "LC_COLLATE": "C",
    "LC_MESSAGES": "C",
}


def _apply_ascii_locale_env() -> None:
    """Force a C locale for the embedded-PG subprocesses (initdb / postgres).

    Set in this process's environment so every child PG binary inherits it.
    Safe for the Python app itself: its locale was fixed at interpreter start and
    it does all file I/O as explicit UTF-8, so mutating ``os.environ`` now only
    affects the child processes we spawn, not Python's own text handling.
    """
    for key, value in _ASCII_LOCALE_ENV.items():
        os.environ[key] = value


def _initdb_args(pgdata: Path) -> tuple[str, ...]:
    """``initdb`` arguments matching pixeltable-pgserver, plus an explicit C locale.

    Kept identical to ``pixeltable_pgserver.postgres_server`` (auth=trust, utf8
    encoding, superuser ``postgres``) so a cluster we pre-create is exactly what
    pixeltable expects -- it then finds ``PG_VERSION`` and skips its own initdb.
    """
    return (
        "--auth=trust",
        "--auth-local=trust",
        "--encoding=utf8",
        "--locale=C",
        "-U",
        "postgres",
        "-D",
        str(pgdata),
    )


def _postgres_major(version: str) -> str | None:
    """Reduce a PostgreSQL version string to the major that decides file format.

    PostgreSQL changed how it numbers releases at 10. From then on the first
    component alone is the major, so ``16.11``, ``16.2`` and ``16`` are all
    major 16 and share one on-disk format. Before 10 the second component was
    part of the major: ``9.5`` and ``9.6`` are as incompatible with each other
    as 15 is with 16, so both components have to survive here or a 9.5 cluster
    would be reported as a 9.6 one.

    Returns ``None`` when the string carries no leading number, which is what an
    empty, truncated or corrupted ``PG_VERSION`` looks like. That is deliberately
    not treated as a mismatch: we cannot say what wrote the directory, and a
    guard that guesses would block a boot on no evidence.
    """
    parts = version.strip().split(".")
    if not parts or not parts[0].isdigit():
        return None
    if parts[0] == "9" and len(parts) > 1 and parts[1].isdigit():
        return f"9.{parts[1]}"
    return parts[0]


def _major_sort_key(major: str) -> tuple[int, ...]:
    """Order two majors so the message can say which side is the newer one."""
    return tuple(int(part) for part in major.split(".") if part.isdigit())


def _data_dir_major(pgdata: Path) -> str | None:
    """Return the PostgreSQL major that created ``pgdata``, or ``None``.

    Every cluster carries its major in ``PG_VERSION``, written by initdb and
    never updated in place - a major upgrade is a new directory plus pg_upgrade
    or a dump/restore, never an edit of this file. ``None`` covers both "the
    directory is not a cluster yet" (no file, the fresh-install path) and "the
    file is there but says nothing usable".
    """
    try:
        raw = (pgdata / "PG_VERSION").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return _postgres_major(raw)


def _bundled_major() -> str | None:
    """Return the PostgreSQL major the bundled binaries provide, or ``None``.

    ``pg_config --version`` prints one line, ``PostgreSQL 16.11``, and it ships
    in the same ``pginstall/bin`` directory as initdb and the postmaster, so it
    is present wherever they are - including the frozen desktop bundle, whose
    hook collects that whole tree (``desktop/hooks/hook-pixeltable_pgserver.py``).

    Fails open on everything: a missing package, a missing binary, a non-zero
    exit, a timeout, output in a shape we do not recognise. The caller uses this
    only to refuse a boot, and refusing because we could not interrogate our own
    installation would break working machines to guard against a broken one.
    """
    try:
        from pixeltable_pgserver.utils import POSTGRES_BIN_PATH
    except Exception:  # noqa: BLE001
        return None
    exe = Path(POSTGRES_BIN_PATH) / ("pg_config.exe" if os.name == "nt" else "pg_config")
    if not exe.is_file():
        return None
    try:
        completed = subprocess.run(  # noqa: S603
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not read the bundled PostgreSQL version from %s: %r", exe, exc)
        return None
    tokens = completed.stdout.strip().split()
    if not tokens:
        return None
    return _postgres_major(tokens[-1])


class VersionConflict(NamedTuple):
    """A data directory and the bundled binaries disagreeing, with both numbers.

    The prose message is the useful thing for a log or a terminal, but the two
    majors have to survive as values as well: the launcher checklist gets one
    short line per stage, and building that line by re-parsing the paragraph -
    or by re-running ``pg_config`` - would be two ways of asking a question
    already answered here.
    """

    found: str
    expected: str
    message: str


def data_dir_version_conflict(pgdata: Path | str) -> VersionConflict | None:
    """Explain why the cluster on disk cannot be opened by the bundled binaries.

    A PostgreSQL data directory is readable only by the major version that wrote
    it. The postmaster refuses in both directions and it refuses immediately, so
    an application that bumps its bundled PostgreSQL leaves every existing
    installation unable to start - and the raw refusal surfaces here after
    several layers of retry, as "the local database could not be started".

    Only the *presence* of ``PG_VERSION`` was ever read before this function
    existed. That is enough to decide whether initdb still has to run and tells
    nobody anything about compatibility, so the one recovery anybody could name
    was ``init-db --reset``, which deletes the cluster. This says what the two
    versions are while the data is still on disk, and names the recoveries that
    keep it before the one that does not.

    Returns a :class:`VersionConflict` on a mismatch and ``None`` otherwise -
    including when either version cannot be read, which is not evidence of a
    conflict.
    """
    pgdata = Path(pgdata)
    found = _data_dir_major(pgdata)
    if found is None:
        return None
    expected = _bundled_major()
    if expected is None or found == expected:
        return None

    if _major_sort_key(found) > _major_sort_key(expected):
        cause = (
            "Nothing ever downgrades a data directory, so this normally means the application "
            "was downgraded: an older release is running against a directory a newer one has "
            "already opened. Installing that newer release again is the shortest way back."
        )
    else:
        cause = (
            "This normally means the application was upgraded across a PostgreSQL version bump: "
            f"the directory was written by the PostgreSQL {found} the previous release carried, "
            "and nothing migrates it on its own."
        )

    message = (
        f"The local database at {pgdata} was created by PostgreSQL {found}, and this build ships "
        f"PostgreSQL {expected}. PostgreSQL cannot open a data directory written by a different "
        f"major version, so the cluster stays exactly as it is until one of the two sides moves. "
        f"{cause} "
        f"To keep the data: install PostgreSQL {found}, start it on {pgdata}, and point the "
        f"application at it by setting DATABASE_URL - or use that PostgreSQL {found} to run "
        f"pg_dump, then restore the dump into a fresh directory here. Setting DATABASE_URL is "
        f"enough on its own, with one exception: '--embedded-pg' and a truthy OE_USE_EMBEDDED_PG "
        f"both override it and send the application back to this directory, so drop them if you "
        f"are using them. "
        f"'openconstructionerp init-db --reset' also clears the conflict, and it clears it by "
        f"DELETING the cluster at {pgdata}: every project, price, document and user in it is gone "
        f"permanently. Run it only after a dump, or if this installation holds nothing you need."
    )
    return VersionConflict(found=found, expected=expected, message=message)


def _clear_incomplete_cluster(pgdata: Path) -> None:
    """Empty a ``pgdata`` directory that has no ``PG_VERSION`` (a failed initdb).

    A valid PostgreSQL cluster always has a ``PG_VERSION`` file; its absence
    means initdb never finished -- the locale abort on a Turkish Windows box, a
    power loss, or an antivirus lock mid-init all leave debris behind. initdb
    then refuses to run because the target directory "exists but is not empty",
    so a user upgrading from a build that failed this way would keep failing.
    Since a directory without ``PG_VERSION`` is never a usable cluster, clearing
    its contents loses nothing recoverable and lets a fresh initdb proceed.

    Removes the directory's contents, not the directory itself, so any mount
    point or ACLs on ``pgdata`` survive. Best-effort: a file we cannot remove is
    logged, not fatal (the subsequent initdb will surface a clear error).
    """
    if (pgdata / "PG_VERSION").exists():
        return
    try:
        entries = list(pgdata.iterdir())
    except OSError:
        return
    if not entries:
        return
    import shutil

    logger.warning(
        "embedded PostgreSQL data dir %s has no PG_VERSION but holds %d leftover "
        "entries from a failed or interrupted initialisation; clearing them so the "
        "cluster can be re-created cleanly",
        pgdata,
        len(entries),
    )
    for entry in entries:
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
        except OSError as exc:
            logger.warning("could not remove %s while clearing an incomplete cluster: %r", entry, exc)


#: Delimits the settings this module owns inside ``postgresql.conf``, so the
#: block can be rewritten in place instead of appended to on every boot.
_SETTINGS_BEGIN = "# BEGIN OpenConstructionERP settings (managed, do not edit)"
_SETTINGS_END = "# END OpenConstructionERP settings"

#: Lock slots are a shared pool sized ``max_locks_per_transaction`` times
#: ``max_connections``, not a per-transaction allowance. The platform's schema
#: runs to well over a thousand tables and indexes, and creating or reflecting it
#: takes a lock on each one, so several connections doing that at once exhaust
#: the default pool of 64 and PostgreSQL fails the statement with "out of shared
#: memory". The extra slots cost a few megabytes, which is worth paying to keep
#: the cluster usable on a 2 GB box.
_SERVER_SETTINGS = (("max_locks_per_transaction", "512"),)


def _apply_server_settings(pgdata: Path) -> bool:
    """Write the settings the platform's schema needs into ``postgresql.conf``.

    Returns ``True`` when the file was changed. Runs before every start and is
    idempotent: the managed block is replaced rather than appended, so repeated
    boots leave one copy. A cluster that does not exist yet, or a config we
    cannot read or write, is left alone -- the settings are a widening of
    PostgreSQL's defaults, so failing to apply them only returns the cluster to
    the behaviour it had before.
    """
    conf = pgdata / "postgresql.conf"
    try:
        original = conf.read_text(encoding="utf-8")
    except OSError:
        return False

    body = [f"{name} = {value}" for name, value in _SERVER_SETTINGS]
    block = "\n".join([_SETTINGS_BEGIN, *body, _SETTINGS_END])

    start = original.find(_SETTINGS_BEGIN)
    if start == -1:
        updated = original.rstrip("\n") + "\n\n" + block + "\n"
    else:
        end = original.find(_SETTINGS_END, start)
        if end == -1:
            # Truncated block from an interrupted write: replace to end of file.
            updated = original[:start] + block + "\n"
        else:
            updated = original[:start] + block + original[end + len(_SETTINGS_END) :]

    if updated == original:
        return False
    try:
        conf.write_text(updated, encoding="utf-8")
    except OSError as exc:  # noqa: BLE001
        logger.warning("could not apply embedded PostgreSQL settings to %s: %r", conf, exc)
        return False
    logger.info("applied embedded PostgreSQL settings to %s", conf)
    return True


def _pre_initialize_cluster(pgdata: Path) -> bool:
    """Create the PG cluster ourselves, once, before pixeltable starts it.

    Returns ``True`` if this call initialised the cluster, ``False`` if it was
    already initialised or the pre-init failed -- in which case we leave it to
    pixeltable's own path, so we are never worse off than before.

    Two reasons to own this step rather than let ``get_server()`` do it:

    * **Locale, on Windows.** initdb rejects a locale *name* containing non-ASCII
      characters and reads it from the OS regional settings, which env vars do
      not override, so a Turkish box needs an explicit ``--locale=C``.
    * **Settings, everywhere.** ``get_server()`` runs initdb and starts the
      postmaster in one call, leaving no point in between to write
      ``postgresql.conf``. ``max_locks_per_transaction`` is a postmaster-level
      setting, so a config written afterwards would not take effect until the
      *next* boot -- meaning a first run on a fresh machine, which is exactly
      ``make quickstart``, would still hit the lock ceiling this module exists to
      raise. Initialising here means the config is in place before the postmaster
      ever starts.
    """
    if (pgdata / "PG_VERSION").exists():
        return False
    # A previous build (e.g. the released one without this fix) may have aborted
    # initdb partway and left unusable debris; initdb will not run in a non-empty
    # directory, so clear that first. This is what unblocks a user upgrading from
    # a build that was stuck "Recovering the local database" forever.
    _clear_incomplete_cluster(pgdata)
    try:
        from pixeltable_pgserver.pgexec import pgexec
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not import pixeltable pgexec for pre-init: %r", exc)
        return False
    try:
        pgexec("initdb", _initdb_args(pgdata))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pre-initialising embedded PostgreSQL with --locale=C failed; falling back to pixeltable's own initdb: %r",
            exc,
        )
        return False
    logger.info("pre-initialised embedded PostgreSQL cluster (locale=C) at %s", pgdata)
    return True


def _port_from_pidfile(pgdata: Path) -> int | None:
    """Return the port the recovering postmaster is listening on, if known.

    During crash recovery PostgreSQL writes the port line (line 4) early, so we
    can learn the port even before the pidfile is "complete" enough for
    pixeltable's parser. Returns ``None`` if not yet present.

    The port names the TCP port and the unix socket alike: the socket file is
    ``<socket dir>/.s.PGSQL.<port>``, so one number serves both families.
    """
    lines = _pidfile_lines(pgdata)
    if len(lines) < 4:
        return None
    try:
        port = int(lines[3].strip())
    except ValueError:
        return None
    return port if port > 0 else None


def _pidfile_lines(pgdata: Path) -> list[str]:
    """Return the postmaster pidfile as lines, or an empty list if unreadable."""
    try:
        return (pgdata / "postmaster.pid").read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def _unix_socket_path(pgdata: Path) -> Path | None:
    """Return the unix socket this cluster listens on, when it listens on one.

    Line 5 of the pidfile is the first entry of ``unix_socket_directories``. It
    is empty on Windows, where PostgreSQL has no unix sockets, and holds a
    directory on Linux and macOS. The socket inside it is named after the port.
    """
    lines = _pidfile_lines(pgdata)
    if len(lines) < 5:
        return None
    socket_dir = lines[4].strip()
    port = _port_from_pidfile(pgdata)
    if not socket_dir or port is None:
        return None
    return Path(socket_dir) / f".s.PGSQL.{port}"


def _listens_on_tcp(pgdata: Path) -> bool:
    """Whether the pidfile says this cluster accepts TCP at all.

    Line 6 is the first ``listen_addresses`` entry, empty when the postmaster
    was started with none. Absent information is answered ``True``: a probe that
    skips a family it cannot rule out reports a healthy cluster dead, which is
    the failure this whole helper exists to prevent.
    """
    lines = _pidfile_lines(pgdata)
    if len(lines) < 6:
        return True
    return bool(lines[5].strip())


#: What a liveness probe found. The middle answer is the whole reason these
#: three exist rather than a bool.
#:
#: ``closed``    nothing accepted a connection: no postmaster at all, or one
#:               still replaying WAL that has not opened its listen socket yet.
#: ``mute``      the listen socket accepted a connection and then said nothing.
#: ``answering`` the cluster spoke the PostgreSQL protocol back to us.
_CLOSED = "closed"
_MUTE = "mute"
_ANSWERING = "answering"

#: Seconds allowed for the connect itself, and for the server's first protocol
#: byte. The reply gets the longer budget on purpose: a healthy cluster answers
#: a startup packet in milliseconds, but a machine in the middle of an antivirus
#: scan can be slow enough that a tight timeout would convict a working server.
_PROBE_CONNECT_SECONDS = 2
_PROBE_REPLY_SECONDS = 5

#: Protocol version 3.0 as PostgreSQL encodes it in a StartupMessage.
_PG_PROTOCOL_3 = 196608


def _startup_packet() -> bytes:
    """A minimal PostgreSQL v3 StartupMessage.

    The credentials in it do not have to be usable. The probe reads whatever
    comes back and counts a refusal as proof of life, so this only has to be a
    packet a server is willing to answer.
    """
    body = struct.pack("!i", _PG_PROTOCOL_3) + b"user\x00postgres\x00database\x00postgres\x00\x00"
    return struct.pack("!i", len(body) + 4) + body


def _speaks_postgres(sock: socket.socket) -> bool:
    """Whether an already-open socket has a PostgreSQL server still talking on it.

    Sends a StartupMessage and waits for the first response byte. Which byte it
    is does not matter: ``R`` (an authentication request), ``E`` (an error, such
    as "the database system is starting up" or "sorry, too many clients
    already") and anything else all prove a server is there to say so. Only
    silence, EOF or a reset mean the thing behind the socket cannot serve.

    Counting an error as healthy is the deliberate half. This asks whether a
    server is alive, not whether we may log in, and the two failures are not
    equally bad: refusing to boot because a probe could not authenticate would
    break working machines, while trusting a socket that never speaks is what
    shipped.

    A postmaster keeps its listen socket open for as long as the process lives,
    so a bare ``connect`` succeeds against one that can no longer start a
    backend and reports it healthy. That is how a launcher announces the
    database ready and fails to connect to it in the same breath, which is what
    a user saw on a released build: the ready stage passed and every asyncpg
    connect after it died with a reset mid-handshake.
    """
    try:
        sock.settimeout(_PROBE_REPLY_SECONDS)
        sock.sendall(_startup_packet())
        first = sock.recv(1)
    except OSError:
        return False
    if not first:
        return False
    try:
        # Leave the way a client should, so a probe does not litter the server
        # log with an incomplete-startup-packet warning on every attempt.
        sock.sendall(b"X\x00\x00\x00\x04")
    except OSError:
        pass
    return True


def _probe_cluster(pgdata: Path) -> str:
    """How this cluster answers right now: ``closed``, ``mute`` or ``answering``.

    The unix socket is tried first where the cluster has one. That order is not
    a preference, it is the only reading that cannot be answered by a stranger:
    a system PostgreSQL on 5432 would accept a TCP connect and satisfy a probe
    asking about a cluster in a temporary directory it has never heard of. The
    socket path comes out of this cluster's own pidfile and belongs to it alone.

    TCP is tried when the pidfile reports a listen address, or when it is too
    short to say. Windows clusters answer here; on Linux and macOS the
    postmaster pixeltable-pgserver starts has no TCP listener at all, and asking
    it for one is how a healthy cluster gets reported dead.

    ``mute`` is reported only when something did accept a connection, so the
    distinction survives a cluster that offers two families and answers on
    neither: an open socket anywhere outranks a closed one everywhere.
    """
    saw_open_socket = False

    sock_path = _unix_socket_path(pgdata)
    if sock_path is not None and hasattr(socket, "AF_UNIX"):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(_PROBE_CONNECT_SECONDS)
                s.connect(str(sock_path))
                saw_open_socket = True
                if _speaks_postgres(s):
                    return _ANSWERING
        except OSError:
            pass

    if _listens_on_tcp(pgdata):
        port = _port_from_pidfile(pgdata)
        if port is not None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=_PROBE_CONNECT_SECONDS) as s:
                    saw_open_socket = True
                    if _speaks_postgres(s):
                        return _ANSWERING
            except OSError:
                pass

    return _MUTE if saw_open_socket else _CLOSED


def _accepts_a_connection(pgdata: Path) -> bool:
    """One attempt to reach this cluster, answered only by the cluster itself.

    Kept as the yes/no reading the waiting loops want. It is true only for
    ``answering``: an open socket with nothing behind it is not a database, and
    treating it as one is the defect this module carried into a release.
    """
    return _probe_cluster(pgdata) == _ANSWERING


def _cluster_answers(pgdata: Path, timeout_seconds: float) -> bool:
    """True when this cluster accepts a connection, on any family it offers.

    Separate from :func:`_wait_until_connectable`, which exists to sit out a
    multi minute crash recovery and deliberately pauses after it succeeds so the
    following attach finds a finished pidfile. This one asks a much smaller
    question, whether a cluster we have just been told is ready is actually
    there, so it answers the moment the socket opens and costs a healthy boot
    nothing. Always tries at least once, however small the window.
    """
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while True:
        if _accepts_a_connection(pgdata):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _wait_until_connectable(pgdata: Path, deadline: float) -> bool:
    """Block until the embedded postmaster accepts connections, or deadline.

    Connects with a raw socket, which succeeds as soon as recovery finishes and
    the postmaster opens its listen socket. This is far more robust than parsing
    the pidfile, which is incomplete while recovery runs. Returns ``True`` if it
    became connectable before ``deadline``, else ``False``.

    Shares :func:`_accepts_a_connection` with the ready-stage probe rather than
    repeating the connect, because the address family a cluster listens on is a
    property of the cluster and not of the reason we are asking.
    """
    while time.monotonic() < deadline:
        if _accepts_a_connection(pgdata):
            # Give PostgreSQL a breath after the socket opens so the very next
            # get_server() attach finds status == 'ready'.
            time.sleep(1.0)
            return True
        time.sleep(2.0)
    return False


def _launcher_log_path() -> Path:
    """Best-effort path to the desktop launcher log the STAGE markers land in.

    The Tauri desktop shell pumps this process's stdout (where :func:`emit_stage`
    writes) into ``~/.openestimate/desktop-launcher.log``. Naming it in the fatal
    log line points a stuck user straight at the file that holds the real cause.
    """
    return Path.home() / ".openestimate" / "desktop-launcher.log"


def _pg_failure_detail(pgdata: Path, last_exc: Exception | None) -> str:
    """Build a short human-readable reason for an embedded-PG boot failure.

    Carries the REAL underlying error (exception type and its message, not just
    the class name) plus the tail of the PostgreSQL log, so the ``STAGE:pg:fail``
    marker the launcher shows names an actionable cause instead of an opaque one.
    """
    detail = "Could not start the local database"
    if last_exc is not None:
        message = str(last_exc).replace("\n", " ").replace("\r", " ").strip()
        if message and message != type(last_exc).__name__:
            detail += f": {type(last_exc).__name__}: {message[:200]}"
        else:
            detail += f": {type(last_exc).__name__}"
    log = pgdata / "log"
    try:
        if log.exists():
            tail = log.read_text(encoding="utf-8", errors="ignore").splitlines()[-3:]
            joined = " ".join(line.strip() for line in tail if line.strip())
            if joined:
                detail += f" (postgres log: {joined})"
    except OSError:
        pass
    return detail


def auto_migrate_legacy_sqlite(data_dir: Path | str) -> str:
    """One-time transparent SQLite -> embedded-PostgreSQL data migration.

    Runs only when ALL hold: embedded PG is running, a legacy
    ``<data_dir>/openestimate.db`` exists with content, the target is PostgreSQL,
    and the embedded cluster has no app rows yet (so an already-populated PG is
    never clobbered). On success the SQLite file is renamed to
    ``openestimate.db.migrated`` (with a numeric suffix if needed) so it never
    re-runs. Never raises -- returns a human-readable status string for the
    caller to log/print. A no-op (and safe) when the preconditions don't hold.
    """
    if _server is None:
        return "skip: embedded PostgreSQL not running"

    sqlite_file = Path(data_dir).expanduser() / "openestimate.db"
    try:
        if not sqlite_file.exists() or sqlite_file.stat().st_size == 0:
            return "skip: no legacy SQLite database to migrate"
    except OSError as exc:
        return f"skip: cannot stat {sqlite_file}: {exc!r}"

    sync_url = os.environ.get("DATABASE_SYNC_URL", "")
    if "postgresql" not in sync_url:
        return "skip: target is not PostgreSQL"

    try:
        from sqlalchemy import create_engine

        from app.scripts import migrate_sqlite_to_postgres as migrator
    except Exception as exc:  # noqa: BLE001
        logger.error("auto-migration unavailable: %r", exc)
        return f"error: migration module import failed: {exc!r}"

    dst = None
    src = None
    try:
        base = migrator._load_metadata()
        dst = create_engine(sync_url)
        base.metadata.create_all(dst)

        existing = migrator._target_has_rows(dst, base)
        if existing:
            return f"skip: embedded PostgreSQL already has data (e.g. '{existing}')"

        src = migrator._make_source_engine(f"sqlite:///{sqlite_file.as_posix()}")
        skipped = migrator._copy_all(src, dst, base, 1000)
        migrator._reset_sequences(dst, base)
    except Exception as exc:  # noqa: BLE001
        logger.exception("SQLite -> PostgreSQL auto-migration failed")
        return f"error: {exc!r}"
    finally:
        for eng in (src, dst):
            if eng is not None:
                try:
                    eng.dispose()
                except Exception:  # noqa: BLE001
                    pass

    # Rename the source so a later boot does not migrate again.
    backup = sqlite_file.with_name(sqlite_file.name + ".migrated")
    counter = 0
    while backup.exists():
        counter += 1
        backup = sqlite_file.with_name(f"{sqlite_file.name}.migrated.{counter}")
    try:
        sqlite_file.rename(backup)
        kept = backup.name
    except OSError:
        logger.warning("migrated but could not rename %s", sqlite_file)
        kept = sqlite_file.name + " (rename failed)"

    msg = f"migrated SQLite -> embedded PostgreSQL (skipped {skipped} unconvertible rows); legacy db kept as {kept}"
    logger.info(msg)
    return msg


def retain() -> None:
    """Pin the cluster so an application shutdown in this process leaves it running.

    The application stops the embedded cluster from its own shutdown handler,
    which is right when the application booted it. It is wrong when something
    longer-lived did: the test session boots one cluster for the whole run, and
    without this pin the first test that exercises the application's shutdown
    takes the database down for every test after it.

    The owner keeps the cluster and stops it with ``shutdown(force=True)``.
    """
    global _retained
    _retained = True


def shutdown(*, force: bool = False) -> None:
    """Stop the embedded cluster if this process booted one (safe to always call).

    A cluster pinned by :func:`retain` is left alone unless ``force`` is passed,
    which only its owner should do.
    """
    global _server, _retained
    if _server is None:
        return
    if _retained and not force:
        logger.debug("embedded PostgreSQL is retained by its owner, leaving it running")
        return
    _retained = False
    try:
        _server.cleanup()
        # Routine stop: keep it at debug so a shutdown that happens BECAUSE
        # startup failed cannot add log noise on top of the real cause. Genuine
        # cleanup errors below still log with a traceback.
        logger.debug("embedded PostgreSQL stopped")
    except Exception:  # noqa: BLE001
        logger.debug("embedded PostgreSQL cleanup failed", exc_info=True)
    finally:
        _server = None
