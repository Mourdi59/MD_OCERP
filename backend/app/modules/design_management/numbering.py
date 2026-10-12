# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Drawing numbers from a scheme: compose, parse, validate. Pure, no database.

The service fills the field values (from the project, the design role, the WBS
node or what the user typed), asks :func:`scope_key` for the counter to
allocate from under a row lock, and :func:`compose` joins the result. Every
number, generated or typed, goes through :func:`validate`, which names the
failing field (rule 6) and refuses status or revision segments (rule 10).
:func:`parse` turns a valid number back into its parts (rule 7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.modules.design_management.catalogue import CONTAINER_PART, DrawingNumbering, NumberingField

#: Revision codes as CDE writes them (``P01``, ``C02``, ``P.01.01``, ``C.02``).
_REVISION = re.compile(r"^[PC](\d{2}|\.\d{1,3}(\.\d{1,3})?)$")


def _status_codes() -> set[str]:
    from app.modules.cde.suitability import SUITABILITY_CODES

    return {c for entries in SUITABILITY_CODES.values() for c, _ in entries}


@dataclass(frozen=True)
class FieldIssue:
    """One reason a number does not match its scheme."""

    code: str
    field: str | None = None
    value: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "value": self.value}


@dataclass
class Validation:
    valid: bool
    issues: list[FieldIssue] = field(default_factory=list)
    parts: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "issues": [i.as_dict() for i in self.issues], "parts": self.parts}


def _joiner(scheme: DrawingNumbering, f: NumberingField, index: int) -> str:
    if index == 0:
        return ""
    return scheme.separator if f.joiner is None else f.joiner


def normalise(scheme: DrawingNumbering, value: str) -> str:
    """Apply the scheme's case to a field value or a whole number."""
    value = (value or "").strip()
    if scheme.case == "upper":
        return value.upper()
    if scheme.case == "lower":
        return value.lower()
    return value


def scope_key(scheme: DrawingNumbering, values: dict[str, str]) -> str:
    """The counter key: scheme id plus the values of the scope fields, in scheme order."""
    parts = [f"{code}={normalise(scheme, values.get(code, ''))}" for code in scheme.scope_fields()]
    return f"{scheme.id}|" + "|".join(parts)


def format_number(scheme: DrawingNumbering, value: int) -> str:
    number = scheme.field("number")
    pad = number.pad if number and number.pad else 1
    return str(value).zfill(pad)


def compose(scheme: DrawingNumbering, values: dict[str, str], number: int | str) -> str:
    """Join field values in scheme order; an empty optional field is left out with its joiner."""
    out = []
    for i, f in enumerate(scheme.fields):
        raw = format_number(scheme, int(number)) if f.code == "number" else normalise(scheme, values.get(f.code, ""))
        if not raw and not f.required:
            continue
        out.append(_joiner(scheme, f, i) + raw)
    return "".join(out)


def missing_values(scheme: DrawingNumbering, values: dict[str, str]) -> list[str]:
    """Required fields (except the number) that have no value yet."""
    return [
        f.code for f in scheme.fields if f.code != "number" and f.required and not (values.get(f.code) or "").strip()
    ]


def _lenient_part(scheme: DrawingNumbering, f: NumberingField, nxt: NumberingField | None) -> str:
    """A permissive group for one field, used to find which field is wrong."""
    glued = nxt is not None and nxt.joiner == ""
    if glued and f.length_min and f.length_max:
        return f".{{{f.length_min},{f.length_max}}}"
    if glued and f.code == "number":
        return r"\d+"
    if f.length_min and f.length_max and f.joiner == "":
        return f".{{{f.length_min},{f.length_max}}}"
    sep = re.escape(scheme.separator)
    return f"[^{sep}]+"


def _build(scheme: DrawingNumbering, part: Any) -> re.Pattern[str]:
    chunks = []
    for i, f in enumerate(scheme.fields):
        nxt = scheme.fields[i + 1] if i + 1 < len(scheme.fields) else None
        body = f"(?P<{f.code}>{part(f, nxt)})"
        piece = re.escape(_joiner(scheme, f, i)) + body
        chunks.append(piece if f.required else f"(?:{piece})?")
    flags = re.IGNORECASE if scheme.case == "any" else 0
    return re.compile("".join(chunks), flags)


