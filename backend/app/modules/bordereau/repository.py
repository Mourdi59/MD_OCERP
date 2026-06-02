"""Bordereau de prix data access layer.

Pure data access — no business logic.
"""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.modules.boq.models import BOQ, Position
from app.modules.bordereau.models import (
    Bordereau,
    BordereauComponent,
    BordereauLine,
)


class BordereauRepository:
    """Data access for Bordereau model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, bordereau_id: uuid.UUID) -> Bordereau | None:
        return await self.session.get(Bordereau, bordereau_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Bordereau], int]:
        base = select(Bordereau).where(Bordereau.project_id == project_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            base.options(noload(Bordereau.lines))
            .order_by(Bordereau.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, bordereau: Bordereau) -> Bordereau:
        self.session.add(bordereau)
        await self.session.flush()
        return bordereau

    async def update_fields(self, bordereau_id: uuid.UUID, **fields: object) -> None:
        stmt = update(Bordereau).where(Bordereau.id == bordereau_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, bordereau_id: uuid.UUID) -> None:
        stmt = delete(Bordereau).where(Bordereau.id == bordereau_id)
        await self.session.execute(stmt)

    async def count_attached_boqs(self, bordereau_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(BOQ.bordereau_id == bordereau_id)
        return (await self.session.execute(stmt)).scalar_one()

    async def list_attached_boq_ids(self, bordereau_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(BOQ.id).where(BOQ.bordereau_id == bordereau_id)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]


class BordereauLineRepository:
    """Data access for BordereauLine model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, line_id: uuid.UUID) -> BordereauLine | None:
        return await self.session.get(BordereauLine, line_id)

    async def list_for_bordereau(self, bordereau_id: uuid.UUID) -> list[BordereauLine]:
        stmt = (
            select(BordereauLine)
            .where(BordereauLine.bordereau_id == bordereau_id)
            .order_by(BordereauLine.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_reference_code(
        self, bordereau_id: uuid.UUID, code: str,
    ) -> BordereauLine | None:
        stmt = select(BordereauLine).where(
            BordereauLine.bordereau_id == bordereau_id,
            BordereauLine.reference_code == code,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_by_designation_norm(
        self, bordereau_id: uuid.UUID, designation_norm: str, unit: str,
    ) -> BordereauLine | None:
        stmt = select(BordereauLine).where(
            BordereauLine.bordereau_id == bordereau_id,
            BordereauLine.designation_norm == designation_norm,
            BordereauLine.unit == unit,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create(self, line: BordereauLine) -> BordereauLine:
        self.session.add(line)
        await self.session.flush()
        await self.session.refresh(line)
        return line

    async def update_fields(self, line_id: uuid.UUID, **fields: object) -> None:
        stmt = update(BordereauLine).where(BordereauLine.id == line_id).values(**fields)
        await self.session.execute(stmt)
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, line_id: uuid.UUID) -> None:
        stmt = delete(BordereauLine).where(BordereauLine.id == line_id)
        await self.session.execute(stmt)

    async def next_sort_order(self, bordereau_id: uuid.UUID) -> int:
        stmt = select(func.max(BordereauLine.sort_order)).where(
            BordereauLine.bordereau_id == bordereau_id,
        )
        result = (await self.session.execute(stmt)).scalar_one_or_none()
        return (result or 0) + 1

    async def count_linked_positions(self, line_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            Position.bordereau_line_id == line_id,
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def list_linked_positions(
        self, line_id: uuid.UUID, *, attached_bordereau_id: uuid.UUID | None = None,
    ) -> list[Position]:
        """List positions linked to this line.

        When ``attached_bordereau_id`` is given, only positions whose
        BOQ is currently attached to that bordereau are returned.
        """
        stmt = select(Position).where(Position.bordereau_line_id == line_id)
        if attached_bordereau_id is not None:
            stmt = stmt.join(BOQ, Position.boq_id == BOQ.id).where(
                BOQ.bordereau_id == attached_bordereau_id,
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class BordereauComponentRepository:
    """Data access for BordereauComponent model."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_line(self, line_id: uuid.UUID) -> list[BordereauComponent]:
        stmt = (
            select(BordereauComponent)
            .where(BordereauComponent.line_id == line_id)
            .order_by(BordereauComponent.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace_for_line(
        self, line_id: uuid.UUID, components: list[BordereauComponent],
    ) -> list[BordereauComponent]:
        await self.session.execute(
            delete(BordereauComponent).where(BordereauComponent.line_id == line_id),
        )
        self.session.add_all(components)
        await self.session.flush()
        for c in components:
            await self.session.refresh(c)
        return components
