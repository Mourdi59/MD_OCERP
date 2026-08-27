# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Boot-path data repairs owned by the i18n foundation module.

Imported by :func:`app.core.data_repairs.discover_data_repairs`, which is what
makes the registrations below take effect.

Both repairs here touch ``oe_i18n_tax_config``, and they are of opposite
natures. That is the useful thing about having them side by side: the tax rate
one may not rewrite a value, and the subdivision one must.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.data_repairs import DataRepair, SupersededBy, register_data_repair

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

#: The table both repairs below rewrite.
TAX_CONFIG_TABLE = "oe_i18n_tax_config"


async def _run_romania_vat(session: AsyncSession) -> int:
    """Close Romania's 19 % VAT row and add the 21 % standard and 11 % reduced rates."""
    from app.modules.i18n_foundation.romania_vat import repair_romanian_vat_rates

    return await repair_romanian_vat_rates(session)


async def _run_tax_subdivision(session: AsyncSession) -> int:
    """Label the shipped Canadian and US tax rows with the subdivision they apply in."""
    from app.modules.i18n_foundation.tax_subdivision_repair import repair_tax_subdivisions

    return await repair_tax_subdivisions(session)


#: Nature ``superseded``: 19 % was the correct Romanian standard rate until
#: 31 July 2025 and the wrong one from 1 August. An estimate or invoice priced
#: before the reform must still resolve at 19 %, so the repair closes the old
#: row's window and inserts the new rate beside it rather than editing the rate
#: in place. The declaration below is what lets the registry's contract test
#: check that, instead of trusting the implementation to have got it right:
#: ``verify_supersede_shape`` fails the repair if any pre-existing row's rate
#: moves, and permits only ``effective_to`` going from empty to set.
ROMANIA_VAT_2025 = register_data_repair(
    DataRepair(
        repair_id="romania_vat_2025",
        revision="v3308_romania_vat_2025",
        summary="Close Romania's 19% VAT row and add the 21% standard and 11% reduced rates",
        run=_run_romania_vat,
        nature="superseded",
        superseded=SupersededBy(
            effective_from="2025-08-01",
            table=TAX_CONFIG_TABLE,
            closes_column="effective_to",
            # Closing the 19 % window also has to take the default flag off it:
            # a rate that is no longer in force cannot go on being the one the
            # UI offers first. It is a selection hint, not a value any invoice
            # was issued at, so moving it changes no money. Declared rather than
            # quietly permitted because the contract test caught this edit and
            # an undeclared exception is how a real one would get through later.
            also_updates=("is_default",),
        ),
    )
)

#: Nature ``always_wrong``, and worth saying why, because it writes to the same
#: table as the repair above and does the thing that one is forbidden to do: it
#: edits a pre-existing row in place. The difference is which column. These rows
#: were seeded without the subdivision they apply in - a Canadian provincial
#: rate that names no province is not a rate that was correct until some date,
#: it is a row that was incomplete from the day it was written. Nothing was
#: entitled to resolve against it, and filling the label in is not a change of
#: value. The rate itself is never touched.
TAX_SUBDIVISION_BACKFILL = register_data_repair(
    DataRepair(
        repair_id="tax_subdivision_backfill",
        revision="v3307_tax_subdivision",
        summary="Label the shipped Canadian and US tax rates with the subdivision they apply in",
        run=_run_tax_subdivision,
        nature="always_wrong",
    )
)
