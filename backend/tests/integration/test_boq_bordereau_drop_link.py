"""Bordereau drag-and-drop — POST position with an explicit ``bordereau_line_id``.

Covers:

* Creating a Position with ``bordereau_line_id`` stamps the link, derives
  ``unit_rate`` from the line, honours ``after_position_id`` placement, and
  — crucially — does NOT spawn a near-duplicate bordereau line the way the
  designation-based auto-link would when the line's unit is stored
  un-normalised (``"M3"`` vs the position's normalised ``"m3"``).
* A line belonging to a bordereau the BOQ is NOT attached to is rejected
  with 422, and the whole create rolls back (no orphan position).

Run:
    cd backend
    python -m pytest tests/integration/test_boq_bordereau_drop_link.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

# ── Shared fixtures (module-scoped — same pattern as other BOQ integration tests) ──


@pytest_asyncio.fixture(scope="module")
async def shared_client() -> AsyncClient:
    """Module-scoped client with full app lifecycle."""
    app = create_app()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan_ctx():
        async with app.router.lifespan_context(app):
            yield

    async with lifespan_ctx():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture(scope="module")
async def shared_auth(shared_client: AsyncClient) -> dict[str, str]:
    """Module-scoped auth: register + force-promote-to-admin + login."""
    unique = uuid.uuid4().hex[:8]
    email = f"bdxdrop-{unique}@test.io"
    password = f"BdxDrop{unique}9!"

    reg = await shared_client.post(
        "/api/v1/users/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Bordereau Drop Tester",
            "role": "admin",
        },
    )
    assert reg.status_code == 201, f"Registration failed: {reg.text}"

    from sqlalchemy import update as sa_update

    from app.database import async_session_factory
    from app.modules.users.models import User

    async with async_session_factory() as session:
        await session.execute(sa_update(User).where(User.email == email.lower()).values(role="admin", is_active=True))
        await session.commit()

    token = ""
    data: dict = {}
    for attempt in range(3):
        resp = await shared_client.post(
            "/api/v1/users/auth/login",
            json={"email": email, "password": password},
        )
        data = resp.json()
        token = data.get("access_token", "")
        if token:
            break
        if "Too many login attempts" in data.get("detail", ""):
            await asyncio.sleep(5 * (attempt + 1))
            continue
        break
    assert token, f"Login failed: {data}"
    return {"Authorization": f"Bearer {token}"}


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_project(client: AsyncClient, auth: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/projects/",
        json={
            "name": f"BdxDrop Test {uuid.uuid4().hex[:6]}",
            "description": "bordereau drag-and-drop integration",
            "region": "DACH",
            "classification_standard": "din276",
            "currency": "EUR",
        },
        headers=auth,
    )
    assert resp.status_code == 201, f"Create project failed: {resp.text}"
    return resp.json()["id"]


async def _create_boq(client: AsyncClient, auth: dict[str, str], project_id: str) -> str:
    resp = await client.post(
        "/api/v1/boq/boqs/",
        json={
            "project_id": project_id,
            "name": f"BdxDrop BOQ {uuid.uuid4().hex[:6]}",
            "description": "bordereau drag-and-drop integration",
        },
        headers=auth,
    )
    assert resp.status_code == 201, f"Create BOQ failed: {resp.text}"
    return resp.json()["id"]


async def _create_bordereau(client: AsyncClient, auth: dict[str, str], project_id: str) -> str:
    resp = await client.post(
        "/api/v1/bordereau/bordereaux/",
        json={"project_id": project_id, "name": f"Bordereau {uuid.uuid4().hex[:6]}"},
        headers=auth,
    )
    assert resp.status_code == 201, f"Create bordereau failed: {resp.text}"
    return resp.json()["id"]


async def _attach_bordereau(client: AsyncClient, auth: dict[str, str], boq_id: str, bordereau_id: str) -> None:
    resp = await client.post(
        f"/api/v1/bordereau/boqs/{boq_id}/bordereau",
        json={"bordereau_id": bordereau_id},
        headers=auth,
    )
    assert resp.status_code == 200, f"Attach bordereau failed: {resp.text}"


async def _create_line(
    client: AsyncClient,
    auth: dict[str, str],
    bordereau_id: str,
    *,
    designation: str,
    unit: str,
    unit_rate: float,
) -> dict:
    resp = await client.post(
        f"/api/v1/bordereau/bordereaux/{bordereau_id}/lines",
        json={"designation": designation, "unit": unit, "unit_rate": unit_rate},
        headers=auth,
    )
    assert resp.status_code == 201, f"Create bordereau line failed: {resp.text}"
    return resp.json()


async def _list_lines(client: AsyncClient, auth: dict[str, str], bordereau_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/bordereau/bordereaux/{bordereau_id}/lines", headers=auth)
    assert resp.status_code == 200, f"List lines failed: {resp.text}"
    return resp.json()


async def _add_position(client: AsyncClient, auth: dict[str, str], boq_id: str, body: dict) -> dict:
    resp = await client.post(
        f"/api/v1/boq/boqs/{boq_id}/positions/",
        json={"boq_id": boq_id, **body},
        headers=auth,
    )
    assert resp.status_code == 201, f"Create position failed: {resp.text}"
    return resp.json()


async def _get_positions(client: AsyncClient, auth: dict[str, str], boq_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/boq/boqs/{boq_id}", headers=auth)
    assert resp.status_code == 200, f"GET BOQ failed: {resp.text}"
    return resp.json()["positions"]


# ═══════════════════════════════════════════════════════════════════════════
#  Happy path: explicit link, placement, and no duplicate-line regression
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_position_create_with_bordereau_line_id_links_and_places(
    shared_client: AsyncClient, shared_auth: dict[str, str]
) -> None:
    client, auth = shared_client, shared_auth
    project_id = await _create_project(client, auth)
    boq_id = await _create_boq(client, auth, project_id)

    # Two anchor positions BEFORE the bordereau is attached, so neither the
    # attach pass nor the auto-link can touch them or mint lines for them.
    anchor1 = await _add_position(
        client, auth, boq_id,
        {"ordinal": "0010", "description": "Anchor one", "unit": "m2", "quantity": 1, "unit_rate": 10},
    )
    anchor2 = await _add_position(
        client, auth, boq_id,
        {"ordinal": "0020", "description": "Anchor two", "unit": "m2", "quantity": 1, "unit_rate": 20},
    )

    bordereau_id = await _create_bordereau(client, auth, project_id)
    await _attach_bordereau(client, auth, boq_id, bordereau_id)

    # Un-normalised unit on purpose: "M3" stored verbatim on the line, while
    # PositionCreate.unit normalises to "m3". The designation-based auto-link
    # would miss this line and mint a duplicate — the explicit link must not.
    line = await _create_line(
        client, auth, bordereau_id,
        designation="Béton C30/37 pour fondations", unit="M3", unit_rate=185.0,
    )
    lines_before = await _list_lines(client, auth, bordereau_id)

    created = await _add_position(
        client, auth, boq_id,
        {
            "ordinal": "0015",
            "description": line["designation"],
            "unit": line["unit"],
            "quantity": 0,
            "unit_rate": line["unit_rate"],
            "link_mode": "standalone",
            "after_position_id": anchor1["id"],
            "bordereau_line_id": line["id"],
        },
    )

    assert created["bordereau_line_id"] == line["id"]
    assert Decimal(created["unit_rate"]) == Decimal("185"), f"rate not derived from line: {created['unit_rate']}"
    assert Decimal(created["quantity"]) == Decimal("0")
    assert created["sort_order"] == anchor1["sort_order"] + 1, "after_position_id placement broken"

    # The regression this feature exists to avoid: no near-duplicate line.
    lines_after = await _list_lines(client, auth, bordereau_id)
    assert len(lines_after) == len(lines_before), (
        f"explicit link minted a bordereau line: {[ln['designation'] for ln in lines_after]}"
    )

    # Placement visible in the BOQ read model too: dropped row sits between anchors.
    positions = await _get_positions(client, auth, boq_id)
    by_id = {p["id"]: p for p in positions}
    assert by_id[anchor1["id"]]["sort_order"] < by_id[created["id"]]["sort_order"] < by_id[anchor2["id"]]["sort_order"]


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-bordereau link is rejected and the create rolls back
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_position_create_with_foreign_bordereau_line_is_422_and_rolls_back(
    shared_client: AsyncClient, shared_auth: dict[str, str]
) -> None:
    client, auth = shared_client, shared_auth
    project_id = await _create_project(client, auth)
    boq_id = await _create_boq(client, auth, project_id)

    # Attached bordereau (so the BOQ has one) + a second, NON-attached one.
    attached_id = await _create_bordereau(client, auth, project_id)
    await _attach_bordereau(client, auth, boq_id, attached_id)
    foreign_id = await _create_bordereau(client, auth, project_id)
    foreign_line = await _create_line(
        client, auth, foreign_id, designation="Foreign line", unit="m", unit_rate=42.0,
    )

    before = await _get_positions(client, auth, boq_id)

    resp = await client.post(
        f"/api/v1/boq/boqs/{boq_id}/positions/",
        json={
            "boq_id": boq_id,
            "ordinal": "0010",
            "description": "should not persist",
            "unit": "m",
            "quantity": 0,
            "unit_rate": 42.0,
            "link_mode": "standalone",
            "bordereau_line_id": foreign_line["id"],
        },
        headers=auth,
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    assert "not attached" in resp.text.lower()

    # The position insert must have rolled back with the failed link.
    after = await _get_positions(client, auth, boq_id)
    assert len(after) == len(before), "orphan position persisted after failed link"
