# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Comparison operators for quantity-rule property conditions.

A rule's ``property_filter`` maps a property name to what the element must
carry. A bare value (``{"Phase Created": "Progetto"}``) is the original
equality form with ``*`` / ``?`` wildcards, and stays exactly that: every rule
saved before operators existed matches as it always did. Any other comparison
is an object carrying the reserved ``$op`` key::

    {"Phase Demolished": {"$op": "is_empty"},
     "Width": {"$op": "gt", "value": "200 mm"},
     "Type Name": {"$op": "not_contains", "value": "temp"}}

The ``$`` prefix keeps the object apart from a plain dict value, which the
equality form already reads as "nested containment" for dict-valued
properties. No IFC or Revit property set carries a ``$op`` key.

Numeric comparisons are unit-aware where a value carries a unit: "3 m" is
greater than "2500 mm", "12 m²" equals "12 m2". A bare number on one side is
read in the unit of the other side. Two units of different kinds (a length
against a mass) never compare, so such a condition selects nothing rather than
comparing meaningless numbers.

The same table drives the sandbox in ``frontend/src/features/bim/ruleSandbox.ts``;
both read ``__tests__/fixtures/ruleMatchingParity.json``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

OP_KEY = "$op"

OP_EQUALS = "equals"
OP_NOT_EQUALS = "not_equals"
OP_CONTAINS = "contains"
OP_NOT_CONTAINS = "not_contains"
OP_GT = "gt"
OP_GTE = "gte"
OP_LT = "lt"
OP_LTE = "lte"
OP_IS_EMPTY = "is_empty"
OP_IS_NOT_EMPTY = "is_not_empty"

NUMERIC_OPS = frozenset({OP_GT, OP_GTE, OP_LT, OP_LTE})
TEXT_OPS = frozenset({OP_CONTAINS, OP_NOT_CONTAINS})
VALUELESS_OPS = frozenset({OP_IS_EMPTY, OP_IS_NOT_EMPTY})
ALL_OPS = frozenset({OP_EQUALS, OP_NOT_EQUALS}) | NUMERIC_OPS | TEXT_OPS | VALUELESS_OPS

# What the import and the sidecar reader treat as "no value"
# (``rule_properties._EMPTY_VALUES``); Revit writes "None" for an unset phase.
_EMPTY_TEXT = frozenset({"", "none", "null", "n/a"})

MAX_TEXT_VALUE = 500

# Factor to the base unit of each kind: metre, square metre, cubic metre, kilogram.
_UNITS: dict[str, tuple[str, float]] = {
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "dm": ("length", 0.1),
    "m": ("length", 1.0),
    "km": ("length", 1000.0),
    "in": ("length", 0.0254),
    "ft": ("length", 0.3048),
    "yd": ("length", 0.9144),
    "mm2": ("area", 1e-6),
    "cm2": ("area", 1e-4),
    "dm2": ("area", 0.01),
    "m2": ("area", 1.0),
    "ha": ("area", 10000.0),
    "in2": ("area", 0.00064516),
    "ft2": ("area", 0.09290304),
    "sf": ("area", 0.09290304),
    "yd2": ("area", 0.83612736),
    "mm3": ("volume", 1e-9),
    "cm3": ("volume", 1e-6),
    "dm3": ("volume", 0.001),
    "l": ("volume", 0.001),
    "m3": ("volume", 1.0),
    "ft3": ("volume", 0.028316846592),
    "cf": ("volume", 0.028316846592),
    "yd3": ("volume", 0.764554857984),
    "g": ("mass", 0.001),
    "kg": ("mass", 1.0),
    "t": ("mass", 1000.0),
    "lb": ("mass", 0.45359237),
}

_NUMBER_RE = re.compile(r"^\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(.*?)\s*$", re.DOTALL)


@dataclass(frozen=True)
class Measure:
    """A number and the unit it was written in (``""`` when none)."""

    value: float
    unit: str


@dataclass
class ConditionError(Exception):
    """A condition the rule engine cannot evaluate; ``code`` names the message."""

    code: str
    key: str
    op: str = ""
    value: str = ""


def fold_unit(raw: str) -> str:
    """Canonical spelling of a unit: lower case, superscripts as digits."""
    return raw.replace("²", "2").replace("³", "3").replace(" ", "").lower()


