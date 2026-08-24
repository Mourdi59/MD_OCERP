# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The contract standard a demo pack declares must reach the notice engine.

Driven from the shipped packs rather than from a constructed contract, because
a hand-built fixture is exactly what let the defect sit. ``normalize_standard``
mapped a FIDIC string to FIDIC in isolation and always had; what nothing
checked was the seam - whether any demo project put a standard anywhere the
resolver actually looks. None did, so every demo project fell through to the
standard-neutral periods, including the one whose pack names FIDIC, which the
engine supports and holds correct periods for.

Each test states the population it swept and asserts a floor on it. A suite of
this shape passes vacuously the day the packs stop declaring a form, and a
green run over an empty set is the failure mode it exists to prevent.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.demo_packs import PACK_TEMPLATES
from app.core.demo_projects import DemoTemplate, _generate_module_data
from app.modules.change_intelligence.time_bar import (
    GENERIC_PERIODS,
    NOTICE_PERIODS,
    STANDARD_UNKNOWN,
    normalize_standard,
    period_for,
)
from app.modules.change_intelligence.time_bar_service import (
    _TERMS_STANDARD_KEYS,
    _standard_from_terms,
)

_BASE = datetime(2026, 4, 1)


def _head_contract(template: DemoTemplate) -> dict | None:
    """The generated head contract for one pack, or ``None`` if it makes none."""
    generated = _generate_module_data(template, uuid.uuid4(), uuid.uuid4(), template.demo_id, _BASE)
    contracts = generated.get("contracts") or []
    return contracts[0] if contracts else None


def _declared_form(template: DemoTemplate) -> str:
    """The form of contract a pack declares in its own words, or ``""``."""
    return str(template.project_metadata.get("general_contractor_form") or "").strip()


def test_the_packs_still_declare_both_a_known_and_an_unknown_standard() -> None:
    """Without both, every other test in this file passes without discriminating."""
    declared = {t.demo_id: _declared_form(t) for t in PACK_TEMPLATES if _declared_form(t)}
    assert declared, "no pack declares a form of contract; the rest of this file proves nothing"

    resolved = {demo_id: normalize_standard(form) for demo_id, form in declared.items()}
    known = {d for d, s in resolved.items() if s != STANDARD_UNKNOWN}
    unknown = {d for d, s in resolved.items() if s == STANDARD_UNKNOWN}

    assert known, f"no pack declares a standard the engine supports: {resolved}"
    assert unknown, f"no pack declares one the engine does not know: {resolved}"


def test_a_declared_standard_is_stored_where_the_resolver_looks() -> None:
    """The key must be one the resolver reads, not merely a key.

    This is the half that was missing. Storing the form under a name the
    resolver never inspects satisfies every other assertion here and changes
    nothing on screen - which is exactly what ``general_contractor_form`` in
    project metadata did for as long as it existed.
    """
    swept = 0
    for template in PACK_TEMPLATES:
        if not _declared_form(template):
            continue
        head = _head_contract(template)
        assert head is not None, f"{template.demo_id} generates no head contract"
        terms = head.get("terms") or {}
        assert terms, f"{template.demo_id} declares a form but its head contract carries no terms"
        assert set(terms) & set(_TERMS_STANDARD_KEYS), (
            f"{template.demo_id} stores its standard under {sorted(terms)}, "
            f"none of which the resolver reads ({sorted(_TERMS_STANDARD_KEYS)})"
        )
        swept += 1
    assert swept >= 3, f"expected at least three packs declaring a form, swept {swept}"


def test_a_pack_naming_a_supported_standard_gets_that_standards_periods() -> None:
    """The seam end to end: pack text, terms, resolver, periods."""
    swept = 0
    for template in PACK_TEMPLATES:
        form = _declared_form(template)
        expected = normalize_standard(form)
        if expected == STANDARD_UNKNOWN:
            continue
        head = _head_contract(template)
        assert head is not None, f"{template.demo_id} generates no head contract"
        resolved = _standard_from_terms(head.get("terms") or {})
        assert resolved == expected, (
            f"{template.demo_id} declares {form!r} ({expected}) but its contract resolves to {resolved}"
        )
        for notice_type, days in NOTICE_PERIODS[expected].items():
            assert period_for(resolved, notice_type) == days
        swept += 1
    assert swept >= 1, "no pack declares a supported standard; this test swept nothing"


def test_the_supported_standard_differs_from_the_generic_fallback_where_it_should() -> None:
    """Otherwise a project resolving to UNKNOWN would satisfy the test above.

    Before the fix every demo project resolved to UNKNOWN and was given
    ``GENERIC_PERIODS``. FIDIC and the generic table agree on claim and EOT at
    28 days, so an assertion that happened to pick either would have passed
    against the defect. This names the periods where the two genuinely
    disagree and pins those.
    """
    swept = 0
    for template in PACK_TEMPLATES:
        expected = normalize_standard(_declared_form(template))
        if expected == STANDARD_UNKNOWN:
            continue
        differing = {
            notice_type: (days, GENERIC_PERIODS[notice_type])
            for notice_type, days in NOTICE_PERIODS[expected].items()
            if notice_type in GENERIC_PERIODS and GENERIC_PERIODS[notice_type] != days
        }
        assert differing, f"{expected} agrees with the generic table everywhere; this proves nothing"

        head = _head_contract(template)
        resolved = _standard_from_terms((head or {}).get("terms") or {})
        for notice_type, (own, generic) in differing.items():
            assert period_for(resolved, notice_type) == own
            assert period_for(resolved, notice_type) != generic
        swept += 1
    assert swept >= 1, "no pack declares a supported standard; this test swept nothing"


def test_a_pack_naming_a_standard_the_engine_does_not_know_stays_standard_neutral() -> None:
    """Not a gap, and it must not be forced into a standard the engine knows.

    The Canadian packs declare CCDC, which the engine holds no periods for.
    Resolving it to UNKNOWN and counting standard-neutral periods is the system
    being honest. Inventing CCDC day counts to make this green would be a
    fabricated deadline wearing a standard's name.
    """
    swept = 0
    for template in PACK_TEMPLATES:
        form = _declared_form(template)
        if not form or normalize_standard(form) != STANDARD_UNKNOWN:
            continue
        head = _head_contract(template)
        assert head is not None, f"{template.demo_id} generates no head contract"
        resolved = _standard_from_terms(head.get("terms") or {})
        assert resolved == STANDARD_UNKNOWN, f"{template.demo_id} declares {form!r}, expected UNKNOWN"
        for notice_type, days in GENERIC_PERIODS.items():
            assert period_for(resolved, notice_type) == days
        swept += 1
    assert swept >= 1, "no pack declares an unsupported standard; the control swept nothing"


def test_a_pack_declaring_no_form_carries_no_contract_standard() -> None:
    """Most packs name no form, and inventing one for them would be worse."""
    swept = 0
    for template in PACK_TEMPLATES:
        if _declared_form(template):
            continue
        head = _head_contract(template)
        if head is None:
            continue
        assert not (head.get("terms") or {}).get("contract_standard"), (
            f"{template.demo_id} declares no form but its contract carries a standard"
        )
        swept += 1
    assert swept >= 10, f"expected most packs to declare no form, swept {swept}"
