# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Daily jobs run by ``notifications.notification_worker.start_scheduler``.

* :func:`credential_expiry_sweep` (rule 9): calls the credentials module's own
  ``refresh_statuses`` per project, so a credential that lapses while nobody
  edits it still fires ``credentials.expiry.alert``. Benefits every module
  that links credentials; nothing is recomputed here.
* :func:`staffing_retention_sweep` (rule 14): anonymises ended files whose
  ``retention_due_at`` has passed. A file on ``retention_hold`` is not
  ``ended`` and is never picked up.

Both commit per project or per file and are idempotent: a second run finds
nothing drifted and nothing due.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def credential_expiry_sweep(session_factory=None) -> int:
    from app.database import async_session_factory
    from app.modules.credentials.models import Credential
    from app.modules.credentials.service import CredentialService

    factory = session_factory or async_session_factory
    async with factory() as session:
        stmt = select(Credential.project_id).where(Credential.valid_until.is_not(None)).distinct()
        project_ids = list((await session.execute(stmt)).scalars())
    updated = 0
    for pid in project_ids:
        async with factory() as session:
            _examined, n = await CredentialService(session).refresh_statuses(pid)
            await session.commit()
            updated += n
    return updated


async def staffing_retention_sweep(session_factory=None) -> int:
    from app.database import async_session_factory
    from app.modules.staffing.repository import StaffingRepository
    from app.modules.staffing.service import StaffingService

    factory = session_factory or async_session_factory
    today = datetime.now(UTC).date()
    done = 0
    async with factory() as session:
        svc = StaffingService(session)
        for pfile in await StaffingRepository(session).files_due(today):
            await svc.anonymise(pfile, None, reason="retention_due")
            done += 1
        await session.commit()
    if done:
        logger.info("staffing: anonymised %d personnel files at retention end", done)
    return done
