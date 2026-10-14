# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Which classification code sits under which, without naming a standard.

A cost frame line carries a code of the project's classification standard
(``300`` of DIN 276, ``2.6`` of NRM, ``03 30 00`` of MasterFormat). The bill
and the commitments carry finer codes of the same standard. Whether a fine code
belongs under a frame code is a question about the code's shape, and two shapes
cover every standard the platform resolves:

* dotted codes (``2.6.1``) nest by segment: ``2.6`` covers ``2.6.1`` and not
  ``2.60``;
* run-together digit codes (``330``, ``033000``) nest by significant digits,
  where trailing zeros are padding: ``300`` covers ``3xx``, ``330`` covers
  ``33x``, ``331`` covers only itself.

Anything else (letters, mixed) nests by plain prefix. No function here looks at
the standard's name, so a standard added tomorrow works if it has either shape.
"""

from __future__ import annotations

import re

__all__ = ["covers", "most_specific", "normalise", "overlaps", "truncate"]

_SPACES = re.compile(r"[\s_-]+")


def normalise(code: object) -> str:
    """The code as compared: trimmed, upper-cased, with spaces and dashes removed."""
    if code is None:
        return ""
    return _SPACES.sub("", str(code).strip()).upper()


def _segments(code: str) -> list[str]:
    return [seg.lstrip("0") or "0" for seg in code.split(".") if seg != ""]


def covers(frame_code: object, code: object) -> bool:
    """Does ``frame_code`` cover ``code`` (or equal it)? An empty code is covered by nothing."""
    frame, other = normalise(frame_code), normalise(code)
    if not frame or not other:
        return False
    if "." in frame or "." in other:
        fs, os_ = _segments(frame), _segments(other)
        return len(fs) <= len(os_) and os_[: len(fs)] == fs
    if frame.isdigit() and other.isdigit():
        stem = frame.rstrip("0")
        # An all-zero code is the whole classification.
        return other.startswith(stem) if stem else True
    return other.startswith(frame)


def overlaps(a: object, b: object) -> bool:
    """Do two codes cover one another in either direction (they would count a leaf twice)?"""
    return covers(a, b) or covers(b, a)


def _specificity(code: str) -> int:
    code = normalise(code)
    if "." in code:
        return len(_segments(code))
    return len(code.rstrip("0")) if code.isdigit() else len(code)


def most_specific(frame_codes: list[str], code: object) -> str | None:
    """The frame code covering ``code`` with the most significant digits or segments, if any."""
    found = [f for f in frame_codes if covers(f, code)]
    return max(found, key=_specificity) if found else None


def truncate(code: object, depth: int) -> str:
    """The code cut to ``depth`` segments (dotted) or digits (run-together), padded back for digit codes.

    ``truncate("331", 1) == "300"``, ``truncate("2.6.1", 2) == "2.6"``. A code already shorter than
    ``depth`` comes back unchanged.
    """
    text = normalise(code)
    if depth < 1 or not text:
        return text
    if "." in text:
        return ".".join(text.split(".")[:depth])
    if text.isdigit():
        return text[:depth].ljust(len(text), "0")
    return text[:depth]
