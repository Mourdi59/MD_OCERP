"""The public demo is genuinely read-only, and only when it is switched on.

The claim under test is not "the guard answers 403". It is "with the flag on,
nothing in the database moves", which is a different and much stronger claim,
so the evidence is a row census of every table in the schema taken before and
after the write attempts rather than the status codes the API returned.

Three phases, all in one run, on one application instance:

* Phase A, flag ON  - every non-safe method on every mounted route is refused
  with the exact contract, and the census is unchanged afterwards.
* Phase B, flag OFF - the same writes all succeed and the census grows. Without
  this control, phase A would also pass against a harness that never manages to
  write anything, and a guard that is on for everybody would look correct.
* Phase C, flag ON  - reads still work, including the ones that post a body,
  and a visitor can still sign in.

The flag is flipped between phases on a single app built once, which is also
the point: it proves the value is read per request rather than baked in at
construction, so nobody can later flip the default and have this suite stay
green.

Run: pytest tests/integration/test_demo_read_only.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi import WebSocket
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import get_settings
from app.core.demo_read_only import (
    _ALWAYS_WRITABLE,
    _AUTHENTICATION_WRITABLE,
    ALLOWED_ENDPOINTS,
    DEMO_READ_ONLY_ERROR,
    SAFE_METHODS,
    DemoReadOnlyError,
    WriteScope,
    demo_read_only_guard,
    endpoint_key,
)
from app.database import async_session_factory
from app.main import create_app

#: Tables the guard deliberately lets a permitted request write. Taken from the
#: module rather than restated here: a second copy of the decision would let
#: someone widen the exemption without this test noticing. They are the trace
#: of a visit rather than demo content, and they are reported separately below
#: instead of being quietly dropped from the comparison.
EXEMPT_TABLES = set(_ALWAYS_WRITABLE) | set(_AUTHENTICATION_WRITABLE)

#: A stand-in for every path parameter. The guard refuses before validation, so
#: the value only has to be well-formed enough not to 404 on the router.
_ANY_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _leave_the_flag_off_afterwards():
    """No test in this file may leave a read-only deployment behind it.

    ``get_settings`` is an ``lru_cache``, so restoring the environment is not
    enough on its own: the cached Settings object built while the flag was on
    would still be handed to whatever runs next. Clear it explicitly rather
    than relying on the order fixture finalizers happen to run in.
    """
    yield
    import os

    os.environ.pop("OE_DEMO_READ_ONLY", None)
    get_settings.cache_clear()
    assert get_settings().demo_read_only is False


def _set_flag(monkeypatch: pytest.MonkeyPatch, *, on: bool) -> None:
    """Flip the read-only demo flag for subsequent requests."""
    monkeypatch.setenv("OE_DEMO_READ_ONLY", "true" if on else "false")
    get_settings.cache_clear()
    assert get_settings().demo_read_only is on


async def _census() -> dict[str, tuple[int, str]]:
    """Row count *and* a content digest for every table in the public schema.

    Generated from the catalog, not from a hand-picked list: a guard that
    refuses the endpoints someone thought of while a different one writes is
    the failure mode this test exists to catch, and a hand-written table list
    would share the same blind spot as the hand-written endpoint list.

    The digest is here because a row count alone is blind to the write that
    matters most on a demo: an UPDATE. Editing every project's name leaves
    every count identical. Hashing the ordered text of each row catches it.

    ``row::text`` renders timestamps through ``DateStyle`` and ``TimeZone`` and
    floats through ``extra_float_digits``, all of them per-session settings.
    Two snapshots taken on different pooled connections could therefore differ
    with nothing written at all, which would read as a guard failure. Pinning
    the three of them makes the digest a function of the data alone.
    """
    async with async_session_factory() as session:
        await session.execute(text("SET LOCAL TimeZone = 'UTC'"))
        await session.execute(text("SET LOCAL DateStyle = 'ISO, YMD'"))
        await session.execute(text("SET LOCAL extra_float_digits = 0"))
        names = [
            row[0]
            for row in (
                await session.execute(
                    text(
                        "SELECT c.relname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE c.relkind = 'r' AND n.nspname = 'public' "
                        "ORDER BY c.relname"
                    )
                )
            ).all()
        ]
        if not names:
            return {}
        union = " UNION ALL ".join(
            f"SELECT '{n}' AS t, count(*) AS c, "
            f"coalesce(md5(string_agg(x::text, '|' ORDER BY x::text)), '-') AS d "
            f'FROM "{n}" x'
            for n in names
        )
        rows = (await session.execute(text(union))).all()
    return {row[0]: (int(row[1]), str(row[2])) for row in rows}


def _diff(
    before: dict[str, tuple[int, str]], after: dict[str, tuple[int, str]]
) -> dict[str, tuple[tuple[int, str], tuple[int, str]]]:
    """Tables whose contents changed, as ``{table: (before, after)}``."""
    moved: dict[str, tuple[tuple[int, str], tuple[int, str]]] = {}
    for table in sorted(set(before) | set(after)):
        was, now = before.get(table, (0, "-")), after.get(table, (0, "-"))
        if was != now:
            moved[table] = (was, now)
    return moved


def _rows(census: dict[str, tuple[int, str]]) -> int:
    """Total rows across the whole schema."""
    return sum(count for count, _digest in census.values())


def _assert_contract(response: Any, where: str) -> None:
    """The refusal is exactly the shape the screen was built against."""
    assert response.status_code == 403, f"{where}: expected 403, got {response.status_code} {response.text[:200]}"
    body = response.json()
    assert set(body) == {"detail"}, f"{where}: unexpected top-level keys {sorted(body)}"
    detail = body["detail"]
    assert isinstance(detail, dict), f"{where}: detail is {type(detail).__name__}, not an object"
    assert set(detail) == {"error", "message"}, f"{where}: unexpected detail keys {sorted(detail)}"
    assert detail["error"] == DEMO_READ_ONLY_ERROR
    assert isinstance(detail["message"], str) and detail["message"].strip()


#: The curated writes. Each one has to succeed with the flag off, which is what
#: makes its refusal with the flag on mean something.
def _writes(marker: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    return [
        (
            "POST",
            "/api/v1/projects/",
            {"name": f"Demo guard {marker}", "currency": "EUR", "region": "DACH"},
        ),
        (
            "POST",
            "/api/v1/costs/",
            {
                "code": f"DGC-{marker}",
                "description": f"Demo guard item {marker}",
                "unit": "m3",
                "rate": "123.45",
                "currency": "EUR",
            },
        ),
        (
            "POST",
            "/api/v1/users/auth/register",
            {
                "email": f"guard-{marker}@demo-guard.io",
                "password": f"GuardPass{marker}9!",
                "full_name": "Guard Probe",
            },
        ),
        ("PATCH", "/api/v1/users/me/", {"full_name": f"Renamed {marker}"}),
        ("PUT", "/api/v1/users/me/sidebar-preferences/", {"hidden_modules": [f"/{marker}"]}),
        ("POST", "/api/v1/users/me/api-keys/", {"name": f"guard-{marker}"}),
    ]


@pytest_asyncio.fixture(scope="module")
async def app_client():
    """One application, one lifespan, for every phase below."""
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as ac:
            yield app, ac


@pytest_asyncio.fixture(scope="module")
async def auth_headers(app_client):
    """Register, promote and sign in while the flag is still off."""
    from sqlalchemy import update as sa_update

    from app.modules.users.models import User

    _app, client = app_client
    get_settings.cache_clear()
    unique = uuid.uuid4().hex[:8]
    email = f"dro-{unique}@demo-guard.io"
    password = f"DroPass{unique}9!"

    registered = await client.post(
        "/api/v1/users/auth/register",
        json={"email": email, "password": password, "full_name": "Read-only Probe"},
    )
    assert registered.status_code == 201, registered.text

    async with async_session_factory() as session:
        await session.execute(sa_update(User).where(User.email == email.lower()).values(role="admin", is_active=True))
        await session.commit()

    signed_in = await client.post("/api/v1/users/auth/login", json={"email": email, "password": password})
    assert signed_in.status_code == 200, signed_in.text
    return {
        "headers": {"Authorization": f"Bearer {signed_in.json()['access_token']}"},
        "email": email,
        "password": password,
    }


def _mutating_routes(app) -> list[tuple[str, str, str, bool]]:
    """Every mounted (method, path) that is not a safe method.

    Returns ``(method, template, concrete_path, allowlisted)``. Built from the
    live route table so nothing can be missed by being spelled differently in
    a test than it is in the router.
    """
    out: list[tuple[str, str, str, bool]] = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        endpoint = getattr(route, "endpoint", None)
        template = getattr(route, "path", None)
        if not methods or not template:
            continue
        allowlisted = endpoint_key(endpoint) in ALLOWED_ENDPOINTS
        concrete = template
        while "{" in concrete:
            head, _, rest = concrete.partition("{")
            _param, _, tail = rest.partition("}")
            concrete = f"{head}{_ANY_ID}{tail}"
        for method in sorted(methods):
            if method in SAFE_METHODS:
                continue
            out.append((method, template, concrete, allowlisted))
    return out


@pytest.mark.asyncio
@pytest.mark.integration
async def test_demo_read_only_refuses_every_write_and_moves_no_rows(app_client, auth_headers, monkeypatch):
    """Phase A: the whole mutating surface is refused, and the database is still."""
    app, client = app_client
    headers = auth_headers["headers"]
    routes = _mutating_routes(app)
    assert len(routes) > 1000, f"route sweep collapsed to {len(routes)} entries - the census is wrong"

    _set_flag(monkeypatch, on=True)
    before = await _census()
    assert before, "row census came back empty - the harness is measuring nothing"

    # 1. The curated writes, which phase B proves really do write.
    for method, path, payload in _writes("phase-a"):
        response = await client.request(method, path, headers=headers, json=payload)
        _assert_contract(response, f"{method} {path}")

    # 2. The whole surface, so this cannot be "the endpoints I thought of".
    unexpected: list[str] = []
    swept = 0
    for method, template, concrete, allowlisted in routes:
        if allowlisted:
            continue
        response = await client.request(method, concrete, headers=headers, json={})
        swept += 1
        if response.status_code != 403 or response.json().get("detail", {}).get("error") != DEMO_READ_ONLY_ERROR:
            unexpected.append(f"{method} {template} -> {response.status_code}")

    after = await _census()
    moved = _diff(before, after)
    non_exempt = {t: v for t, v in moved.items() if t not in EXEMPT_TABLES}
    exempt_moved = {t: v for t, v in moved.items() if t in EXEMPT_TABLES}

    print(f"\n[phase A] flag ON, mutating routes swept: {swept} (allowlisted skipped: {len(routes) - swept})")
    print(f"[phase A] tables counted: {len(before)}; total rows before: {_rows(before)}, after: {_rows(after)}")
    print(f"[phase A] declared-exempt tables that moved: {exempt_moved or 'none'}")
    print(f"[phase A] every other table that moved: {non_exempt or 'none'}")

    assert not unexpected, f"{len(unexpected)} routes did not answer the contract: {unexpected[:20]}"
    assert not non_exempt, f"the database moved while the demo was read-only: {non_exempt}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_writes_still_work_with_the_flag_off(app_client, auth_headers, monkeypatch):
    """Phase B, the negative control: off means off, for everybody."""
    _app, client = app_client
    headers = auth_headers["headers"]

    _set_flag(monkeypatch, on=False)
    before = await _census()

    statuses: list[str] = []
    for method, path, payload in _writes(uuid.uuid4().hex[:6]):
        response = await client.request(method, path, headers=headers, json=payload)
        statuses.append(f"{method} {path} -> {response.status_code}")
        assert 200 <= response.status_code < 300, f"{method} {path} failed with the flag OFF: {response.text[:300]}"

    after = await _census()
    moved = _diff(before, after)
    non_exempt = {t: v for t, v in moved.items() if t not in EXEMPT_TABLES}

    print("\n[phase B] flag OFF, writes attempted:")
    for line in statuses:
        print(f"           {line}")
    print(f"[phase B] total rows before: {_rows(before)}, after: {_rows(after)}")
    print(f"[phase B] tables that moved: {moved}")

    assert non_exempt, (
        "the flag-off control moved nothing outside the exempt tables, so the "
        "flag-on result proves nothing: the harness is not writing"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reads_and_sign_in_still_work_with_the_flag_on(app_client, auth_headers, monkeypatch):
    """Phase C: the whole point is that a visitor sees everything."""
    _app, client = app_client
    headers = auth_headers["headers"]

    # Sign-in throttles its own ``last_login_at`` UPDATE to once a minute, so a
    # login that follows another one closely never issues it - and the write
    # carve-out that makes sign-in possible would go untested. Age the row so
    # the UPDATE really fires. Done here, with no request in scope and the flag
    # still off, which is the state the seeders and migrations run in.
    from sqlalchemy import update as sa_update

    from app.modules.users.models import User

    async with async_session_factory() as session:
        await session.execute(
            sa_update(User).where(User.email == auth_headers["email"].lower()).values(last_login_at=None)
        )
        await session.commit()

    _set_flag(monkeypatch, on=True)
    before = await _census()

    reads = [
        ("GET", "/api/health", None),
        ("GET", "/api/system/status", None),
        ("GET", "/api/v1/projects/", None),
        ("GET", "/api/v1/users/me/", None),
        ("GET", "/api/v1/costs/", None),
        ("GET", "/api/v1/notifications/", None),
    ]
    for method, path, payload in reads:
        response = await client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 200, f"{method} {path} -> {response.status_code} {response.text[:200]}"

    # Reads that post a body because the query does not fit in a URL. These are
    # the ones a method-only guard would have broken.
    body_reads = [
        ("/api/v1/costs/match/", {"query": "concrete C25/30", "top_k": 5}),
        ("/api/v1/boq/boqs/search-cost-items/", {"query": "concrete", "limit": 5}),
        (
            "/api/v1/boq/boqs/suggest-rate/",
            {"description": "concrete slab 200mm", "unit": "m2"},
        ),
    ]
    for path, payload in body_reads:
        response = await client.post(path, headers=headers, json=payload)
        assert response.status_code != 403, f"POST {path} was refused, but it only reads: {response.text[:200]}"
        assert response.status_code < 500, f"POST {path} -> {response.status_code} {response.text[:200]}"

    # Signing in has to keep working, or the demo is a login page.
    signed_in = await client.post(
        "/api/v1/users/auth/login",
        json={"email": auth_headers["email"], "password": auth_headers["password"]},
    )
    assert signed_in.status_code == 200, f"sign-in refused on the read-only demo: {signed_in.text[:300]}"
    assert signed_in.json().get("access_token")

    # ...and it really did take the write carve-out rather than skipping it.
    async with async_session_factory() as session:
        stamped = (
            await session.execute(
                text("SELECT last_login_at FROM oe_users_user WHERE email = :e"),
                {"e": auth_headers["email"].lower()},
            )
        ).scalar_one()
    assert stamped is not None, "sign-in did not stamp last_login_at, so the carve-out went untested"

    after = await _census()
    moved = _diff(before, after)
    non_exempt = {t: v for t, v in moved.items() if t not in EXEMPT_TABLES}

    exempt_moved = {t: v for t, v in moved.items() if t in EXEMPT_TABLES}
    print("\n[phase C] flag ON, reads + sign-in: all served")
    print(f"[phase C] declared-exempt tables that moved: {exempt_moved or 'none'}")
    print(f"[phase C] every other table that moved: {non_exempt or 'none'}")

    assert not non_exempt, f"a read moved the database while the demo was read-only: {non_exempt}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_an_edit_to_existing_data_leaves_the_row_byte_for_byte(app_client, auth_headers, monkeypatch):
    """Phase D: the case a row count cannot see.

    The sweep in phase A posts empty bodies, so every request there is refused
    before it could have edited anything, and counts alone would have proved
    the same thing. This is the other shape of a demo write: a real, valid
    edit of a row that already exists. Nothing is created and nothing is
    deleted, so the count is identical either way, and only the digest can
    tell a refusal from a successful rename.
    """
    _app, client = app_client
    headers = auth_headers["headers"]

    _set_flag(monkeypatch, on=False)
    created = await client.post(
        "/api/v1/projects/",
        headers=headers,
        json={"name": f"Demo guard subject {uuid.uuid4().hex[:6]}", "currency": "EUR", "region": "DE"},
    )
    assert created.status_code == 201, created.text[:300]
    project_id = created.json()["id"]

    before = await _census()
    _set_flag(monkeypatch, on=True)

    response = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=headers,
        json={"name": "Renamed by a visitor", "description": "and described by one too"},
    )
    after = await _census()

    assert response.status_code == 403, f"a rename was not refused: {response.status_code} {response.text[:300]}"
    assert response.json()["detail"]["error"] == DEMO_READ_ONLY_ERROR

    reread = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["name"] != "Renamed by a visitor"

    moved = {t: v for t, v in _diff(before, after).items() if t not in EXEMPT_TABLES}
    projects = "oe_projects_project"
    print(f"\n[phase D] PATCH /api/v1/projects/{{id}} -> {response.status_code}")
    print(f"[phase D] {projects} before: {before.get(projects)}")
    print(f"[phase D] {projects} after:  {after.get(projects)}")
    print(f"[phase D] tables that moved: {moved or 'none'}")

    assert before.get(projects) == after.get(projects), "the project row changed under a refused edit"
    assert not moved, f"the database moved under a refused edit: {moved}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_the_guard_cannot_be_talked_out_of_it(app_client, auth_headers, monkeypatch):
    """No header, verb or spelling gets a write through."""
    _app, client = app_client
    headers = dict(auth_headers["headers"])

    _set_flag(monkeypatch, on=True)

    # An anonymous caller gets the refusal, not a 401: the demo says why.
    anonymous = await client.post("/api/v1/projects/", json={"name": "x"})
    _assert_contract(anonymous, "anonymous POST /api/v1/projects/")

    # A method override header is not a way round it.
    overridden = await client.post(
        "/api/v1/projects/",
        headers={**headers, "X-HTTP-Method-Override": "GET"},
        json={"name": "x"},
    )
    _assert_contract(overridden, "method-override POST /api/v1/projects/")

    # The underscore mirror mount of a module is the same endpoint, so one
    # allowlist entry covers both spellings and neither is a back door.
    mirrored = await client.post("/api/v1/bid_management/bidders/", headers=headers, json={})
    _assert_contract(mirrored, "underscore mirror POST /api/v1/bid_management/bidders/")

    # The deployment's own control surface is refused too, not exempted.
    upgrade = await client.post("/api/system/upgrade", headers=headers, json={})
    _assert_contract(upgrade, "POST /api/system/upgrade")


#: Path the write probe below is mounted at, and where its result lands. A
#: socket handler cannot return a value, so the outcome comes back through a
#: module global rather than a return.
_WRITE_PROBE_PATH = "/__demo_read_only_write_probe__"
_WRITE_PROBE: dict[str, Any] = {}


def _cause_chain(exc: BaseException) -> list[str]:
    """Type names down an exception's ``__cause__``/``__context__`` chain."""
    names: list[str] = []
    current: BaseException | None = exc
    while current is not None and len(names) < 10:
        names.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return names


