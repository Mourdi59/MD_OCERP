# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The governance area that hosts design is read from the catalogue's ``hosts`` tag, never from an area code."""

from __future__ import annotations

import pytest

from app.modules.design_management.hosting import DESIGN_TAG, hosting_area_code
from app.modules.project_governance import catalogue as cat


@pytest.mark.parametrize(
    ("cid", "expected"),
    [
        ("elf_module_framework", "m07_design_management"),
        ("neutral", "scope_quality"),
        ("hoai_lph", "scope_quality"),  # areas taken from neutral
        ("riba_2020", "scope_quality"),
        ("aia_b101", "scope_quality"),
        ("aho_heft9", "b"),
    ],
)
def test_every_shipped_model_resolves_a_design_area(cid: str, expected: str) -> None:
    assert hosting_area_code(cat.get_catalogue(cid)) == expected


def test_a_catalogue_without_the_tag_hosts_nothing() -> None:
    c = cat.get_catalogue("neutral")
    untagged = c.model_copy(update={"areas": tuple(a.model_copy(update={"hosts": ()}) for a in c.areas)})
    assert hosting_area_code(untagged) is None
    assert DESIGN_TAG == "design"
