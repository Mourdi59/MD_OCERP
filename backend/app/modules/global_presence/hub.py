# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""In-memory hub for global user presence.

A single room shared by every authenticated WebSocket. The hub tracks
which page (route) each user is viewing and whether they are active or
idle. Multiple browser tabs per user are supported: the "latest route"
is taken from whichever tab was most recently active, and a user only
"leaves" when ALL their sockets close.

Design choices
--------------

* **Pure asyncio / stdlib.**  No Redis, no Celery.  Single-worker
  deployments get full fan-out; multi-worker gets correct but
  worker-local presence.  Upgrade path: Postgres LISTEN/NOTIFY.

* **Two internal indices.**  ``_connections`` maps each WebSocket to its
  per-tab state; ``_user_sockets`` maps each user to their open tabs.
  This avoids monkey-patching WebSocket objects and gives O(1) lookup
  in both directions.

* **Dead-socket scrub on every broadcast.**  If a tab closes without a
  graceful close frame, ``send_json`` raises; we catch it and drop the
  socket so stale entries cannot leak memory.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Per-socket state kept by the hub."""

    user_id: uuid.UUID
    user_name: str
    route: str
    status: str  # "active" | "idle"
    connected_at: datetime
    last_active_at: datetime


class GlobalPresenceHub:
    """Subscribe / broadcast / disconnect for the global presence room."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, ConnectionInfo] = {}
        self._user_sockets: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────

    async def join(
        self,
        ws: WebSocket,
        *,
        user_id: uuid.UUID,
        user_name: str,
        route: str = "/",
    ) -> tuple[list[dict[str, Any]], bool]:
        """Register ``ws`` in the global room.

        Args:
            ws: The WebSocket connection.
            user_id: Authenticated user's UUID.
            user_name: Display name for the roster.
            route: Initial page route.

        Returns:
            A tuple of (roster, is_first_socket).  ``roster`` is the full
            list of currently present users (including the joiner).
            ``is_first_socket`` is True when this is the user's first tab,
            meaning a ``presence_join`` should be broadcast.
        """
        now = datetime.now(UTC)
        info = ConnectionInfo(
            user_id=user_id,
            user_name=user_name,
            route=route,
            status="active",
            connected_at=now,
            last_active_at=now,
        )
        async with self._lock:
            self._connections[ws] = info
            sockets = self._user_sockets.setdefault(user_id, set())
            is_first = len(sockets) == 0
            sockets.add(ws)
            roster = self._build_roster()
        return roster, is_first

    async def leave(self, ws: WebSocket) -> uuid.UUID | None:
        """Remove ``ws`` from the room.

        Returns:
            The user_id if this was their last socket (the caller should
            broadcast ``presence_leave``), or ``None`` if they still have
            other tabs open.
        """
        async with self._lock:
            info = self._connections.pop(ws, None)
            if info is None:
                return None
            sockets = self._user_sockets.get(info.user_id)
            if sockets is not None:
                sockets.discard(ws)
                if not sockets:
                    del self._user_sockets[info.user_id]
                    return info.user_id
        return None

    async def update_route(self, ws: WebSocket, route: str) -> dict[str, Any] | None:
        """Update the route for a specific tab.

        Returns:
            A user-level update dict to broadcast, or ``None`` if the
            socket is unknown.
        """
        async with self._lock:
            info = self._connections.get(ws)
            if info is None:
                return None
            info.route = route
            info.last_active_at = datetime.now(UTC)
            # "Active route" for this user = the most recently active tab.
            active_route = self._active_route_for(info.user_id)
        return {
            "user_id": str(info.user_id),
            "user_name": info.user_name,
            "route": active_route,
            "status": info.status,
        }

    async def update_status(self, ws: WebSocket, status: str) -> dict[str, Any] | None:
        """Update the activity status for a specific tab.

        Args:
            ws: The WebSocket connection.
            status: ``"active"`` or ``"idle"``.

        Returns:
            A user-level update dict to broadcast, or ``None`` if the
            socket is unknown.
        """
        if status not in ("active", "idle"):
            return None
        async with self._lock:
            info = self._connections.get(ws)
            if info is None:
                return None
            info.status = status
            info.last_active_at = datetime.now(UTC)
            active_route = self._active_route_for(info.user_id)
            # A user is "active" if ANY of their tabs is active.
            user_status = self._user_status_for(info.user_id)
        return {
            "user_id": str(info.user_id),
            "user_name": info.user_name,
            "route": active_route,
            "status": user_status,
        }

    async def broadcast(
        self,
        event: dict[str, Any],
        *,
        exclude: WebSocket | None = None,
    ) -> int:
        """Send ``event`` as JSON to every connected socket.

        Returns the number of successful sends. Dead sockets are
        scrubbed in-place.
        """
        async with self._lock:
            targets = list(self._connections.keys())

        sent = 0
        dead: list[WebSocket] = []
        for ws in targets:
            if ws is exclude:
                continue
            try:
                await ws.send_json(event)
                sent += 1
            except Exception:  # noqa: BLE001 - dead socket
                dead.append(ws)

        if dead:
            for ws in dead:
                await self.leave(ws)
        return sent

    # ── Diagnostics ───────────────────────────────────────────────────

    def connection_count(self) -> int:
        """Total number of open WebSocket connections."""
        return len(self._connections)

    def user_count(self) -> int:
        """Number of distinct users present."""
        return len(self._user_sockets)

    def roster(self) -> list[dict[str, Any]]:
        """Read-only snapshot of the current roster."""
        return self._build_roster()

    def reset(self) -> None:
        """Drop everything. Used by test teardown."""
        self._connections.clear()
        self._user_sockets.clear()

    # ── Internals ─────────────────────────────────────────────────────

    def _build_roster(self) -> list[dict[str, Any]]:
        """Build the deduplicated user roster (one entry per user)."""
        roster: list[dict[str, Any]] = []
        for user_id, sockets in self._user_sockets.items():
            if not sockets:
                continue
            # Pick the most recently active connection for this user.
            best: ConnectionInfo | None = None
            for ws in sockets:
                info = self._connections.get(ws)
                if info is None:
                    continue
                if best is None or info.last_active_at > best.last_active_at:
                    best = info
            if best is not None:
                roster.append(
                    {
                        "user_id": str(user_id),
                        "user_name": best.user_name,
                        "route": best.route,
                        "status": self._user_status_for(user_id),
                        "connected_at": best.connected_at.isoformat(),
                    }
                )
        return roster

    def _active_route_for(self, user_id: uuid.UUID) -> str:
        """Return the route from the user's most recently active tab."""
        sockets = self._user_sockets.get(user_id)
        if not sockets:
            return "/"
        best: ConnectionInfo | None = None
        for ws in sockets:
            info = self._connections.get(ws)
            if info is None:
                continue
            if best is None or info.last_active_at > best.last_active_at:
                best = info
        return best.route if best else "/"

    def _user_status_for(self, user_id: uuid.UUID) -> str:
        """A user is "active" if ANY of their tabs reports active."""
        sockets = self._user_sockets.get(user_id)
        if not sockets:
            return "idle"
        for ws in sockets:
            info = self._connections.get(ws)
            if info is not None and info.status == "active":
                return "active"
        return "idle"


# Module-level singleton. Each worker process has its own instance.
global_presence_hub = GlobalPresenceHub()
