# Desktop bootstrap plan (Hermes-style self-verifying launcher)

Status: investigation complete, first launcher fixes landed in `desktop/src-tauri/src/main.rs`.
Owner: desktop. Target: v7.0.0 for the visible bootstrap UI, with the attach-first
and open-log fixes already in the tree.

## 1. What actually went wrong on the founder machine

Forensic findings from the live machine (2026-06-06):

- The installed app is **v6.7.0** (`C:\Program Files\OpenConstructionERP`,
  `OpenConstructionERP.exe` + `openestimate-server.exe`, both stamped 6.7.0 in the
  exe version resource and in the HKLM Uninstall key). The newer installers
  (v6.8.1, v6.8.2, v6.9.0, v6.10.0) were never installed over it.
- v6.7.0 is the tag immediately **before** the frozen-build launch fix. That fix
  shipped in commit `baf6a2c93` ("fix(desktop): resolve silent launch failure on
  frozen builds; v6.8.1"). A check of the v6.7.0 source tree confirms the
  asyncpg-SSL-on-loopback workaround in `backend/app/database.py` is **absent**
  from v6.7.0.
- Reproduced directly. Running the installed v6.7.0 `openestimate-server.exe serve`
  against an isolated data dir:
  - the embedded PostgreSQL cluster **started successfully** (postmaster came up,
    pidfile `status = ready`, PG log: "database system is ready to accept
    connections");
  - the backend process then ran for 100+ seconds burning CPU but **never bound
    its HTTP port** (`/api/health` "Unable to connect"), and produced **0 bytes**
    of captured stdout/stderr.
  - This is exactly the v6.8.1 failure signature: the cluster is healthy, but the
    first asyncpg connection (migrations / `create_all`) blows up while eagerly
    building an `ssl.SSLContext` on the frozen build's broken bundled OpenSSL
    (asyncpg default sslmode `prefer`). The HTTP server never starts, so the
    Tauri shell waits out its boot window and the user sees "nothing happens".
- Positive control: the **current source** backend (v6.10.0, which has the SSL
  loopback fix) run the same way came up **healthy (HTTP 200, `database: ok`)** in
  ~159s on the same machine. So the fix is real and sufficient for this failure.

There is **no** `~/.openestimate/desktop-launcher.log` on the machine, which is
itself consistent with a v6.7.0 install: the no-silent-fail launcher that writes
that log was added in v6.8.1, so the installed shell never wrote one.

### Root-cause verdict

The installed desktop build is **v6.7.0**, which predates the asyncpg-SSL-on-
loopback fix. In a frozen (PyInstaller) build the very first database connection
raises `ssl.SSLError` on the bundled OpenSSL, so the backend never finishes
starting and the window never advances past the splash. **Installing v6.10.0 (or
any v6.8.1+) over it fixes the specific crash.** The fix is already in the
shipped product; the founder is simply running an old install.

### Second, latent hazard found on this machine (cluster/port sharing)

This is a real developer-machine scenario worth hardening against, because the
founder's box runs both dev tools and the desktop app out of the same
`~/.openestimate`:

- A dev backend (`python -m app.cli serve --port 8000`) was running and already
  owned the embedded cluster at `~/.openestimate/pgdata` (postmaster live on a
  high port; `postmaster.pid status = ready`).
- The desktop app, on the default `--data-dir`, would call
  `pixeltable_pgserver.get_server(~/.openestimate/pgdata)`. Cross-process,
  pgserver **attaches** to the already-running postmaster (it reads the pidfile,
  sees it running, and reuses it) - so the desktop and the dev backend would
  share one cluster.
- The danger is on exit: the backend's shutdown calls
  `embedded_pg.shutdown() -> srv.cleanup() -> pixeltable _cleanup()`, which
  decrements the shared `.handle_pids.json` and, if it believes it holds the last
  handle, runs `pg_ctl stop` - which can stop the postmaster out from under the
  still-running dev backend. (Today this is masked only because
  `.handle_pids.json` is polluted with ~38 stale PIDs from force-killed sessions,
  which accidentally keeps the count above one. That is luck, not design.)

## 2. What was fixed now (already in the tree, compiles)

All changes are in `desktop/src-tauri/src/main.rs` and verified with
`cargo check` (clean, zero warnings, cargo 1.93.1):

1. **Attach to an existing healthy backend instead of booting a second one.**
   Before spawning the sidecar, `setup()` now probes a small set of likely ports
   (`8000, 8080, 8732, 8765`) for a server that self-identifies as ours (its
   `/api/health` body carries `"version"` plus `"modules_loaded"`/`"alembic"`). If
   one is found, the launcher navigates the webview straight to it and does **not**
   spawn a second backend - eliminating the shared-cluster shutdown hazard above
   and making a warm start instant. The probe is run to completion (short, bounded)
   so the spawn decision is made before any sidecar starts (no race).
2. **One-click "Open log" command.** Added a `open_log_file` Tauri command
   (registered via `invoke_handler`) that opens `~/.openestimate/desktop-launcher.log`
   with the OS default handler (`cmd /c start` / `open` / `xdg-open`, no new
   dependency, not the deprecated shell-plugin `open`). The splash failure UI can
   call it via `window.__TAURI__` (`withGlobalTauri` is already on). See the
   one-line splash wiring noted in section 4.

The existing launcher (v6.8.1+) already does the rest of the no-silent-fail
contract well and is kept: it writes `desktop-launcher.log` from the first
instruction, never panics in `setup()`, drives a visible boot checklist from the
backend's `STAGE:<id>:<status>:<detail>` markers, surfaces a backend crash with
the tail of its stderr, picks a free HTTP port, and waits up to 600s for health.
The embedded-PG layer (`backend/app/core/embedded_pg.py`) already handles slow
WAL-replay recovery, stale-pidfile cleanup with PID-liveness check, and a
connect-probe retry loop.

## 3. The Hermes-style bootstrap (full design)

Goal: first run (and every run) verifies the runtime step by step, shows visible
progress, self-repairs what is safe, and never exits silently. Most of the
verification belongs in the backend sidecar (it owns Python, the wheels, and the
cluster); the Tauri shell owns the visible UI and the attach/port decisions.

### 3.1 Environment verification checklist (sidecar, emitted as STAGE markers)

Run in order, each emitting `STAGE:<id>:start|progress|done|fail:<detail>` so the
splash checklist lights up live:

1. `python` - bundled interpreter present and importable. In a frozen build this
   is implicit (we are running inside it); emit `done` immediately. From a pip
   install, check `sys.version_info >= (3, 12)`.
2. `wheels` - import the critical wheels and report the first missing one by name:
   `fastapi`, `sqlalchemy`, `asyncpg`, `psycopg2`, `uvicorn`, `pixeltable_pgserver`.
   A clear "component X is missing, please reinstall" beats a deep ImportError
   traceback. (New step; today these are bundled by the PyInstaller spec but never
   verified at runtime.)
3. `pg` - embedded cluster health:
   - if `pgdata/PG_VERSION` is absent -> `initdb` (first run, a few seconds);
   - if a postmaster is already running on this `pgdata` -> **re-use it** (attach),
     do not start a second one;
   - if the last shutdown was unclean -> allow slow WAL-replay recovery (already
     implemented: 600s window, connect-probe instead of fragile pidfile parsing);
   - stale `postmaster.pid` whose PID is dead -> remove it (already implemented).
4. `migrate` - schema bring-up (`create_all` + alembic). On a fresh cluster also
   the one-time transparent SQLite -> PostgreSQL migration (already implemented).
5. `server` - uvicorn binds the chosen port; emit `done` once the socket is up.
6. `open` - shell navigates the webview to the app.

### 3.2 Port and instance selection (shell)

- **Attach first** (landed): if a healthy OpenConstructionERP backend is already
  listening on a known port, attach instead of booting a second one.
- Otherwise pick a free HTTP port (`portpicker`, already done) and spawn the
  sidecar. The embedded-PG port is chosen by pixeltable itself and never fixed, so
  the DB never collides.

### 3.3 Visible progress UI (shell + splash)

Already present and good: animated checklist with per-step done/active/failed
icons, a status line, a hint, the log path, and a "Copy details" button. The
launcher drives it from STAGE markers and from its own steps. Add the "Open log"
button (command landed; wiring in 4).

### 3.4 Self-repair actions (safe only)

- **Stale postmaster.pid**: remove when the named PID is dead (done). Never remove
  one whose process is alive.
- **Slow crash recovery**: wait it out rather than killing PG mid-replay (done).
  Explicitly do **not** run `pg_resetwal` automatically - it can lose committed
  data; only ever offer it as a manual, clearly-warned last resort.
- **Corrupted bundled runtime**: in a PyInstaller onefile build there is no venv
  to re-extract at runtime; the honest repair is "reinstall". A future onedir/
  embeddable-Python layout could re-extract a corrupted `_internal/`; not now.
- **`.handle_pids.json` hygiene**: when attaching to (or booting) the cluster,
  prune dead PIDs from the handle list so a future last-handle cleanup is correct
  and the shared-cluster shutdown hazard cannot bite. (Backend change, see 5.)

### 3.5 Never a silent exit (already the contract)

Every fallible step is handled; the window stays open; failures show a
human-readable message plus the log path; the log is always written. Keep this.

## 4. Splash wiring for "Open log" (frontend, out of this scope to edit)

`frontend/public/splash.html` (and its build copy) need a small button + handler.
The Tauri command is already registered. Suggested 3-line wiring inside the
existing `setError()` / button block:

```js
// when invoking is available (withGlobalTauri), wire an "Open log" button:
var openBtn = document.getElementById('openlogbtn');
if (openBtn && window.__TAURI__ && window.__TAURI__.core) {
  openBtn.addEventListener('click', function () {
    window.__TAURI__.core.invoke('open_log_file').catch(function () {});
  });
  // reveal it in setError() alongside the existing "Copy details" button
}
```

## 5. What ships in v7.0.0 vs later

**v7.0.0 (now / next build):**
- Attach-to-existing-backend and the `open_log_file` command (landed in
  `main.rs`, compiles clean).
- The splash "Open log" button wiring (frontend, 3 lines).
- Re-cut the installers from current `main` so users finally get the SSL fix and
  the visible boot checklist. This alone resolves the founder's crash.
- Add the `wheels` verification STAGE step in the sidecar bootstrap and prune dead
  PIDs from `.handle_pids.json` on attach/boot (backend, small, low risk).

**Later:**
- Onedir/embeddable-Python layout enabling true re-extract self-repair of a
  corrupted runtime.
- A guided, clearly-warned manual recovery path for a genuinely corrupt cluster
  (export-what-you-can, then reinitialize), never automatic `pg_resetwal`.
- An in-app "check for updates / you are N versions behind" nudge so an old
  install like v6.7.0 cannot silently linger past a fix.

## 6. Repro / verification steps

Reproduce the founder failure (old install):
1. Note the installed version (HKLM Uninstall `OpenConstructionERP` shows 6.7.0).
2. Run the installed sidecar against a scratch dir:
   `& "C:\Program Files\OpenConstructionERP\openestimate-server.exe" serve --host 127.0.0.1 --port 8765 --data-dir <tmp>`
   The cluster comes up (pgdata/log shows "ready") but `/api/health` on 8765 never
   answers and the process never binds the port -> the silent failure.

Verify the fix (current source has it):
1. From `backend/`: `python -m app.cli serve --host 127.0.0.1 --port 8767 --data-dir <tmp>`
   (embedded PG default). `/api/health` returns 200 with `"database":"ok"`.
2. Confirms the v6.8.1 SSL loopback fix in `backend/app/database.py` resolves the
   exact crash; the right action for the founder is to install v6.10.0 over the old
   v6.7.0.

Verify the new launcher behavior:
1. `cargo check` in `desktop/src-tauri` (done: clean).
2. Build the desktop app, start a backend on 8000 first, then launch the desktop
   app: it should detect the running backend and attach to it (launcher log:
   "found an existing OpenConstructionERP backend on port 8000; attaching") rather
   than spawn a second sidecar.
3. Force a failure (e.g. point at a busy/locked data dir), confirm the splash shows
   a red failed step and the "Open log" button opens the launcher log.
