# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Daily jobs run by ``notifications.notification_worker.start_scheduler``.

* :func:`credential_expiry_sweep` (rule 9): calls the credentials module's own
  ``refresh_statuses`` per project, so a credential that lapses while nobody
  edits it still fires ``credentials.expiry.alert``. Benefits every module
  that links credentials; nothing is recomputed here.
* :func:`staffing_retention_sweep` (rule 14): for every ended file whose
  stored retention date has passed, reads the retention rules again and then
  deletes or anonymises it, as the rules say. A file on ``retention_hold`` is
  not ``ended`` and is never picked up; a file with a legal duty still running
  is kept and its date corrected.

One transaction per project or per file. A failure is logged at warning with
the id and the next item runs, so one bad file cannot hold every other file
past its retention end. Both are idempotent: a second run finds nothing
drifted and nothing due.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

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
        try:
            async with factory() as session:
                _examined, n = await CredentialService(session).refresh_statuses(pid)
                await session.commit()
        except Exception:
            # The boundary of a nightly job: this project is reported and the others still run.
            logger.warning("staffing: credential status refresh failed for project %s", pid, exc_info=True)
            continue
        updated += n
    return updated


async def staffing_retention_sweep(session_factory=None, *, today: date | None = None) -> int:
    """Apply the retention end to every file that is due on ``today`` (default: now). Returns files removed."""
    from app.database import async_session_factory
    from app.modules.staffing.repository import StaffingRepository
    from app.modules.staffing.service import StaffingService

    factory = session_factory or async_session_factory
    day = today or datetime.now(UTC).date()
    async with factory() as session:
        due = await StaffingRepository(session).file_ids_due(day)
    done = 0
    for file_id in due:
        try:
            async with factory() as session:
                pfile = await StaffingRepository(session).file_for_retention(file_id)
                if pfile is None:
                    continue
                outcome = await StaffingService(session).apply_retention(pfile, None, today=day)
                await session.commit()
        except Exception:
            # The boundary of a nightly job: this file is reported and the others still run.
            logger.warning("staffing: retention end failed for personnel file %s", file_id, exc_info=True)
            continue
        if outcome != "kept":
            done += 1
    if done:
        logger.info("staffing: %d personnel files deleted or anonymised at retention end", done)
    return done