async def _write_probe_socket(websocket: WebSocket) -> None:
    """A socket route that deliberately writes, so layer 2 can be seen through one.

    Defined at module level, and that is load-bearing rather than stylistic.
    This file uses postponed annotations, so ``websocket: WebSocket`` is stored
    as the string ``"WebSocket"``, and FastAPI resolves an endpoint's
    annotations against ``endpoint.__globals__``. A handler defined inside a
    test body, importing ``WebSocket`` inside that body too, therefore has no
    resolvable annotation: FastAPI falls back to reading the parameter as a
    required query field and closes the handshake with 1008 before the handler
    is ever entered. That is precisely how the previous version of this test
    failed, and it failed against a throwaway application, so it said nothing
    about the real one either way.
    """
    from app.core import demo_read_only as dro

    _WRITE_PROBE.clear()
    _WRITE_PROBE["scope"] = dro._write_scope.get()
    await websocket.accept()
    try:
        async with async_session_factory() as session:
            # A real row-moving UPDATE that cannot damage anything: PostgreSQL
            # writes a new tuple version and the value is unchanged. It has to
            # be a statement that genuinely succeeds with the flag off, or the
            # negative control below proves nothing - an earlier draft used an
            # INSERT that was refused for a missing NOT NULL column in both
            # polarities, which reads exactly like a working guard.
            result = await session.execute(text("UPDATE alembic_version SET version_num = version_num"))
            await session.commit()
        _WRITE_PROBE["outcome"] = "wrote"
        _WRITE_PROBE["rowcount"] = result.rowcount
    except Exception as exc:  # noqa: BLE001 - the refusal is the measurement
        _WRITE_PROBE["outcome"] = "refused"
        _WRITE_PROBE["chain"] = _cause_chain(exc)
    await websocket.close()


