"""The zero-width gate lets the provenance watermark through, and nothing that merely resembles it.

The watermark is built from characters the gate otherwise reports (U+200B, U+2060).
Only the exact, whole sequence is exempt: a lone character, or the sequence with any
one character changed or missing, is still stray.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("check_zero_width")

ZWSP, ZWNJ, ZWJ, WJ = chr(0x200B), chr(0x200C), chr(0x200D), chr(0x2060)


def _changed(index: int, to: str) -> str:
    chars = list(gate.WATERMARK)
    chars[index] = to
    return "".join(chars)


def test_the_watermark_is_the_documented_signature() -> None:
    assert gate.WATERMARK == (ZWSP + ZWNJ + ZWJ + WJ) * 4


def test_the_whole_watermark_passes() -> None:
    assert gate.stray_in_line(f" * Sheet{gate.WATERMARK} mode wiring") == []


def test_two_whole_watermarks_on_one_line_pass() -> None:
    assert gate.stray_in_line(f"a{gate.WATERMARK}b{gate.WATERMARK}c") == []


@pytest.mark.parametrize(
    "line",
    [
        pytest.param(f"word{ZWSP}word", id="lone-zwsp"),
        pytest.param(f"word{WJ}word", id="lone-wj"),
        pytest.param(_changed(0, ZWNJ), id="first-zwsp-changed"),
        pytest.param(_changed(3, ZWJ), id="first-wj-changed"),
        pytest.param(_changed(15, ZWSP), id="last-char-changed"),
        pytest.param(gate.WATERMARK[:-1], id="one-short"),
        pytest.param(gate.WATERMARK[:4], id="one-quarter"),
        pytest.param(f"{gate.WATERMARK}{ZWSP}", id="whole-plus-stray"),
    ],
)
def test_anything_but_the_whole_watermark_fails(line: str) -> None:
    assert gate.stray_in_line(line) != []


def test_the_scan_reports_a_partial_signature_but_not_a_whole_one(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "whole.ts").write_text(f"// Header{gate.WATERMARK} text\n", encoding="utf-8")
    (root / "partial.ts").write_text(f"// Header{gate.WATERMARK[:-1]} text\n", encoding="utf-8")
    hits, _ = gate.scan(str(tmp_path), ["src"])
    assert {rel for rel, _, _ in hits} == {"src/partial.ts"}


def test_the_stripper_never_cuts_into_a_whole_watermark(tmp_path: Path) -> None:
    sys.path.insert(0, str(_SCRIPTS))
    try:
        stripper = _load("strip_zero_width")
    finally:
        sys.path.remove(str(_SCRIPTS))
    path = tmp_path / "f.ts"
    path.write_text(f"a{gate.WATERMARK}b{ZWSP}c\n", encoding="utf-8")
    stripper.strip_file(str(path), {}, {})
    assert path.read_text(encoding="utf-8") == f"a{gate.WATERMARK}bc\n"