def _field_issue(scheme: DrawingNumbering, f: NumberingField, value: str) -> FieldIssue | None:
    if f.length_min and len(value) < f.length_min:
        return FieldIssue("numbering_field_invalid", f.code, value)
    if f.length_max and len(value) > f.length_max:
        return FieldIssue("numbering_field_invalid", f.code, value)
    if f.pattern and not re.fullmatch(f.pattern, value):
        return FieldIssue("numbering_field_invalid", f.code, value)
    codes = f.codes()
    if codes is not None and value not in codes:
        return FieldIssue("numbering_code_not_in_list", f.code, value)
    if f.code == "number":
        if not value.isdigit():
            return FieldIssue("numbering_field_invalid", f.code, value)
        if f.pad and len(value) < f.pad:
            return FieldIssue("numbering_field_invalid", f.code, value)
    return None


def parse(scheme: DrawingNumbering, code: str) -> dict[str, str] | None:
    """The parts of a VALID number, or ``None``."""
    result = validate(scheme, code)
    return result.parts if result.valid else None


def validate(scheme: DrawingNumbering, code: str) -> Validation:
    """Check a number against the scheme; every issue names its field where one is known."""
    issues: list[FieldIssue] = []
    value = code or ""
    if not value.strip():
        return Validation(False, [FieldIssue("numbering_empty")])
    if len(value) > scheme.max_length:
        issues.append(FieldIssue("numbering_too_long", None, value))
    check_chars = value.upper() if scheme.case == "any" else value
    if not re.fullmatch(scheme.allowed_chars, check_chars):
        if scheme.case == "upper" and re.fullmatch(scheme.allowed_chars, value.upper()):
            issues.append(FieldIssue("numbering_case_invalid", None, value))
        else:
            issues.append(FieldIssue("numbering_chars_invalid", None, value))
    lenient = _build(scheme, lambda f, nxt: _lenient_part(scheme, f, nxt)).fullmatch(value)
    if lenient is None:
        issues.append(FieldIssue("numbering_structure_invalid", None, value))
        _flag_metadata_segments(scheme, value, issues)
        return Validation(False, issues)
    parts = {k: v for k, v in lenient.groupdict().items() if v is not None}
    statuses = _status_codes()
    for f in scheme.fields:
        v = parts.get(f.code)
        if v is None:
            if f.required:
                issues.append(FieldIssue("numbering_field_missing", f.code))
            continue
        problem = _field_issue(scheme, f, v.upper() if scheme.case == "any" else v)
        if problem is not None:
            issues.append(problem)
        # Rule 10: a free field holding a status or revision code is metadata in the name.
        if f.code_list == "free" and f.code != "number" and (v.upper() in statuses or _REVISION.fullmatch(v.upper())):
            issues.append(FieldIssue("numbering_metadata_in_number", f.code, v))
    return Validation(not issues, issues, parts if not issues else None)


def _flag_metadata_segments(scheme: DrawingNumbering, value: str, issues: list[FieldIssue]) -> None:
    statuses = _status_codes()
    for seg in value.split(scheme.separator):
        if seg.upper() in statuses or _REVISION.fullmatch(seg.upper()):
            issues.append(FieldIssue("numbering_metadata_in_number", None, seg))


def container_parts(scheme: DrawingNumbering, parts: dict[str, str]) -> tuple[dict[str, str | None], dict[str, str]]:
    """Split parsed parts into CDE container columns and the extra parts kept in metadata."""
    columns: dict[str, str | None] = {col: parts.get(code) for code, col in CONTAINER_PART.items()}
    extra = {k: v for k, v in parts.items() if k not in CONTAINER_PART}
    return columns, extra


def parts_mismatch(scheme: DrawingNumbering, code: str, stored: dict[str, str | None]) -> list[str]:
    """Rule 7: container columns that disagree with what the code parses into."""
    parts = parse(scheme, code)
    if parts is None:
        return ["number"]
    columns, _extra = container_parts(scheme, parts)
    out = []
    for code_field, col in CONTAINER_PART.items():
        if scheme.field(code_field) is None:
            continue
        want = columns.get(col)
        have = stored.get(col)
        if (want or None) != (have or None):
            out.append(code_field)
    return out


def sequence_of(scheme: DrawingNumbering, code: str) -> int | None:
    """The sequence value of a valid number (rule 8: a typed number moves the counter past it)."""
    parts = parse(scheme, code)
    if parts is None or not parts.get("number", "").isdigit():
        return None
    return int(parts["number"])


def scope_values(parts: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in parts.items() if k != "number"}


__all__ = [
    "FieldIssue",
    "Validation",
    "compose",
    "container_parts",
    "format_number",
    "missing_values",
    "normalise",
    "parse",
    "parts_mismatch",
    "scope_key",
    "scope_values",
    "sequence_of",
    "validate",
]
