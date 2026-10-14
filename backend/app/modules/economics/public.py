# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What another module may read from a project's economics. Reads only.

Small frozen read models, so no module has to import this module's repository, service or ORM rows. Answers
``None`` when the project has no plan. ``approved`` says whether the frame is the approved one: a caller that
blocks on a frame must treat an unapproved frame as a draft, not as a limit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.economics.repository import EconomicsRepository

__all__ = ["FrameLineView", "FrameView", "project_frame"]


@dataclass(frozen=True)
class FrameLineView:
    code: str
    title: str
    amount: Decimal


@dataclass(frozen=True)
class FrameView:
    standard: str
    currency: str
    status: str
    approved: bool
    markup_allowance: Decimal
    lines: tuple[FrameLineView, ...]

    @property
    def total(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), Decimal("0")) + self.markup_allowance


async def project_frame(session: AsyncSession, project_id: uuid.UUID) -> FrameView | None:
    """The project's cost frame as it stands, or ``None`` when the project has no economics plan."""
    repo = EconomicsRepository(session)
    plan = await repo.plan(project_id)
    if plan is None:
        return None
    lines = tuple(FrameLineView(f.code, f.title, f.amount) for f in await repo.frame_lines(project_id))
    return FrameView(
        standard=plan.classification_standard,
        currency=plan.currency,
        status=plan.status,
        approved=plan.status == "approved",
        markup_allowance=plan.markup_allowance,
        lines=lines,
    )