async def _drive_socket(
    app: Any,
    path: str,
    query: str = "",
    frames: tuple[dict[str, Any], ...] = (),
) -> list[dict[str, Any]]:
    """Run one WebSocket connection straight against the ASGI application.

    Deliberately not ``TestClient``: that drives its own event loop on another
    thread, while the asyncpg pool these handlers read through is bound to this
    one. Speaking ASGI directly keeps the connection on the test's loop, needs
    no new dependency, and exercises the real middleware stack, the real
    routing and the real application-level dependencies.

    Nothing is caught here. An exception escaping the application is the
    finding, not something to fold into the returned frames.
    """
    inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    await inbox.put({"type": "websocket.connect"})
    for frame in frames:
        await inbox.put(frame)
    await inbox.put({"type": "websocket.disconnect", "code": 1000})

    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return await inbox.get()

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "ws",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [
            (b"host", b"testserver"),
            (b"connection", b"upgrade"),
            (b"upgrade", b"websocket"),
            (b"sec-websocket-version", b"13"),
            (b"sec-websocket-key", b"dGhlIHNhbXBsZSBub25jZQ=="),
        ],
        "subprotocols": [],
        "state": {},
    }
    # A handler that never returns is a failure, not a reason to hang the suite.
    await asyncio.wait_for(app(scope, receive, send), timeout=30.0)
    return sent


