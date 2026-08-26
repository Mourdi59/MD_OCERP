"""Section headers must not be convicted of missing a leaf-row attribute.

A section header aggregates its children. By construction it carries no
unit, no quantity, no rate and no classification code: those live on the
leaf rows underneath it. A rule that demands a leaf-level code and then
walks every row therefore convicts every header in the tree, and on a
deep bill the false findings outnumber the real ones.

Two directions are asserted here, because only one of them is obvious.

Forwards: the rules listed in ``NARROWED`` must not fire on a section
row. That is the fix.

Backwards: the rules listed in ``STILL_JUDGE_SECTIONS`` must keep firing
on one, and each carries a payload proving it. Narrowing a rule silences
it on every header, and a rule that stopped firing looks exactly like a
rule that passed. Those eight judge something a header genuinely has -
a title, an ordinal, a sign, an arithmetic identity, a currency, or a
classification code it chose to carry - so narrowing them would trade a
false positive for a false negative.

Section detection has two branches (``_get_leaf_positions``): an
explicit ``type`` field, and the parent_id graph for the seed and import
paths that never stamp one. Both are exercised, because a hand-rolled
guard that covers only the explicit branch passes a test that only
exercises the explicit branch.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.validation.engine import Severity, ValidationContext, ValidationRule, rule_registry
from app.core.validation.rules import (
    BC3CodeRequired,
    BirimFiyatCodeRequired,
    CPWDCodeRequired,
    CurrencyConsistency,
    DIN276CostGroupRequired,
    DIN276ValidCostGroup,
    DPGFLotRequired,
    GBT50500CodeRequired,
    GESNCodeRequired,
    MasterFormatClassificationRequired,
    MasterFormatValidDivision,
    NegativeValues,
    NoDuplicateOrdinals,
    NRMClassificationRequired,
    NRMValidElement,
    PositionHasDescription,
    SekisanCodeRequired,
    SINAPICodeRequired,
    TotalMismatch,
    register_builtin_rules,
)

SECTION_ID = "sec-1"
LEAF_OK_ID = "leaf-ok"
LEAF_BAD_ID = "leaf-bad"

# A code every one of the narrowed rules accepts, so the clean leaf in
# each payload is clean for whichever rule is under test. Verified by
# ``test_the_clean_leaf_is_clean_for_every_narrowed_rule`` rather than
# asserted by eye - a payload that quietly stopped being valid would
# turn every "no failure on the section" assertion into a coincidence.
GOOD_CLASSIFICATION: dict[str, str] = {
    "din276": "300",
    "nrm": "5.1.1",
    "masterformat": "03 30 00",
    "sinapi": "87878",
    "gesn": "08-01-001",
    "dpgf": "Lot 03",
    "gbt50500": "010101001",
    "cpwd": "2.1",
    "birimfiyat": "15.185",
    "sekisan": "1.1",
    "bc3_code": "E04AB010",
    "code": "E04AB010",
}

# The eleven ERROR-severity rules that demand a classification code the
# leaf rows carry and the headers above them do not.
NARROWED: list[type[ValidationRule]] = [
    DIN276CostGroupRequired,
    NRMClassificationRequired,
    MasterFormatClassificationRequired,
    SINAPICodeRequired,
    GESNCodeRequired,
    DPGFLotRequired,
    GBT50500CodeRequired,
    CPWDCodeRequired,
    BirimFiyatCodeRequired,
    SekisanCodeRequired,
    BC3CodeRequired,
]

_NARROWED_IDS = [cls.__name__ for cls in NARROWED]


def _ctx(positions: list[dict[str, Any]], *, region: str = "DE", standard: str = "") -> ValidationContext:
    return ValidationContext(
        data={"positions": positions},
        project_id="00000000-0000-0000-0000-000000000000",
        region=region,
        standard=standard,
        metadata={"locale": "en"},
    )


def _section(**overrides: Any) -> dict[str, Any]:
    """A section header that is correct in every way a header can be."""
    row: dict[str, Any] = {
        "id": SECTION_ID,
        "parent_id": None,
        "ordinal": "01",
        "description": "Groundworks",
        "unit": "section",
        "quantity": 0.0,
        "unit_rate": 0.0,
        "total": 0.0,
        "type": "section",
        "classification": {},
    }
    row.update(overrides)
    return row


def _leaf(**overrides: Any) -> dict[str, Any]:
    """A priced leaf row carrying a code every narrowed rule accepts."""
    row: dict[str, Any] = {
        "id": LEAF_OK_ID,
        "parent_id": SECTION_ID,
        "ordinal": "01.001",
        "description": "Excavation to reduce levels",
        "unit": "m3",
        "quantity": 10.0,
        "unit_rate": 25.0,
        "total": 250.0,
        "currency": "EUR",
        "type": "position",
        "classification": dict(GOOD_CLASSIFICATION),
    }
    row.update(overrides)
    return row


def _run(rule: ValidationRule, positions: list[dict[str, Any]]) -> list[Any]:
    return asyncio.run(rule.validate(_ctx(positions, standard=rule.standard)))


def _failures_against(rule: ValidationRule, positions: list[dict[str, Any]], element_ref: str) -> list[Any]:
    return [r for r in _run(rule, positions) if not r.passed and r.element_ref == element_ref]


# ── The clean payload really is clean ────────────────────────────────────


@pytest.mark.parametrize("rule_cls", NARROWED, ids=_NARROWED_IDS)
def test_the_clean_leaf_is_clean_for_every_narrowed_rule(rule_cls: type[ValidationRule]) -> None:
    """Guards the shared fixture, not the rules.

    Every assertion below reads "the section produced no failure while
    the leaf did". If the leaf's code stopped satisfying some rule, that
    rule's tests would still pass for the wrong reason.
    """
    failures = _failures_against(rule_cls(), [_section(), _leaf()], LEAF_OK_ID)
    assert failures == [], f"{rule_cls.__name__} rejects the shared good code: {[f.message for f in failures]}"


# ── Forwards: a header is not convicted ──────────────────────────────────


@pytest.mark.parametrize("rule_cls", NARROWED, ids=_NARROWED_IDS)
def test_a_section_header_is_not_convicted_of_missing_a_leaf_code(rule_cls: type[ValidationRule]) -> None:
    rule = rule_cls()
    positions = [_section(), _leaf()]
    assert _failures_against(rule, positions, SECTION_ID) == []


@pytest.mark.parametrize("rule_cls", NARROWED, ids=_NARROWED_IDS)
def test_a_header_known_only_from_the_parent_graph_is_not_convicted(rule_cls: type[ValidationRule]) -> None:
    """The implicit branch, which a hand-rolled ``type`` check misses.

    The seed and spreadsheet-import paths do not stamp a ``type`` field.
    Their headers are recognisable only because another row names them
    as its parent, so a guard that reads ``type`` alone convicts every
    one of them while passing the explicit-branch test above.
    """
    rule = rule_cls()
    section = _section()
    del section["type"]
    assert _failures_against(rule, [section, _leaf()], SECTION_ID) == []


# ── Backwards: the rule did not go silent ────────────────────────────────


@pytest.mark.parametrize("rule_cls", NARROWED, ids=_NARROWED_IDS)
def test_the_rule_still_convicts_a_leaf_row_carrying_no_code(rule_cls: type[ValidationRule]) -> None:
    """Skipping headers must not become skipping everything.

    Without this, every assertion above is satisfied by a rule that
    returns an empty list - which is the shape of the defect this whole
    file exists to fix.
    """
    rule = rule_cls()
    bad_leaf = _leaf(id=LEAF_BAD_ID, ordinal="01.002", description="Backfill", classification={})
    failures = _failures_against(rule, [_section(), _leaf(), bad_leaf], LEAF_BAD_ID)
    assert len(failures) == 1, f"{rule_cls.__name__} stopped convicting an uncoded leaf row"
    assert "01.002" in failures[0].message


# ── The eight that keep judging headers, asserted rather than noted ──────

# (rule, positions, id of the row whose conviction is expected or None
# for a whole-bill finding). Each defect is something a header genuinely
# has and can get wrong, which is why narrowing these would replace a
# false positive with a false negative.
STILL_JUDGE_SECTIONS: list[tuple[type[ValidationRule], list[dict[str, Any]], str | None]] = [
    # A header with no title is unreadable in every export and outline.
    (PositionHasDescription, [_section(description=""), _leaf()], SECTION_ID),
    # Two headers sharing an ordinal collide exactly as two leaves do.
    (NoDuplicateOrdinals, [_section(), _section(id="sec-2"), _leaf()], SECTION_ID),
    # A header that chose to carry a cost group must carry a real one.
    (DIN276ValidCostGroup, [_section(classification={"din276": "999"}), _leaf()], SECTION_ID),
    (NRMValidElement, [_section(classification={"nrm": "77"}), _leaf()], SECTION_ID),
    (MasterFormatValidDivision, [_section(classification={"masterformat": "77 00 00"}), _leaf()], SECTION_ID),
    # A negative figure is wrong on any row, header included.
    (NegativeValues, [_section(quantity=-1.0), _leaf()], SECTION_ID),
    # A header whose stored total contradicts its own zeroes is corrupt.
    (TotalMismatch, [_section(total=5000.0), _leaf()], SECTION_ID),
    # A stray currency on a header still splits the bill in two.
    (CurrencyConsistency, [_section(currency="USD"), _leaf()], None),
]

_STILL_IDS = [f"{cls.__name__}" for cls, _, _ in STILL_JUDGE_SECTIONS]


@pytest.mark.parametrize(("rule_cls", "positions", "element_ref"), STILL_JUDGE_SECTIONS, ids=_STILL_IDS)
def test_these_rules_deliberately_still_judge_a_section_row(
    rule_cls: type[ValidationRule],
    positions: list[dict[str, Any]],
    element_ref: str | None,
) -> None:
    failures = [r for r in _run(rule_cls(), positions) if not r.passed]
    assert failures, f"{rule_cls.__name__} no longer judges section rows"
    if element_ref is not None:
        assert any(f.element_ref == element_ref for f in failures)


@pytest.mark.parametrize(("rule_cls", "positions", "element_ref"), STILL_JUDGE_SECTIONS, ids=_STILL_IDS)
def test_the_same_rules_pass_a_well_formed_section_row(
    rule_cls: type[ValidationRule],
    positions: list[dict[str, Any]],
    element_ref: str | None,
) -> None:
    """Still judging headers is only defensible if the judgement is fair.

    The payloads above are deliberately defective. The same rule against
    a correct header must say nothing, or "keeps judging sections" would
    just mean "convicts every section".
    """
    assert [r for r in _run(rule_cls(), [_section(), _leaf()]) if not r.passed] == []


# ── Registry-wide, so a rule added later cannot reintroduce this ─────────


def _registered_error_rules() -> list[ValidationRule]:
    register_builtin_rules()
    return list(rule_registry._rules.values())


def test_no_registered_rule_convicts_a_well_formed_section_row() -> None:
    """The property, stated over the registry rather than over a list.

    A list of the rules that had this defect can only ever catch the
    next one after somebody adds it to the list. This asks the question
    of every rule that exists, so a new standard's ``code_required``
    fails here on the day it is written.

    Scoped to convictions that name the section row: a rule reading the
    payload as a purchase order or a submittal reports against no row at
    all, and those are a different defect (see the report).
    """
    rules = _registered_error_rules()
    # Load control. An empty or truncated registry answers this question
    # with silence, which reads exactly like a pass.
    assert len(rules) > 100, f"registry holds only {len(rules)} rules, so this swept almost nothing"
    by_id = {r.rule_id for r in rules}
    for expected in ("sinapi.code_required", "nrm.classification_required", "din276.cost_group_required"):
        assert expected in by_id, f"{expected} is not registered, so this test did not measure it"

    positions = [_section(), _leaf()]
    convicted: dict[str, str] = {}
    for rule in rules:
        try:
            results = asyncio.run(rule.validate(_ctx(positions, standard=rule.standard)))
        except Exception:  # noqa: BLE001 - a rule for another payload shape is not this test's business
            continue
        for res in results:
            if not res.passed and res.severity == Severity.ERROR and res.element_ref == SECTION_ID:
                convicted[rule.rule_id] = res.message
    assert convicted == {}, f"{len(convicted)} rule(s) convict a well-formed section header: {sorted(convicted)}"


def test_the_registry_sweep_can_see_a_conviction_at_all() -> None:
    """Negative control for the sweep above.

    Same walk, same scoping, against a header stripped of the things a
    header legitimately has. If this finds nothing, the sweep is not
    capable of finding anything and its silence means nothing.
    """
    rules = _registered_error_rules()
    broken = _section(description="", quantity=-1.0, total=5000.0)
    positions = [broken, _leaf()]
    convicted = set()
    for rule in rules:
        try:
            results = asyncio.run(rule.validate(_ctx(positions, standard=rule.standard)))
        except Exception:  # noqa: BLE001
            continue
        for res in results:
            if not res.passed and res.severity == Severity.ERROR and res.element_ref == SECTION_ID:
                convicted.add(rule.rule_id)
    assert "boq_quality.position_has_description" in convicted
    assert "boq_quality.negative_values" in convicted
    assert "boq_quality.total_mismatch" in convicted


# ── Where the detector draws the line, pinned from both sides ────────────

# A header is not detected by having children. ``boq/router.py::_row_type``
# builds the real payload and calls a row a section when it has no unit,
# no quantity and no rate, and the spreadsheet importer says the same
# thing in the same words before it ever reaches the engine. So a row of
# that shape is skipped whether or not anything names it as a parent.
#
# That is a real consequence and it cuts both ways, which is why the
# neighbours are here too: change any one of the three and the row is a
# leaf again and must still be convicted. Without the second half of this
# table, "the eleven skip headers" could quietly have become "the eleven
# skip anything cheap to skip". The thirteen rules that were already on
# this helper have always drawn the line here; the eleven now agree with
# them rather than disagreeing.
DETECTOR_BOUNDARY: list[tuple[str, str, float, float, bool]] = [
    ("no unit, no quantity, no rate", "", 0.0, 0.0, False),
    ("carries a unit", "m3", 0.0, 0.0, True),
    ("carries a quantity", "", 5.0, 0.0, True),
    ("carries a rate", "", 0.0, 12.5, True),
    ("fully priced", "m3", 5.0, 12.5, True),
]


def _row_type(unit: str, quantity: float, unit_rate: float) -> str:
    """Mirrors ``boq/router.py::_row_type``, which stamps the real payload."""
    normalised = (unit or "").strip().lower()
    if normalised in ("", "section") and quantity == 0.0 and unit_rate == 0.0:
        return "section"
    return "position"


@pytest.mark.parametrize(
    ("label", "unit", "quantity", "unit_rate", "expect_convicted"),
    DETECTOR_BOUNDARY,
    ids=[case[0] for case in DETECTOR_BOUNDARY],
)
def test_only_the_unpriced_unitless_row_is_read_as_a_header(
    label: str,
    unit: str,
    quantity: float,
    unit_rate: float,
    expect_convicted: bool,
) -> None:
    row = {
        "id": "orphan",
        "parent_id": None,
        "ordinal": "07",
        "description": "Sundries",
        "unit": unit,
        "quantity": quantity,
        "unit_rate": unit_rate,
        "total": quantity * unit_rate,
        "type": _row_type(unit, quantity, unit_rate),
        "classification": {},
    }
    failures = _failures_against(SINAPICodeRequired(), [row], "orphan")
    assert bool(failures) is expect_convicted, label
