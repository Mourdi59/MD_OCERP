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

Without the delivery-model module (no provider registered) the route code
alone is recorded and nothing is checked against a plan: rules 10 and 11 have
nobody to ask, the item reports ``delivery_model: not_installed`` and no
owner-furnished item exists. What is never stored is an id nobody can verify:
a contract package id is refused with ``package_plan_unavailable`` (422) until
a provider can confirm it belongs to the project's plan.

The commitment release module registers a second provider::

    register_commitment_provider(MyCommitments())

A capacity reservation with a fee above zero binds money, and money binds only
through a released commitment (rule 13). That port fails closed: with a fee
above zero and no provider registered the slot cannot be held
(``commitment_release_unavailable``), and a commitment id is stored only after
the provider confirmed it belongs to the project.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
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
    """What the delivery-model module answers for the plant register.

    ``ensure_owner_furnished_item`` is idempotent on ``plant_item_id``: the
    first call creates the owner-furnished item, every later call returns the
    same one with its installer package set to the value passed (``None``
    means the owner installs). A provider that returned the old installer
    would leave the route stuck on ``installer_mismatch``.

    ``release_owner_furnished_item`` is called when the route of the plant
    item stops being owner-furnished: the provider detaches or closes the item
    it keeps for ``plant_item_id``, so no owner-furnished item points at a
    plant item that is no longer one. Releasing when none exists is a no-op.
    """

    async def package_plan(self, session: Any, project_id: uuid.UUID) -> PackagePlan | None: ...

    async def release_owner_furnished_item(
        self, session: Any, project_id: uuid.UUID, *, plant_item_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> None: ...

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


# ── commitment release (rule 13) ──────────────────────────────────────────


@dataclass(frozen=True)
class CommitmentRef:
    """A commitment item as the slot rule needs it.

    ``released`` is the commitment module's own answer to "may money be bound
    on this item now"; this module never interprets that module's states.
    ``released_amount`` is how much is released in ``currency``, ``None`` when
    the release carries no ceiling. ``plant_item_id`` is the plant item the
    commitment was planned for, when it names one.
    """

    id: uuid.UUID
    released: bool
    released_amount: Decimal | None = None
    currency: str = ""
    plant_item_id: uuid.UUID | None = None


class CommitmentProvider(Protocol):
    async def get_commitment(
        self, session: Any, project_id: uuid.UUID, commitment_item_id: uuid.UUID
    ) -> CommitmentRef | None:
        """The commitment item of THIS project, or ``None`` for a missing or foreign id."""
        ...


_COMMITMENTS: list[CommitmentProvider] = []


def register_commitment_provider(provider: CommitmentProvider) -> None:
    """Register (replace) the one commitment provider."""
    _COMMITMENTS[:] = [provider]


def unregister_commitment_provider() -> None:
    """Remove the provider (tests)."""
    _COMMITMENTS.clear()


def commitment_provider() -> CommitmentProvider | None:
    return _COMMITMENTS[0] if _COMMITMENTS else None
