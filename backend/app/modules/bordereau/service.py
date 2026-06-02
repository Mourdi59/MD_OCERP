"""Bordereau de prix business logic.

Handles CRUD, attach/detach, line editing with scoped price propagation,
assembly component rollup, and dedup resolution.
"""

import logging
import re
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boq.models import BOQ, Position
from app.modules.boq.repository import BOQRepository, PositionRepository
from app.modules.bordereau.models import (
    Bordereau,
    BordereauComponent,
    BordereauLine,
)
from app.modules.bordereau.repository import (
    BordereauComponentRepository,
    BordereauLineRepository,
    BordereauRepository,
)

logger = logging.getLogger(__name__)

_MONEY_QUANTUM = Decimal("0.0001")


def _to_decimal(
    value: str | int | float | Decimal | None,
    default: Decimal = Decimal("0"),
) -> Decimal:
    if value is None:
        return default
    try:
        if isinstance(value, Decimal):
            d = value
        elif isinstance(value, bool):
            return default
        elif isinstance(value, int):
            d = Decimal(value)
        elif isinstance(value, float):
            d = Decimal(repr(value))
        elif isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            d = Decimal(stripped)
        else:
            return default
    except (InvalidOperation, ValueError, TypeError):
        return default
    if not d.is_finite():
        return default
    return d


def _quantize_money(value: Decimal) -> Decimal:
    if not value.is_finite():
        return value
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _compute_total(
    quantity: str | int | float | Decimal | None,
    unit_rate: str | int | float | Decimal | None,
) -> str:
    q = _to_decimal(quantity)
    r = _to_decimal(unit_rate)
    return str(_quantize_money(q * r))


def _is_bordereau_eligible(description: str, unit: str) -> bool:
    """True when a position should appear in the bordereau.

    A position is eligible only when it has a non-empty designation AND
    a meaningful unit — i.e. it is a real cost line, not a section header.
    Mirrors the frontend ``isSection`` helper: unit in ("", "section") means
    the row is a structural header with no price.
    """
    return bool(description.strip()) and unit.strip().lower() not in ("", "section")


def _normalise_designation(text: str) -> str:
    """Normalise a designation for dedup matching.

    Lowercase, strip accents, collapse whitespace, trim.
    """
    text = text.strip().lower()
    # Strip accents
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text[:255]


