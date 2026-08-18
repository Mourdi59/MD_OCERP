# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Deterministic seed data for the Customer & Partner Portal.

Generates:
    20 portal users - 4 clients, 3 investors, 3 consultants,
                      4 subcontractors, 4 suppliers, 2 building users
    3-5 access rules per user across the supplied project IDs
    30 notifications (mix read/unread, across all kinds)
    50 document-access log entries

All UUIDs are derived from a stable seed (``uuid5(NS, label)``) so reruns
are idempotent.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.portal.models import (
    PortalAccessRule,
    PortalDocumentAccessLog,
    PortalNotification,
    PortalUser,
)
from app.modules.portal.repository import PortalUserRepository

logger = logging.getLogger(__name__)

_NS = uuid.UUID("d4d4c300-1909-4ddc-b01c-0a44e3b01c00")

# Every one of these people used to be named after the job they do: Bob Client,
# Nora Sub, Sven Tenant, and the same joke again in German and Polish, all of
# them at example.com. The portal is a screen we put in front of prospects and
# photograph for the public case pages, so a reader met twenty one placeholders
# and drew a conclusion about the product rather than about the seed. They are
# invented people now, each one plausible in the language the row declares, at
# invented organisations on the reserved .example TLD, which is the convention
# the rest of the demo data already follows.
#
# The seeder upserts on the email address, so these rows arrive alongside the
# old ones on a database that was seeded before this change rather than
# replacing them. That is a property of every rename in a seed keyed this way,
# and the answer is a fresh install rather than a migration of demonstration
# data.
_USERS: tuple[tuple[str, str, str, str], ...] = (
    # (email, full_name, role, language)
    ("a.renwick@harbourgate-estates.example", "Alice Renwick", "client", "en"),
    ("b.kaltenbach@sennwald-immobilien.example", "Bernd Kaltenbach", "client", "de"),
    ("c.montoro@vellara-inversiones.example", "Clara Montoro", "client", "es"),
    ("d.yermolov@nevskaya-estate.example", "Denis Yermolov", "client", "ru"),
    ("e.halloway@lindmark-capital.example", "Eric Halloway", "investor", "en"),
    ("f.osterkamp@wendhorst-beteiligungen.example", "Frieda Osterkamp", "investor", "de"),
    ("g.tamblyn@lindmark-capital.example", "George Tamblyn", "investor", "en"),
    ("h.prewitt@calderwood-advisory.example", "Hannah Prewitt", "consultant", "en"),
    ("i.zheleznov@stroysovet-proekt.example", "Ivan Zheleznov", "consultant", "ru"),
    ("j.weinhold@brandhoff-planung.example", "Julia Weinhold", "consultant", "de"),
    ("k.brenner@marlowe-fitout.example", "Kai Brenner", "subcontractor", "en"),
    ("l.sattler@terrolt-bau.example", "Lina Sattler", "subcontractor", "de"),
    ("m.dolinski@ravensworth-mep.example", "Marek Dolinski", "subcontractor", "en"),
    ("n.fenwick@ravensworth-mep.example", "Nora Fenwick", "subcontractor", "en"),
    ("o.lindqvist@peakstone-supply.example", "Oscar Lindqvist", "supplier", "en"),
    ("p.nordhausen@kessmar-rohbau.example", "Petra Nordhausen", "supplier", "de"),
    ("q.marsh@peakstone-supply.example", "Quentin Marsh", "supplier", "en"),
    ("r.alcaraz@suministros-vellara.example", "Rosa Alcaraz", "supplier", "es"),
    ("s.ackroyd@harbourgate-estates.example", "Sven Ackroyd", "building_user", "en"),
    ("t.reinbold@sennwald-immobilien.example", "Tomas Reinbold", "building_user", "de"),
)


_RESOURCE_TYPES = (
    "project",
    "contract",
    "document",
    "ticket",
    "subcontract",
    "payment_application",
    "po",
    "bid_package",
)


_NOTIFICATION_KINDS = (
    "document_ready",
    "ticket_update",
    "payment_status",
    "award_notification",
    "general",
)


# What each notification kind actually announces. A portal user reads the
# title and body, so they have to say something, not restate the row number.
_NOTIFICATION_TITLES = {
    "document_ready": "A document is ready for you",
    "ticket_update": "Your support ticket was updated",
    "payment_status": "Payment application status changed",
    "award_notification": "Tender award decision published",
    "general": "Notice from the project team",
}

