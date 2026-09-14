# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""WebSocket endpoint for global user presence.

Clients connect to ``/ws/?token=<jwt>`` and receive a stream of
presence events: who joined, who left, and who changed page or went
idle. The JWT is passed as a query parameter because the browser
``WebSocket`` API cannot set custom headers.

Inbound messages (client -> server)
------------------------------------

* ``{"type": "route_update", "route": "/boq/abc123"}``
  - The user navigated to a different page.

* ``{"type": "status_update", "status": "idle"}``
  - The user went idle (or came back: ``"active"``).

* ``{"type": "ping"}``
  - Keep-alive. Server replies with ``{"event": "pong", ...}``.

Outbound events (server -> client)
-----------------------------------

* ``presence_snapshot`` - full roster, sent once on connect.
* ``presence_join``     - a new user appeared (first tab).
* ``presence_leave``    - a user disappeared (last tab closed).
* ``presence_update``   - a user changed route or status.
* ``pong``              - reply to a client ping.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.dependencies import decode_access_token
from app.modules.global_presence.hub import global_presence_hub

router = APIRouter(tags=["global_presence"])
logger = logging.getLogger(__name__)


# ── Auth helpers ──────────────────────────────────────────────────────────────


class _AuthenticationUnavailableError(Exception):
    """The token could not be judged, distinct from judging it bad.

    Allows the caller to close 1011 (server error) rather than 1008
    (policy violation) so the client knows the fault is not its credentials.
    """


async def _authenticate_ws(token: str | None) -> dict[str, Any] | None:
    """Decode a JWT passed as ``?token=`` on a WebSocket upgrade.

    Returns the payload on success, ``None`` when rejected.

    Raises:
        _AuthenticationUnavailableError: the caller could not be judged
            at all (database unreachable, misconfigured secret, etc.).
    """
    if not token:
        return None
    try:
        payload = decode_access_token(token, get_settings())
    except HTTPException:
        return None
    except Exception as exc:  # noqa: BLE001 - stays broad deliberately
        logger.exception("Global presence: WebSocket token decode failed")
        raise _AuthenticationUnavailableError from exc

    try:
        from app.dependencies import verify_user_exists_and_active

        user = await verify_user_exists_and_active(
            payload["sub"],
            issued_at=payload.get("iat"),
            session_id=payload.get("sid"),
        )
        payload["role"] = user.role
        return payload
    except HTTPException:
        return None
    except Exception as exc:  # noqa: BLE001 - stays broad deliberately
        logger.exception("Global presence: WebSocket user re-hydration failed")
        raise _AuthenticationUnavailableError from exc


async def _resolve_user_name(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Return a best-effort display string for a user.

    Prefers ``full_name``; falls back to ``email``; falls back to the
    string form of the UUID so the caller never has to handle ``None``.
    """
    from app.modules.users.models import User

    user = await session.get(User, user_id)
    if user is None:
        return str(user_id)
    return (user.full_name or "").strip() or user.email or str(user_id)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── WebSocket endpoint ────────────────────────────────────────────────────────


@router.websocket("/ws/")
async def global_presence_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Real-time global presence channel."""

    # ── Authenticate ──────────────────────────────────────────────
    try:
        payload = await _authenticate_ws(token)
    except _AuthenticationUnavailableError:
        await websocket.close(code=1011, reason="authentication unavailable")
        return
    if payload is None:
        await websocket.close(code=1008, reason="unauthenticated")
        return

    user_id_str = payload.get("sub")
    if not isinstance(user_id_str, str):
        await websocket.close(code=1008, reason="invalid token subject")
        return
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        await websocket.close(code=1008, reason="invalid user id")
        return

    # ── Resolve display name ──────────────────────────────────────
    async with async_session_factory() as sess:
        user_name = await _resolve_user_name(sess, user_id)

    await websocket.accept()

    # ── Join the hub ──────────────────────────────────────────────
    roster, is_first = await global_presence_hub.join(websocket, user_id=user_id, user_name=user_name)

    try:
        # Send the full roster snapshot to the newly connected client.
        await websocket.send_json(
            {
                "event": "presence_snapshot",
                "users": roster,
                "ts": _now_iso(),
            }
        )

        # Broadcast join only when this is the user's first tab.
        if is_first:
            await global_presence_hub.broadcast(
                {
                    "event": "presence_join",
                    "user_id": str(user_id),
                    "user_name": user_name,
                    "route": "/",
                    "status": "active",
                    "ts": _now_iso(),
                },
                exclude=websocket,
            )

        # ── Message loop ─────────────────────────────────────────
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            raw = message.get("text")
            if raw is None:
                continue

            if raw == "ping":
                await websocket.send_json({"event": "pong", "ts": _now_iso()})
                continue

            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            msg_type = data.get("type")

            if msg_type == "route_update":
                route = data.get("route")
                if isinstance(route, str) and route:
                    update = await global_presence_hub.update_route(websocket, route)
                    if update is not None:
                        await global_presence_hub.broadcast(
                            {
                                "event": "presence_update",
                                **update,
                                "ts": _now_iso(),
                            },
                        )

            elif msg_type == "status_update":
                status = data.get("status")
                if isinstance(status, str):
                    update = await global_presence_hub.update_status(websocket, status)
                    if update is not None:
                        await global_presence_hub.broadcast(
                            {
                                "event": "presence_update",
                                **update,
                                "ts": _now_iso(),
                            },
                        )

            elif msg_type == "ping":
                await websocket.send_json({"event": "pong", "ts": _now_iso()})

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Global presence websocket crashed")
    finally:
        left_user_id = await global_presence_hub.leave(websocket)
        if left_user_id is not None:
            await global_presence_hub.broadcast(
                {
                    "event": "presence_leave",
                    "user_id": str(left_user_id),
                    "ts": _now_iso(),
                },
            )