def _str_to_float(value: str | None) -> float:
    if value is None:
        return 0.0
    try:
        f = float(value)
    except (ValueError, TypeError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0
    return f


class BordereauService:
    """Business logic for Bordereau de prix."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BordereauRepository(session)
        self.line_repo = BordereauLineRepository(session)
        self.comp_repo = BordereauComponentRepository(session)
        self.boq_repo = BOQRepository(session)
        self.position_repo = PositionRepository(session)

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _ensure_not_locked(self, bordereau: Bordereau) -> None:
        if bordereau.is_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bordereau is locked and cannot be edited.",
            )

    async def _get_or_404(self, bordereau_id: uuid.UUID) -> Bordereau:
        bordereau = await self.repo.get_by_id(bordereau_id)
        if bordereau is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bordereau not found.",
            )
        return bordereau

    async def _get_line_or_404(self, line_id: uuid.UUID) -> BordereauLine:
        line = await self.line_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bordereau line not found.",
            )
        return line

    # ── CRUD Bordereau ───────────────────────────────────────────────────

    async def create_bordereau(
        self,
        project_id: uuid.UUID,
        name: str,
        description: str = "",
        currency: str = "",
    ) -> Bordereau:
        bordereau = Bordereau(
            project_id=project_id,
            name=name,
            description=description,
            currency=currency,
        )
        return await self.repo.create(bordereau)

    async def get_bordereau(self, bordereau_id: uuid.UUID) -> Bordereau:
        return await self._get_or_404(bordereau_id)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Bordereau], int]:
        return await self.repo.list_for_project(project_id, offset=offset, limit=limit)

    async def update_bordereau(
        self, bordereau_id: uuid.UUID, **fields: object,
    ) -> Bordereau:
        bordereau = await self._get_or_404(bordereau_id)
        update_fields = {k: v for k, v in fields.items() if v is not None}
        if not update_fields:
            return bordereau
        await self.repo.update_fields(bordereau_id, **update_fields)
        return await self._get_or_404(bordereau_id)

    async def delete_bordereau(self, bordereau_id: uuid.UUID) -> None:
        await self._get_or_404(bordereau_id)
        from sqlalchemy import update as sql_update

        # Clear BOQ.bordereau_id for any attached BOQ before deleting.
        # Position.bordereau_line_id is handled by FK SET NULL on cascade.
        await self.session.execute(
            sql_update(BOQ).where(BOQ.bordereau_id == bordereau_id).values(bordereau_id=None),
        )
        await self.repo.delete(bordereau_id)
        await self.session.flush()

    # ── Attach / Detach ──────────────────────────────────────────────────

    async def attach_to_boq(
        self, boq_id: uuid.UUID, bordereau_id: uuid.UUID,
    ) -> int:
        """Attach a bordereau to a BOQ and backfill existing positions.

        Returns the number of positions linked to the bordereau.
        """
        bordereau = await self._get_or_404(bordereau_id)
        boq = await self.boq_repo.get_by_id(boq_id)
        if boq is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="BOQ not found.",
            )
        if boq.is_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="BOQ is locked.",
            )
        if boq.project_id != bordereau.project_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Bordereau and BOQ must belong to the same project.",
            )
        await self.boq_repo.update_fields(boq_id, bordereau_id=bordereau_id)
        return await self._backfill_bordereau_for_boq(boq_id, bordereau_id)

    async def _backfill_bordereau_for_boq(
        self, boq_id: uuid.UUID, bordereau_id: uuid.UUID,
    ) -> int:
        """Scan all positions in a BOQ and link eligible ones to the bordereau.

        Eligible = has description AND a non-section unit (mirrors frontend
        ``isSection`` helper). Already-linked positions are skipped.
        Each eligible position is resolve'd to a bordereau line (find-or-create)
        and stamped with bordereau_line_id + canonical unit_rate.

        Uses snapshot-before-write discipline throughout: all ORM attributes
        are read into plain Python values before the first ``update_fields``
        call, since that ends in ``session.expire_all()``.

        Returns the number of positions linked (new links only).
        """
        from sqlalchemy import select as sql_select

        from app.modules.boq.models import Position as BOQPosition

        # Load all positions for this BOQ ordered by sort_order.
        stmt = (
            sql_select(BOQPosition)
            .where(BOQPosition.boq_id == boq_id)
            .order_by(BOQPosition.sort_order)
        )
        result = await self.session.execute(stmt)
        all_positions = list(result.scalars().all())

        # Snapshot every position into plain dicts BEFORE any write.
        # update_fields → expire_all() would expire all ORM instances.
        snapshots = [
            {
                "id": p.id,
                "description": p.description or "",
                "unit": p.unit or "",
                "quantity": p.quantity,
                "unit_rate": p.unit_rate,
                "version": int(p.version or 0),
                "reference_code": getattr(p, "reference_code", None),
                "bordereau_line_id": getattr(p, "bordereau_line_id", None),
            }
            for p in all_positions
        ]

        linked_count = 0

        for snap in snapshots:
            # Skip sections and positions that already have a link.
            if not _is_bordereau_eligible(snap["description"], snap["unit"]):
                continue
            if snap["bordereau_line_id"] is not None:
                continue

            try:
                line, _ = await self.resolve_line(
                    bordereau_id,
                    reference_code=snap["reference_code"],
                    designation=snap["description"],
                    unit=snap["unit"],
                )

                # Snapshot line fields before any write expires them.
                line_id = line.id
                line_version = line.version or 0
                line_rate = str(line.unit_rate)

                if _to_decimal(line_rate) == Decimal("0"):
                    # Seed the line from this position's own price.
                    new_rate = str(_quantize_money(_to_decimal(snap["unit_rate"])))
                    await self.line_repo.update_fields(
                        line_id,
                        unit_rate=new_rate,
                        version=line_version + 1,
                    )
                    line_rate = new_rate

                new_total = _compute_total(snap["quantity"], line_rate)
                await self.position_repo.update_fields(
                    snap["id"],
                    bordereau_line_id=line_id,
                    unit_rate=line_rate,
                    total=new_total,
                    version=snap["version"] + 1,
                )
                linked_count += 1

            except Exception:  # noqa: BLE001
                logger.warning(
                    "backfill: failed to link position %s to bordereau %s",
                    snap["id"],
                    bordereau_id,
                    exc_info=True,
                )

        return linked_count

    async def detach_from_boq(self, boq_id: uuid.UUID) -> None:
        boq = await self.boq_repo.get_by_id(boq_id)
        if boq is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="BOQ not found.",
            )
        if boq.is_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="BOQ is locked.",
            )
        await self.boq_repo.update_fields(boq_id, bordereau_id=None)

    # ── CRUD Lines ───────────────────────────────────────────────────────

    async def list_lines(self, bordereau_id: uuid.UUID) -> list[BordereauLine]:
        await self._get_or_404(bordereau_id)
        return await self.line_repo.list_for_bordereau(bordereau_id)

    async def create_line(
        self,
        bordereau_id: uuid.UUID,
        *,
        reference_code: str | None = None,
        designation: str = "",
        unit: str = "",
        unit_rate: float = 0,
        is_assembly: bool = False,
        source: str = "manual",
        metadata: dict | None = None,
    ) -> BordereauLine:
        bordereau = await self._get_or_404(bordereau_id)
        await self._ensure_not_locked(bordereau)

        # Check uniqueness of reference_code within this bordereau
        code = (reference_code or "").strip() or None
        if code:
            existing = await self.line_repo.find_by_reference_code(bordereau_id, code)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A line with reference_code '{code}' already exists in this bordereau.",
                )

        norm = _normalise_designation(designation)
        sort_order = await self.line_repo.next_sort_order(bordereau_id)

        line = BordereauLine(
            bordereau_id=bordereau_id,
            reference_code=code,
            designation=designation,
            designation_norm=norm,
            unit=unit,
            unit_rate=str(_quantize_money(_to_decimal(unit_rate))),
            is_assembly=is_assembly,
            source=source,
            sort_order=sort_order,
            metadata_=metadata or {},
        )
        return await self.line_repo.create(line)

    async def update_line(
        self,
        line_id: uuid.UUID,
        *,
        designation: str | None = None,
        unit: str | None = None,
        unit_rate: float | None = None,
        reference_code: str | None = None,
        is_assembly: bool | None = None,
        version: int | None = None,
        metadata: dict | None = None,
    ) -> tuple[BordereauLine, list[uuid.UUID], int, list[uuid.UUID]]:
        """Update a bordereau line and propagate price changes.

        Returns (line, affected_boq_ids, positions_updated, locked_boqs_skipped).
        """
        line = await self._get_line_or_404(line_id)
        bordereau = await self._get_or_404(line.bordereau_id)
        await self._ensure_not_locked(bordereau)

        # Snapshot ORM attributes before any write — update_fields ends with
        # session.expire_all() which would make later attribute access raise
        # MissingGreenlet in the async engine.
        line_bordereau_id = line.bordereau_id
        line_version = line.version or 0

        # Optimistic concurrency
        if version is not None and version != line_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stale version — another edit happened. Refresh and retry.",
            )

        fields: dict[str, object] = {}
        if designation is not None:
            fields["designation"] = designation
            fields["designation_norm"] = _normalise_designation(designation)
        if unit is not None:
            fields["unit"] = unit
        if unit_rate is not None:
            fields["unit_rate"] = str(_quantize_money(_to_decimal(unit_rate)))
        if reference_code is not None:
            fields["reference_code"] = reference_code.strip() or None
        if is_assembly is not None:
            fields["is_assembly"] = is_assembly
        if metadata is not None:
            fields["metadata_"] = metadata

        if not fields:
            return line, [], 0, []

        fields["version"] = line_version + 1
        await self.line_repo.update_fields(line_id, **fields)

        # Propagate price to linked positions in attached BOQs
        affected_boq_ids: list[uuid.UUID] = []
        positions_updated = 0
        locked_boqs_skipped: list[uuid.UUID] = []

        if "unit_rate" in fields:
            result = await self._propagate_price_to_positions(
                line_id=line_id,
                bordereau_id=line_bordereau_id,  # use snapshot — line is expired
                new_rate=str(fields["unit_rate"]),
            )
            affected_boq_ids = result["affected_boq_ids"]
            positions_updated = result["positions_updated"]
            locked_boqs_skipped = result["locked_boqs_skipped"]

        updated_line = await self._get_line_or_404(line_id)
        return updated_line, affected_boq_ids, positions_updated, locked_boqs_skipped

    async def delete_line(self, line_id: uuid.UUID) -> None:
        line = await self._get_line_or_404(line_id)
        bordereau = await self._get_or_404(line.bordereau_id)
        await self._ensure_not_locked(bordereau)
        # FK SET NULL on Position.bordereau_line_id handles cleanup
        await self.line_repo.delete(line_id)
        await self.session.flush()

    # ── Components (assembly decomposition) ──────────────────────────────

    async def list_components(self, line_id: uuid.UUID) -> list[BordereauComponent]:
        await self._get_line_or_404(line_id)
        return await self.comp_repo.list_for_line(line_id)

    async def replace_components(
        self,
        line_id: uuid.UUID,
        components_data: list[dict],
    ) -> tuple[BordereauLine, list[uuid.UUID], int, list[uuid.UUID]]:
        """Replace all components for an assembly line, recompute unit_rate, propagate.

        Returns (line, affected_boq_ids, positions_updated, locked_boqs_skipped).
        """
        line = await self._get_line_or_404(line_id)
        bordereau = await self._get_or_404(line.bordereau_id)
        await self._ensure_not_locked(bordereau)

        # Build component objects and compute totals
        new_components: list[BordereauComponent] = []
        rollup = Decimal("0")
        for idx, cd in enumerate(components_data):
            factor = _to_decimal(cd.get("factor", "1.0"))
            qty = _to_decimal(cd.get("quantity", "1.0"))
            uc = _to_decimal(cd.get("unit_cost", "0"))
            comp_total = _quantize_money(factor * qty * uc)
            rollup += comp_total

            comp = BordereauComponent(
                line_id=line_id,
                cost_item_id=cd.get("cost_item_id"),
                description=cd.get("description", ""),
                resource_type=cd.get("resource_type"),
                factor=str(_quantize_money(factor)),
                quantity=str(_quantize_money(qty)),
                unit=cd.get("unit", ""),
                unit_cost=str(_quantize_money(uc)),
                total=str(comp_total),
                sort_order=idx,
                metadata_=cd.get("metadata", {}),
            )
            new_components.append(comp)

        await self.comp_repo.replace_for_line(line_id, new_components)

        # Update line unit_rate from component rollup
        new_rate = str(_quantize_money(rollup))
        await self.line_repo.update_fields(
            line_id,
            unit_rate=new_rate,
            is_assembly=True,
            version=(line.version or 0) + 1,
        )

        # Propagate new rate
        result = await self._propagate_price_to_positions(
            line_id=line_id,
            bordereau_id=line.bordereau_id,
            new_rate=new_rate,
        )

        updated_line = await self._get_line_or_404(line_id)
        return (
            updated_line,
            result["affected_boq_ids"],
            result["positions_updated"],
            result["locked_boqs_skipped"],
        )

    # ── Price propagation (scoped to attached BOQs) ──────────────────────

    async def _propagate_price_to_positions(
        self,
        *,
        line_id: uuid.UUID,
        bordereau_id: uuid.UUID,
        new_rate: str,
    ) -> dict:
        """Propagate a new unit_rate to all positions linked to this line
        whose BOQ is currently attached to the bordereau.

        Uses the snapshot-before-write discipline to avoid MissingGreenlet.
        """
        positions = await self.line_repo.list_linked_positions(
            line_id, attached_bordereau_id=bordereau_id,
        )

        if not positions:
            return {"affected_boq_ids": [], "positions_updated": 0, "locked_boqs_skipped": []}

        # Snapshot before any write (expire_all discipline)
        snapshots = [
            {
                "id": p.id,
                "boq_id": p.boq_id,
                "quantity": p.quantity,
                "version": int(p.version or 0),
            }
            for p in positions
        ]

        # Check which BOQs are locked
        boq_ids = list({s["boq_id"] for s in snapshots})
        locked_boq_ids: set[uuid.UUID] = set()
        for bid in boq_ids:
            boq = await self.boq_repo.get_by_id(bid)
            if boq and boq.is_locked:
                locked_boq_ids.add(bid)

        affected_boq_ids: set[uuid.UUID] = set()
        positions_updated = 0

        for snap in snapshots:
            if snap["boq_id"] in locked_boq_ids:
                continue

            new_total = _compute_total(snap["quantity"], new_rate)
            await self.position_repo.update_fields(
                snap["id"],
                unit_rate=new_rate,
                total=new_total,
                version=snap["version"] + 1,
            )
            affected_boq_ids.add(snap["boq_id"])
            positions_updated += 1

        await self.session.flush()

        return {
            "affected_boq_ids": list(affected_boq_ids),
            "positions_updated": positions_updated,
            "locked_boqs_skipped": list(locked_boq_ids),
        }

    # ── Link a position to a bordereau line ──────────────────────────────

    async def link_position_to_line(
        self,
        position_id: uuid.UUID,
        line_id: uuid.UUID,
    ) -> Position:
        """Link a position to a bordereau line, deriving its unit_rate."""
        line = await self._get_line_or_404(line_id)
        position = await self.position_repo.get_by_id(position_id)
        if position is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position not found.",
            )

        # Verify the position's BOQ is attached to this bordereau
        boq = await self.boq_repo.get_by_id(position.boq_id)
        if boq is None or boq.bordereau_id != line.bordereau_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Position's BOQ is not attached to this bordereau.",
            )

        new_total = _compute_total(position.quantity, line.unit_rate)
        await self.position_repo.update_fields(
            position_id,
            bordereau_line_id=line_id,
            unit_rate=line.unit_rate,
            total=new_total,
            version=(position.version or 0) + 1,
        )
        pos = await self.position_repo.get_by_id(position_id)
        return pos  # type: ignore[return-value]

    async def unlink_position(self, position_id: uuid.UUID) -> Position:
        """Unlink a position from its bordereau line (keep cached price)."""
        position = await self.position_repo.get_by_id(position_id)
        if position is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position not found.",
            )
        await self.position_repo.update_fields(
            position_id,
            bordereau_line_id=None,
            version=(position.version or 0) + 1,
        )
        pos = await self.position_repo.get_by_id(position_id)
        return pos  # type: ignore[return-value]

    # ── Resolve (dedup) ──────────────────────────────────────────────────

    async def resolve_line(
        self,
        bordereau_id: uuid.UUID,
        *,
        reference_code: str | None = None,
        designation: str = "",
        unit: str = "",
    ) -> tuple[BordereauLine, bool]:
        """Find or create a bordereau line matching the given identity.

        Returns (line, created).
        """
        await self._get_or_404(bordereau_id)

        # 1. Try by reference_code
        code = (reference_code or "").strip()
        if code:
            existing = await self.line_repo.find_by_reference_code(bordereau_id, code)
            if existing is not None:
                return existing, False

        # 2. Try by normalised designation + unit
        norm = _normalise_designation(designation)
        if norm:
            existing = await self.line_repo.find_by_designation_norm(
                bordereau_id, norm, unit,
            )
            if existing is not None:
                return existing, False

        # 3. Create new line
        line = await self.create_line(
            bordereau_id,
            reference_code=code or None,
            designation=designation,
            unit=unit,
        )
        return line, True
