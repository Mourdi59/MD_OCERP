# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Formwork module - temporary mould catalogue, priced assignments, pour cycles.

Three core entities:

* :class:`FormworkSystem` - catalogue of physical formwork systems (framed
  steel panels, aluminium slab tables, plywood and studs, climbing systems)
  with material, supplier, reuse cap, panel rate, erect/strike rate and
  striking time.
* :class:`FormworkAssignment` - links a project (and optionally a BOQ
  position) to a system with an area, an expected reuse count and a waste
  percentage. The server recomputes the rate build-up on every write to the
  assignment AND on every write to the catalogue row behind it, so a stored
  total never disagrees with the catalogue it came from.
* :class:`FormworkScheduleLine` - the pour-by-pour cycle under an assignment.
  Not decoration: the largest single pour sizes the panel set that has to be
  bought, and the total pour area divided by that set is the reuse count the
  rate may honestly be amortised over.

Validation is part of the workflow, not an add-on: eleven rules register under
the ``formwork`` rule set (see :mod:`app.modules.formwork.validators`) and are
reachable per assignment and per project.
"""


async def on_startup() -> None:
    """Module startup hook (called by the module loader after mount).

    Registers the module's validation rules into the core rule registry under
    the ``formwork`` rule set. The rules also register at import time, because
    the loader imports ``validators`` directly and a deployment that reaches
    the module by only one of those two routes must still get the rules.
    Idempotent either way - the registry overwrites a rule by id.

    Then repairs the trademarked catalogue rows an install upgraded from an old
    seed still carries. That belongs on the boot path rather than in the
    migration that already describes it, because the product never runs alembic
    and records the database at head regardless; see
    :mod:`app.modules.formwork.debrand` for the measurement behind that. The
    module loader awaits this hook without a guard of its own, so a failure here
    is contained rather than allowed to abort the rest of module loading: a
    catalogue that still reads badly is worth strictly less than a server that
    starts.
    """
    import logging

    from app.database import async_session_factory
    from app.modules.formwork.debrand import repair_branded_catalogue
    from app.modules.formwork.validators import register_formwork_rules

    register_formwork_rules()

    try:
        async with async_session_factory() as session:
            if await repair_branded_catalogue(session):
                await session.commit()
    except Exception:  # noqa: BLE001 - startup must survive a failed repair
        logging.getLogger(__name__).exception("formwork catalogue de-brand repair failed")