@pytest.mark.asyncio
@pytest.mark.integration
async def test_websocket_routes_are_guarded_and_cannot_write(app_client, auth_headers, monkeypatch):
    """A WebSocket cannot change stored data on a read-only demo.

    This is the claim the release notes make to operators, and it is the one
    place the HTTP census above cannot reach: a socket carries no method, so
    layer 1 never refuses it, and the whole weight falls on layer 2 being armed
    for the life of the connection.

    Worth knowing before adding a third socket. Everywhere else in this module
    the guarantee is two independent layers, and an allowlist mistake is cheap
    because the other layer catches it. On a WebSocket it is one layer, by
    design - ``demo_read_only_guard`` refuses only when ``scope["type"]`` is
    ``http``, because an ``HTTPException`` is not something a handshake can
    carry. So a socket handler is held by the database tripwire alone, and the
    tripwire has one documented blind spot: ``_pg_bulk_insert_cost_rows`` in
    ``app.modules.costs.router`` writes through a raw DBAPI cursor that never
    reaches the listener. For an HTTP route layer 1 covers that hole. For a
    socket nothing would. Neither socket goes near it today, which is why the
    claim holds; a socket that reached that helper would break it silently.

    FastAPI fills a ``Request`` parameter only for an HTTP route, so a guard
    annotated ``Request`` is called with the argument missing on a WebSocket
    handshake and every socket in the application dies with a ``TypeError`` -
    with the flag off as much as on, because the failure is in solving the
    dependency rather than in anything the guard decides. ``HTTPConnection`` is
    the common base of both and is filled for either.

    Four checks, and the last two are the ones that matter:

    1. the guard's parameter really binds as a connection rather than a request;
    2. every socket route the real application mounts really does carry the
       guard, without which the rest would prove nothing;
    3. a real socket on the real application still serves with the flag on -
       driven, not inferred from the dependency being registered;
    4. a socket that does try to write is refused, and - the load-bearing half -
       the identical write on the identical socket succeeds with the flag off,
       so the refusal is the guard rather than a broken statement.
    """
    from fastapi.dependencies.utils import get_dependant
    from fastapi.routing import APIWebSocketRoute

    # 1. The parameter binds as a connection.
    dependant = get_dependant(path="/", call=demo_read_only_guard)
    assert dependant.http_connection_param_name == "connection"
    assert dependant.request_param_name is None

    app, _client = app_client

    # 2. Every mounted socket carries the guard.
    socket_routes = [r for r in app.routes if isinstance(r, APIWebSocketRoute)]
    assert socket_routes, "no socket routes found, so this test would prove nothing"
    paths = sorted(r.path for r in socket_routes)
    # Named, so that losing a socket to a rename fails here instead of quietly
    # shrinking what this test covers to whatever is left.
    assert any(p.endswith("/notifications/ws/") for p in paths), f"notifications socket missing from {paths}"
    assert any(p.endswith("/presence/") for p in paths), f"presence socket missing from {paths}"
    for route in socket_routes:
        names = [d.dependency for d in route.dependencies]
        assert demo_read_only_guard in names, f"{route.path} does not carry the guard"

    # The write probe is mounted on the shared application rather than on a
    # throwaway one, so that it is reached through the same middleware and the
    # same application-level dependencies as the two real sockets. It is
    # invisible to the sweep in phase A: an APIWebSocketRoute carries no
    # ``methods``, which is the first thing ``_mutating_routes`` reads.
    if not any(r.path == _WRITE_PROBE_PATH for r in socket_routes):
        app.websocket(_WRITE_PROBE_PATH)(_write_probe_socket)
    probe_route = next(r for r in app.routes if getattr(r, "path", None) == _WRITE_PROBE_PATH)
    assert demo_read_only_guard in [d.dependency for d in probe_route.dependencies], (
        "the write probe did not inherit the guard, so it cannot stand in for a real socket"
    )

    token = auth_headers["headers"]["Authorization"].split()[1]

    _set_flag(monkeypatch, on=True)

    # 3. A real socket still serves with the flag on.
    served = await _drive_socket(
        app,
        next(p for p in paths if p.endswith("/notifications/ws/")),
        f"token={token}",
        ({"type": "websocket.receive", "text": "ping"},),
    )
    kinds = [m["type"] for m in served]
    assert "websocket.accept" in kinds, f"the notifications socket was not accepted: {served}"
    payloads = [m.get("text", "") for m in served if m["type"] == "websocket.send"]
    assert any("notifications.hello" in p for p in payloads), f"no hello frame: {payloads}"
    assert any("pong" in p for p in payloads), f"the socket did not answer a ping: {payloads}"

    # 4a. A socket that writes is refused, and refused by layer 2 specifically.
    await _drive_socket(app, _WRITE_PROBE_PATH)
    assert _WRITE_PROBE.get("scope") is WriteScope.NONE, (
        f"the guard did not arm layer 2 for the connection: scope was {_WRITE_PROBE.get('scope')!r}"
    )
    assert _WRITE_PROBE.get("outcome") == "refused", (
        f"a websocket wrote to the database on a read-only demo: {_WRITE_PROBE}"
    )
    assert DemoReadOnlyError.__name__ in _WRITE_PROBE.get("chain", []), (
        f"the write failed, but not because of the guard: {_WRITE_PROBE}"
    )

    # 4b. The negative control. Without it, a write that can never succeed
    # would read exactly like a guard that works.
    _set_flag(monkeypatch, on=False)
    await _drive_socket(app, _WRITE_PROBE_PATH)
    assert _WRITE_PROBE.get("outcome") == "wrote", (
        f"the same write failed with the flag OFF, so the refusal above proves nothing: {_WRITE_PROBE}"
    )
    assert _WRITE_PROBE.get("rowcount", 0) >= 1, f"the control wrote no rows: {_WRITE_PROBE}"

    print(f"\n[sockets] guard attached to {len(socket_routes)} socket routes: {paths}")
    print("[sockets] flag ON: a socket write is refused by layer 2; flag OFF: the same write lands")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_the_database_tripwire_refuses_a_write_layer_one_let_through(monkeypatch):
    """Layer 2 on its own: a write from an allowlisted route is still refused."""
    from app.core import demo_read_only as dro

    _set_flag(monkeypatch, on=True)
    token = dro._set_write_scope(dro.WriteScope.NONE)
    try:
        async with async_session_factory() as session:
            with pytest.raises(Exception) as caught:  # noqa: PT011 - driver may wrap it
                await session.execute(
                    text("INSERT INTO oe_projects_project (id, name) VALUES (:i, 'x')"),
                    {"i": str(uuid.uuid4())},
                )
            chain: list[Any] = []
            exc: BaseException | None = caught.value
            while exc is not None and len(chain) < 10:
                chain.append(exc)
                exc = exc.__cause__ or exc.__context__
            assert any(isinstance(e, dro.DemoReadOnlyError) for e in chain), (
                f"the tripwire did not fire; got {caught.value!r}"
            )
            await session.rollback()

        # A read on the same scope is untouched.
        async with async_session_factory() as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        dro._reset_write_scope(token)
        _set_flag(monkeypatch, on=False)


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("SELECT 1", None),
        ("  \n-- a comment\nSELECT * FROM oe_projects_project", None),
        ("SELECT * FROM t FOR UPDATE", None),
        ("SET LOCAL app.current_tenant = 'x'", None),
        ("BEGIN", None),
        ("SAVEPOINT sa_1", None),
        ("COPY (SELECT 1) TO STDOUT", None),
        ("CREATE TEMP TABLE scratch (a int)", None),
        ('INSERT INTO "oe_activity_log" (a) VALUES (1)', ("INSERT", "oe_activity_log")),
        ("update oe_users_user set last_login_at = now()", ("UPDATE", "oe_users_user")),
        ("DELETE FROM public.oe_projects_project WHERE id = 1", ("DELETE", "oe_projects_project")),
        ("TRUNCATE TABLE oe_projects_project", ("TRUNCATE", "oe_projects_project")),
        ("COPY oe_projects_project FROM STDIN", ("COPY", None)),
        ("ALTER TABLE oe_projects_project ADD COLUMN x int", ("ALTER", None)),
    ],
)
def test_statement_classifier(statement, expected):
    """The tripwire's own reading of a statement, both polarities."""
    from app.core.demo_read_only import classify_statement

    assert classify_statement(statement) == expected