_NOTIFICATION_BODIES = {
    "document_ready": "A new revision has been published to your document area.",
    "ticket_update": "An engineer has responded to your ticket.",
    "payment_status": "Your latest payment application has moved to the next stage.",
    "award_notification": "The award decision for your tender package is now available.",
    "general": "Please review the latest update from the project team.",
}


def _det_uuid(label: str) -> uuid.UUID:
    return uuid.uuid5(_NS, label)


async def seed_portal_demo(
    session: AsyncSession,
    projects_ids: Sequence[uuid.UUID] | None = None,
) -> dict[str, int]:
    """Idempotently populate the portal tables with demo data.

    Args:
        session: an active :class:`AsyncSession`.
        projects_ids: list of real project UUIDs to attach access rules to.
            When empty, deterministic synthetic UUIDs are used so the seed
            still runs end-to-end in an isolated test DB.

    Returns:
        Counts dict with ``users``, ``rules``, ``notifications``,
        ``access_logs`` keys.
    """
    project_pool: list[uuid.UUID] = list(projects_ids or [])
    if not project_pool:
        project_pool = [_det_uuid(f"demo-project-{i}") for i in range(5)]

    now = datetime.now(UTC)

    user_repo = PortalUserRepository(session)

    users: list[PortalUser] = []
    for idx, (email, full_name, role, lang) in enumerate(_USERS):
        existing = await user_repo.get_by_email(email)
        if existing is not None:
            users.append(existing)
            continue
        user = PortalUser(
            id=_det_uuid(f"portal-user-{email}"),
            email=email,
            full_name=full_name,
            portal_role=role,
            language=lang,
            timezone="UTC",
            status="active" if idx % 4 != 0 else "invited",
            invited_at=now - timedelta(days=30 - idx),
            last_login_at=now - timedelta(days=idx) if idx % 4 != 0 else None,
        )
        await user_repo.create(user)
        users.append(user)

    rules_created = 0
    for u_idx, user in enumerate(users):
        rule_count = 3 + (u_idx % 3)  # 3, 4, or 5
        for r_idx in range(rule_count):
            resource_type = _RESOURCE_TYPES[(u_idx + r_idx) % len(_RESOURCE_TYPES)]
            project_id = project_pool[r_idx % len(project_pool)]
            resource_id = (
                project_id if resource_type == "project" else _det_uuid(f"res-{user.email}-{resource_type}-{r_idx}")
            )
            permission = ("view", "comment", "submit", "sign")[r_idx % 4]
            rule = PortalAccessRule(
                id=_det_uuid(f"rule-{user.email}-{resource_type}-{r_idx}"),
                portal_user_id=user.id,
                resource_type=resource_type,
                resource_id=resource_id,
                permission=permission,
                granted_at=now - timedelta(days=10 - r_idx),
            )
            # merge (not add) so reruns are genuinely idempotent: the IDs are
            # deterministic, so a second boot would otherwise re-INSERT the same
            # primary key and raise a UniqueViolation that aborts the seed.
            await session.merge(rule)
            rules_created += 1
    await session.flush()

    notifications_created = 0
    for n_idx in range(30):
        user = users[n_idx % len(users)]
        kind = _NOTIFICATION_KINDS[n_idx % len(_NOTIFICATION_KINDS)]
        read_at = now - timedelta(hours=n_idx) if n_idx % 3 == 0 else None
        notif = PortalNotification(
            id=_det_uuid(f"notif-{n_idx}"),
            portal_user_id=user.id,
            kind=kind,
            title=_NOTIFICATION_TITLES[kind],
            body=_NOTIFICATION_BODIES[kind],
            link_path=f"/portal/items/{n_idx}",
            payload={"seq": n_idx, "kind": kind},
            read_at=read_at,
        )
        await session.merge(notif)
        notifications_created += 1
    await session.flush()

    access_logs_created = 0
    for l_idx in range(50):
        user = users[l_idx % len(users)]
        action = ("view", "download", "sign")[l_idx % 3]
        entry = PortalDocumentAccessLog(
            id=_det_uuid(f"acclog-{l_idx}"),
            portal_user_id=user.id,
            document_type="document",
            document_id=_det_uuid(f"doc-{l_idx}"),
            action=action,
            occurred_at=now - timedelta(minutes=l_idx * 7),
            ip_address=f"10.0.{l_idx // 256}.{l_idx % 256}",
        )
        await session.merge(entry)
        access_logs_created += 1
    await session.flush()

    counts = {
        "users": len(users),
        "rules": rules_created,
        "notifications": notifications_created,
        "access_logs": access_logs_created,
    }
    logger.info("Portal demo seed completed: %s", counts)
    return counts


__all__ = ["seed_portal_demo"]
