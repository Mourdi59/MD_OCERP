# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The package plan this module reads and the owner-furnished items it asks for.

Contract packages and owner-furnished items (OFI) belong to the delivery-model
module. It registers one provider on startup::

    register_package_plan_provider(MyProvider())

and this module calls it to check a procurement route against the package plan
(rule 10), to create or attach the OFI when a route is owner-furnished
(rule 11, idempotent on the plant item id) and to read the OFI's progress back
(``ordered`` / ``delivered`` / ``installed``).

Fail closed: with no provider registered every call that needs one raises
``package_plan_unavailable`` (422). A route is never accepted on the strength
of a plan nobody could read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

OFI_PROGRESS: tuple[str, ...] = ("none", "ordered", "delivered", "installed")


@dataclass(frozen=True)
class PackageRef:
    """One contract package of the project's package plan."""

    id: uuid.UUID
    code: str
    title: str
    supplies: bool
    installs: bool


@dataclass(frozen=True)
class PackagePlan:
    """The project's package plan as the route check needs it.

    ``single_owner_package_id`` is set when the delivery form leaves the owner
    holding one construction contract only (single-point delivery): a
    contractor-furnished item must then point to that package.
    """

    delivery_form: str
    packages: tuple[PackageRef, ...]
    single_owner_package_id: uuid.UUID | None = None

    def package(self, package_id: uuid.UUID | None) -> PackageRef | None:
        return next((p for p in self.packages if p.id == package_id), None) if package_id else None


@dataclass(frozen=True)
class OwnerFurnishedRef:
    """The OFI as this module sees it: who installs it and how far it got."""

    id: uuid.UUID
    installer_package_id: uuid.UUID | None
    progress: str = "none"


class PackagePlanProvider(Protocol):
    async def package_plan(self, session: Any, project_id: uuid.UUID) -> PackagePlan | None: ...

    async def ensure_owner_furnished_item(
        self,
        session: Any,
        project_id: uuid.UUID,
        *,
        plant_item_id: uuid.UUID,
        title: str,
        installer_package_id: uuid.UUID | None,
        actor_id: uuid.UUID | None,
    ) -> OwnerFurnishedRef: ...

    async def get_owner_furnished_item(
        self, session: Any, project_id: uuid.UUID, ofi_id: uuid.UUID
    ) -> OwnerFurnishedRef | None: ...


_PROVIDER: list[PackagePlanProvider] = []


def register_package_plan_provider(provider: PackagePlanProvider) -> None:
    """Register (replace) the one package plan provider."""
    _PROVIDER[:] = [provider]


def unregister_package_plan_provider() -> None:
    """Remove the provider (tests)."""
    _PROVIDER.clear()


def package_plan_provider() -> PackagePlanProvider | None:
    return _PROVIDER[0] if _PROVIDER else None
