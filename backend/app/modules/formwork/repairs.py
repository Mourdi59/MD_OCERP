# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Boot-path data repairs owned by the formwork module.

Imported by :func:`app.core.data_repairs.discover_data_repairs`, which is what
makes the registration below take effect. Nothing else imports this file, and
nothing needs to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.data_repairs import DataRepair, register_data_repair

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _run(session: AsyncSession) -> int:
    """Rename the trademarked formwork catalogue rows an old seed left behind.

    Imported inside the function so that importing this module costs only the
    registration, not the repair's own dependency tree.
    """
    from app.modules.formwork.debrand import repair_branded_catalogue

    return await repair_branded_catalogue(session)


#: Nature ``always_wrong``: the catalogue rows carried product names that were
#: never ours to ship, so there is no date on which the old value was correct
#: and no document that is entitled to keep reading it. Rewriting in place is
#: the whole repair - which is exactly what makes this the opposite case to the
#: tax repairs in ``i18n_foundation/repairs.py``, and why the registry insists
#: each repair says which of the two it is.
FORMWORK_DEBRAND = register_data_repair(
    DataRepair(
        repair_id="formwork_debrand",
        revision="v3271_formwork_debrand",
        summary="Rename trademarked formwork catalogue rows seeded before the de-brand",
        run=_run,
        nature="always_wrong",
    )
)
