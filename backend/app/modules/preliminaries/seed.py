# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Starter checklist of common preliminaries items.

The estimator does not ship priced preliminaries - rates and durations are always
project specific, so amounts are entered by the user. What it ships is a starter
*checklist*: the common general-conditions items an estimator would otherwise
retype on every job (site office, supervision, temporary power, scaffolding,
final clean and so on), each tagged with a sensible category and whether it is
normally time-related or a fixed one-off.

One entry point: :func:`starter_checklist` returns the suggestions as plain
dicts (no amounts), and the router serves these so the UI can offer one-click
"add this item" chips.

A second entry point used to sit here, materialising the checklist as
zero-amount rows for demo projects. Nothing ever called it, on any code path,
and no project in the demo estate carried a single row from it.
"""

from __future__ import annotations

from app.modules.preliminaries.models import ITEM_TYPE_FIXED, ITEM_TYPE_TIME_RELATED

# (label, category, item_type). Categories match the model docstring buckets:
# site_establishment, site_staff, temporary_works, standing_plant, welfare, general.
_STARTER_CHECKLIST: list[tuple[str, str, str]] = [
    ("Site office and cabins", "site_establishment", ITEM_TYPE_TIME_RELATED),
    ("Site set-up and mobilisation", "site_establishment", ITEM_TYPE_FIXED),
    ("Hoarding, fencing and gates", "site_establishment", ITEM_TYPE_FIXED),
    ("Project management and supervision", "site_staff", ITEM_TYPE_TIME_RELATED),
    ("Site engineer", "site_staff", ITEM_TYPE_TIME_RELATED),
    ("Health and safety provision", "site_staff", ITEM_TYPE_TIME_RELATED),
    ("Temporary power", "temporary_works", ITEM_TYPE_TIME_RELATED),
    ("Temporary water and drainage", "temporary_works", ITEM_TYPE_TIME_RELATED),
    ("Scaffolding and access", "temporary_works", ITEM_TYPE_TIME_RELATED),
    ("Standing crane and hoist", "standing_plant", ITEM_TYPE_TIME_RELATED),
    ("Small plant and tools", "standing_plant", ITEM_TYPE_TIME_RELATED),
    ("Welfare facilities", "welfare", ITEM_TYPE_TIME_RELATED),
    ("Site cleaning", "welfare", ITEM_TYPE_TIME_RELATED),
    ("Final clean on completion", "general", ITEM_TYPE_FIXED),
    ("Insurances and bonds", "general", ITEM_TYPE_FIXED),
]


def starter_checklist() -> list[dict[str, str]]:
    """Return the starter checklist as ``[{label, category, item_type}]`` dicts.

    Pure and database-free (used by the router to offer suggestions). Amounts are
    deliberately absent - the user enters the rate, periods or fixed amount.
    """
    return [
        {"label": label, "category": category, "item_type": item_type}
        for label, category, item_type in _STARTER_CHECKLIST
    ]