def parse_measure(raw: Any) -> Measure | None:
    """Read a number with an optional unit; ``None`` for anything else.

    Booleans are not numbers. A decimal comma is not read: "1,500" means two
    different numbers in two conventions, and the rule editor writes every
    number it saves with a dot.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return Measure(float(raw), "") if math.isfinite(raw) else None
    if not isinstance(raw, str):
        return None
    m = _NUMBER_RE.match(raw)
    if not m:
        return None
    value = float(m.group(1))
    if not math.isfinite(value):
        return None
    unit = fold_unit(m.group(2))
    if unit and unit not in _UNITS:
        return None
    return Measure(value, unit)


def compare_measures(actual: Measure, expected: Measure) -> int | None:
    """-1 / 0 / 1 for actual against expected, or ``None`` when they do not compare."""
    a, e = actual.value, expected.value
    if actual.unit and expected.unit and actual.unit != expected.unit:
        kind_a, factor_a = _UNITS[actual.unit]
        kind_e, factor_e = _UNITS[expected.unit]
        if kind_a != kind_e:
            return None
        a, e = a * factor_a, e * factor_e
    if math.isclose(a, e, rel_tol=1e-9, abs_tol=1e-12):
        return 0
    return -1 if a < e else 1


def condition_of(pattern: Any) -> tuple[str, Any] | None:
    """``(op, value)`` when *pattern* is an operator object, else ``None``."""
    if isinstance(pattern, dict) and OP_KEY in pattern:
        return str(pattern.get(OP_KEY)), pattern.get("value")
    return None


def is_empty_value(actual: Any) -> bool:
    """Does the element carry no value for the property?"""
    if actual is None:
        return True
    if isinstance(actual, str):
        return actual.strip().lower() in _EMPTY_TEXT
    if isinstance(actual, (list, dict)):
        return all(is_empty_value(v) for v in (actual.values() if isinstance(actual, dict) else actual))
    return False


def _contains(actual: Any, needle: str) -> bool:
    if is_empty_value(actual):
        return False
    if isinstance(actual, list):
        return any(_contains(item, needle) for item in actual)
    if isinstance(actual, dict):
        return any(_contains(item, needle) for item in actual.values())
    return needle.strip().lower() in _as_text(actual).lower()


def _as_text(value: Any) -> str:
    """A scalar as the sandbox's ``String()`` writes it: 300.0 is "300", True is "true"."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return str(value)


def _numeric(actual: Any, op: str, expected: Any) -> bool:
    want = parse_measure(expected)
    if want is None:
        return False
    values = actual if isinstance(actual, list) else [actual]
    for item in values:
        have = parse_measure(item)
        if have is None:
            continue
        order = compare_measures(have, want)
        if order is None:
            continue
        if (
            (op == OP_GT and order > 0)
            or (op == OP_GTE and order >= 0)
            or (op == OP_LT and order < 0)
            or (op == OP_LTE and order <= 0)
        ):
            return True
    return False


def condition_matches(actual: Any, op: str, value: Any, equals: Any) -> bool:
    """Does *actual* satisfy ``op value``?

    *equals* is the equality predicate of the bare form (wildcards, trimming,
    list membership), passed in so the operator form cannot drift from it.
    An absent property satisfies the negations (it does not equal, it does not
    contain) and nothing else.
    """
    if op == OP_IS_EMPTY:
        return is_empty_value(actual)
    if op == OP_IS_NOT_EMPTY:
        return not is_empty_value(actual)
    if op == OP_EQUALS:
        return actual is not None and equals(actual, value)
    if op == OP_NOT_EQUALS:
        return actual is None or not equals(actual, value)
    if op == OP_CONTAINS:
        return _contains(actual, str(value))
    if op == OP_NOT_CONTAINS:
        return not _contains(actual, str(value))
    if op in NUMERIC_OPS:
        return _numeric(actual, op, value)
    return False


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value) if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    return None


def check_property_filter(property_filter: Any) -> dict[str, Any] | None:
    """Return the filter with operator values normalised, or raise ``ConditionError``.

    A bare value keeps its old meaning and is not checked here. An operator
    object must name a known operator and carry the value that operator
    takes: nothing for the empty checks, text for contains, a number (with an
    optional known unit) for the comparisons.
    """
    if property_filter is None:
        return None
    if not isinstance(property_filter, dict):
        raise ConditionError("bim_rules.filter_not_object", key="")
    out: dict[str, Any] = {}
    for key, pattern in property_filter.items():
        key_text = str(key)
        cond = condition_of(pattern)
        if cond is None:
            out[key_text] = pattern
            continue
        op, value = cond
        if op not in ALL_OPS:
            raise ConditionError("bim_rules.unknown_operator", key=key_text, op=op)
        if op in VALUELESS_OPS:
            if value not in (None, ""):
                raise ConditionError("bim_rules.value_not_allowed", key=key_text, op=op)
            out[key_text] = {OP_KEY: op}
            continue
        text = _scalar_text(value)
        if text is None or not text.strip():
            raise ConditionError("bim_rules.value_required", key=key_text, op=op)
        if len(text) > MAX_TEXT_VALUE:
            raise ConditionError("bim_rules.value_too_long", key=key_text, op=op)
        if op in NUMERIC_OPS and parse_measure(text) is None:
            raise ConditionError("bim_rules.value_not_number", key=key_text, op=op, value=text.strip())
        out[key_text] = {OP_KEY: op, "value": text.strip()}
    return out
