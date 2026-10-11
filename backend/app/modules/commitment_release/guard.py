# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The checker this module installs into :mod:`app.core.commitment_guard`."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from app.core.commitment_guard import GuardVerdict


async def check_document(
    session: Any,
    *,
    project_id: uuid.UUID,
    kind: str,
    document_id: uuid.UUID | None,
    new_amount: Decimal,
    currency: str,
    actor_id: Any = None,
) -> GuardVerdict:
    """``ok | warn | block`` for binding ``new_amount`` on a document, per the project's enforcement."""
    from app.modules.commitment_release.service import CommitmentService

    out = await CommitmentService(session).check_document(
        project_id, kind=kind, document_id=document_id, new_amount=new_amount, currency=currency, actor_id=actor_id
    )
    return GuardVerdict(result=out["result"], reasons=tuple(out["reasons"]), item_id=out.get("item_id"))
