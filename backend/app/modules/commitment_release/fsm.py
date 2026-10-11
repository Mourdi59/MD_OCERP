# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycle of a commitment item, on :class:`app.core.fsm.EntityFSM`.

::

    planned -> release_requested -> released | partially_released -> committed -> closed
                  |    ^                  |  re_release_required <-+
                  v    |                  v
      (rejected / withdrawn: back to the state before the request, attempt n+1)

``release_requested`` returns to whatever the item was before the request when
the route rejects it or the requester withdraws it: ``planned`` for a first
release, ``partially_released`` for a further tranche, ``re_release_required``
for a renewal. ``rejected`` and ``withdrawn`` are outcomes of a
:class:`ReleaseDecision`, not states. ``committed`` and ``closed`` follow the
linked documents and are written only by the module's own recompute.
"Decision overdue" is a computed flag, never a state.

``on_hold`` pauses an item from any working state and resumes into the state it
left (stored on the item). ``aborted`` and ``transferred`` end the item.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

ITEM_STATES: tuple[str, ...] = (
    "planned",
    "release_requested",
    "released",
    "partially_released",
    "committed",
    "closed",
    "re_release_required",
    "on_hold",
    "aborted",
    "transferred",
)

# States from which a release may be requested (first release, next tranche, renewal).
REQUESTABLE: tuple[str, ...] = ("planned", "partially_released", "released", "committed", "re_release_required")
# Working states an item may be paused, aborted or transferred from.
WORKING: tuple[str, ...] = ("planned", "released", "partially_released", "committed", "re_release_required")

_T: list[StateTransition] = []


def _t(src: str, dst: str, description: str) -> None:
    _T.append(StateTransition(src, dst, description=description))


for _src in REQUESTABLE:
    _t(_src, "release_requested", "release requested")
for _dst in ("planned", "partially_released", "released", "committed", "re_release_required"):
    _t("release_requested", _dst, "request decided or withdrawn")
_t("released", "committed", "a linked document counts as committed")
_t("partially_released", "committed", "a linked document counts as committed")
_t("re_release_required", "committed", "linked amount back within the release")
_t("committed", "released", "linked documents no longer count")
_t("committed", "partially_released", "linked documents no longer count")
_t("committed", "closed", "all linked documents completed or closed")
_t("closed", "committed", "a linked document reopened")
for _src in ("released", "partially_released", "committed"):
    _t(_src, "re_release_required", "linked amount above release plus tolerance")
for _src in WORKING:
    _t(_src, "on_hold", "put on hold")
    _t("on_hold", _src, "resumed")
    _t(_src, "aborted", "abort decided")
    _t(_src, "transferred", "transferred to another project or item")
_t("on_hold", "aborted", "abort decided")

ITEM_FSM = register_fsm(
    EntityFSM(
        "commitment_item",
        initial="planned",
        transitions=_T,
        terminal=("aborted", "transferred"),
    )
)

__all__ = ["ITEM_FSM", "ITEM_STATES", "REQUESTABLE", "WORKING"]
