# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What this module answers for the plant register: the package plan and the owner-furnished items.

The plant register checks a procurement route against the package plan, asks
for the owner-furnished item of a plant item whose route is owner-furnished,
reads how far that item got, and lets it go when the route changes. It states
the contract as a protocol in its ``ports`` module; :class:`PackagePlanAnswers`
is this module's side of it, written over the module's own service.

How the plan is translated:

* A cancelled package is not in the plan the register sees.
* ``installs``: the package builds.
* ``supplies``: the package carries supply, or it builds. A package that builds
  furnishes what it installs; what it does not furnish is exactly what the
  owner-furnished items list. The ``supplies`` flag of the plan alone marks a
  separate supply scope and would leave a general contractor unable to furnish.
* ``single_owner_package_id``: set when exactly one package that builds sits at
  the top of the plan (the owner holds one construction contract). Read from
  the plan, never from the name of a delivery form.
* Progress: an item this module has not ordered reads ``none``. ``ordered``
  and ``delivered`` read as they are. An item handed to its installer reads
  ``delivered``: this module does not know that anything was installed.

The register is an optional module. :func:`register` is called at startup and
does nothing when it is not installed.
"""

from __future__ import annotations

import importlib
import logging
import uuid
from typing import Any

from app.modules.delivery_model.service import DeliveryModelService

logger = logging.getLogger(__name__)

# Item state of this module -> progress word of the register's port. Every state is named; none is a default.
PROGRESS = {
    "identified": "none",
    "route_set": "none",
    "ordered": "ordered",
    "delivered": "delivered",
    "handed_to_installer": "delivered",
}


def _ports() -> Any | None:
    """The register's ports, or ``None`` when the module is not installed."""
    try:
        return importlib.import_module("app.modules.plant_register.ports")
    except ImportError:
        return None


def single_owner_package(packages: list[dict[str, Any]]) -> uuid.UUID | None:
    """The one top-level package that builds, when there is exactly one; else ``None``."""
    top = [p for p in packages if p["builds"] and p["parent_id"] is None]
    return uuid.UUID(top[0]["id"]) if len(top) == 1 else None


def plan_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The packages of the plan as the register reads them: ``{id, code, title, supplies, installs}``."""
    return [
        {
            "id": uuid.UUID(p["id"]),
            "code": p["code"],
            "title": p["title"],
            "supplies": bool(p["supplies"] or p["builds"]),
            "installs": bool(p["builds"]),
        }
        for p in packages
    ]


def _live(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in packages if p["status"] != "cancelled"]


class PackagePlanAnswers:
    """This module's side of the register's ``PackagePlanProvider`` protocol."""

    def __init__(self, ports: Any) -> None:
        self._ports = ports

    def _ref(self, row: Any) -> Any:
        return self._ports.OwnerFurnishedRef(
            id=row.id,
            installer_package_id=row.package_id if row.install_by == "package" else None,
            progress=PROGRESS[row.status],
        )

    async def package_plan(self, session: Any, project_id: uuid.UUID) -> Any | None:
        """The project's package plan, or ``None`` while the project has no delivery model."""
        svc = DeliveryModelService(session)
        model = await svc.get_model(project_id)
        if model is None:
            return None
        packages = _live(await svc.package_rows(project_id))
        form = model.selected_form_code or await svc._leading_form(project_id) or ""
        return self._ports.PackagePlan(
            delivery_form=form,
            packages=tuple(self._ports.PackageRef(**p) for p in plan_packages(packages)),
            single_owner_package_id=single_owner_package(packages),
        )

    async def ensure_owner_furnished_item(
        self,
        session: Any,
        project_id: uuid.UUID,
        *,
        plant_item_id: uuid.UUID,
        title: str,
        installer_package_id: uuid.UUID | None,
        actor_id: uuid.UUID | None,
    ) -> Any:
        """The owner-furnished item of this plant item, created on the first call; its installer as passed."""
        row = await DeliveryModelService(session).ensure_ofi_for_plant_item(
            project_id, plant_item_id, title=title, installer_package_id=installer_package_id, actor_id=actor_id
        )
        return self._ref(row)

    async def get_owner_furnished_item(self, session: Any, project_id: uuid.UUID, ofi_id: uuid.UUID) -> Any | None:
        row = await DeliveryModelService(session).repo.ofi(project_id, ofi_id)
        return self._ref(row) if row is not None else None

    async def release_owner_furnished_item(
        self, session: Any, project_id: uuid.UUID, *, plant_item_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> None:
        """The plant item is no longer owner-furnished: its item here is detached and stays, unlinked."""
        await DeliveryModelService(session).release_ofi_of_plant_item(project_id, plant_item_id, actor_id=actor_id)


def register() -> bool:
    """Register this module as the register's package plan provider; ``False`` when it is not installed."""
    ports = _ports()
    if ports is None:
        logger.debug("delivery_model: no plant register installed, no package plan provider registered")
        return False
    ports.register_package_plan_provider(PackagePlanAnswers(ports))
    return True
