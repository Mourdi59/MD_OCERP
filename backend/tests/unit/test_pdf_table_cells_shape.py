# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""A bare table cell prints complex script correctly, not merely visibly.

``pdf_table_font_commands`` gives a cell the right face. It cannot give it the
right shape, because reportlab draws a cell that is not a flowable through
``canvas.drawString``, and that call discards its shaping argument unless
``rlbidi`` is installed. So a Thai tone mark in a plain cell drew at the height
of the vowel it belongs above and merged with it, and a Devanagari i-matra drew
after its consonant instead of before: the right characters in the wrong
arrangement, which looks like output and is not.

``pdf_table_shaped_rows`` shapes the text before the table ever sees it, so the
cell holds the glyphs the shaper chose and the draw call has nothing left to do.

Two properties pull against each other here and both are asserted below. The
shaped cells have to actually change what lands on the page, and every other
cell has to be untouched, by identity rather than by comparison. The second is
not a formality: handing Latin to the shaper applies its ligatures, so a version
of this that shaped every cell would rewrite English documents and move their
column widths while appearing to be a Thai fix.
"""

from __future__ import annotations

import io
import re

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from app.core import pdf_fonts
from app.core.pdf_fonts import (
    BODY_FONT,
    BOLD_FONT,
    CJK_FONT,
    DEVANAGARI_FONT,
    KOREAN_FONT,
    THAI_FONT,
    font_can_draw_all,
    pdf_table_font_commands,
    pdf_table_shaped_rows,
    register_complex_font,
)

# Built from codepoints so the file stays readable in any editor and no reviewer
# has to trust that a glyph they cannot render is the one named.
THAI_STACK = "".join(map(chr, (0x0E17, 0x0E35, 0x0E48)))  # to, sara ii, mai tho
THAI_TONE = chr(0x0E48)
DEVANAGARI_REORDER = "".join(map(chr, (0x0915, 0x093F)))  # ka, then the i-matra
KOREAN = "".join(map(chr, (0xC548, 0xB155)))
CHINESE = "".join(map(chr, (0x6DF7, 0x51DD, 0x571F)))

# Every ligature-forming pair DejaVu carries. A control without one of these
# passes for a reason unrelated to what it checks: "Concrete C25/30" cannot
# fail this test no matter how badly the helper behaves.
LATIN_LIGATURES = "five offices affirm the final fixture"
LATIN_PLAIN = "Concrete C25/30 north retaining wall"


def _hand_shaped(text: str, face: str) -> str:
    """What the shaper says the text should be, obtained without the helper.

    Reportlab's own type is kept rather than flattened with ``str``. That type
    is how the helper recognises text it must not shape again, so a test fixture
    that dropped it would hand the helper something no generator ever produces.
    """
    from reportlab.pdfbase.ttfonts import shapeStr

    assert register_complex_font(face), f"the {face} face did not register"
    return shapeStr(text, face, 12)


def _page_literals(pdf_bytes: bytes) -> list[bytes]:
    """Every string literal the page shows, in draw order.

    Streams are selected on looking like a content stream rather than on
    containing ``BT``. An embedded font carries those two bytes inside its glyph
    tables, so a naive search returns a font blob for one script and the real
    page for another, which is indistinguishable from a genuine difference
    between the two scripts.
    """
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.S):
        body = match.group(1)
        if b"\x00" in body or b" Tf" not in body or b" Tj" not in body:
            continue
        return re.findall(rb"\((.*?)\)\s*Tj", body, re.S)
    raise AssertionError("no page content stream was produced")


def _render(rows: object) -> bytes:
    """Build the table the way the generators build it, and return the file."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    doc.pageCompression = 0
    table = Table(rows)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 12),
                *pdf_table_font_commands(rows),
            ]
        )
    )
    doc.build([table])
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("label", "text", "face"),
    [
        ("thai", THAI_STACK, THAI_FONT),
        ("devanagari", DEVANAGARI_REORDER, DEVANAGARI_FONT),
    ],
)
def test_a_cell_that_needs_shaping_comes_back_shaped(label: str, text: str, face: str) -> None:
    """The helper's output is what the shaper asked for, cell by cell."""
    shaped = pdf_table_shaped_rows([[text]])
    assert shaped[0][0] == _hand_shaped(text, face), f"the {label} cell does not match the shaper"
    assert shaped[0][0] != text, f"the {label} cell came back unchanged, so nothing was shaped"


def test_the_thai_tone_mark_is_substituted_rather_than_merely_moved() -> None:
    """Names the actual defect, so a regression cannot pass by changing anything.

    The tone mark above an upper vowel is a different glyph from the one above a
    consonant. If the substitution stops happening, this fails on the character
    rather than on some byte count that could move for any reason.
    """
    shaped = pdf_table_shaped_rows([[THAI_STACK]])[0][0]
    assert THAI_TONE not in shaped, "the unsubstituted tone mark is still in the cell"
    assert len(shaped) == len(THAI_STACK), "the substitution changed the character count"


def test_the_devanagari_vowel_ends_up_in_front_of_its_consonant() -> None:
    """Devanagari stores the i-matra after its consonant and draws it before."""
    shaped = pdf_table_shaped_rows([[DEVANAGARI_REORDER]])[0][0]
    assert shaped[0] != DEVANAGARI_REORDER[0], "the consonant is still drawn first"


def test_the_fix_changes_what_lands_on_the_page() -> None:
    """The measurement that matters: bytes on the page, not a shaped string.

    Both comparisons are made between two rows of one document, never between
    two documents. reportlab hands out subset codes in order of first use, and it
    does that afresh per file, so two documents independently assign codes 1 and
    2 and a pure reorder comes out byte identical while the glyphs differ. One
    document means one subset table and makes the comparison mean what it says.

    Row 0 is the text a generator has today, row 1 is what the shaper says it
    should be. Before the helper runs they draw differently, which is the defect.
    After it runs they draw identically, which is the fix.
    """
    rows = [[THAI_STACK], [_hand_shaped(THAI_STACK, THAI_FONT)]]
    before = _page_literals(_render(rows))
    after = _page_literals(_render(pdf_table_shaped_rows(rows)))
    assert len(before) == len(after) == 2, "the page did not draw one literal per row"
    assert before[0] != before[1], "the unshaped cell already matched the shaper, so nothing was being measured"
    assert after[0] == after[1], "the shaped cell still draws different glyphs from the shaper"


def test_a_latin_table_is_returned_by_identity() -> None:
    """Not equal, the same object. An English document cannot be touched at all."""
    rows = [[LATIN_PLAIN, "42"], ["Status", "Open"]]
    assert pdf_table_shaped_rows(rows) is rows


def test_latin_ligatures_are_never_applied() -> None:
    """The trap this helper has to avoid, pinned with a string that can spring it.

    ``shapeStr`` on the body face turns "five" into a single ligature glyph and
    moves the column width with it. The helper must never reach the shaper for a
    face that does not need shaping, and the string here carries fi, ffi and ff
    so that a helper which did would be caught rather than flattered.
    """
    rows = [[LATIN_LIGATURES]]
    assert pdf_table_shaped_rows(rows) is rows
    assert _page_literals(_render(rows)) == _page_literals(_render(pdf_table_shaped_rows(rows)))


@pytest.mark.parametrize(("label", "text"), [("korean", KOREAN), ("chinese", CHINESE)])
def test_a_script_that_needs_a_face_but_no_shaping_is_left_alone(label: str, text: str) -> None:
    """Korean and Chinese need a face, which the FONTNAME commands already give."""
    rows = [[text]]
    assert pdf_table_shaped_rows(rows) is rows, f"{label} was shaped and it has no shaping to do"


def test_a_flowable_cell_is_left_alone() -> None:
    """A Paragraph shapes itself and never had this problem."""
    cell = Paragraph(THAI_STACK, getSampleStyleSheet()["Normal"])
    rows = [[cell]]
    assert pdf_table_shaped_rows(rows) is rows
    assert rows[0][0] is cell


def test_the_original_rows_are_never_mutated() -> None:
    """The caller's data outlives this call and often the document too."""
    rows = [[THAI_STACK, LATIN_PLAIN]]
    before = [list(row) for row in rows]
    pdf_table_shaped_rows(rows)
    assert [list(row) for row in rows] == before, "the caller's rows were written to in place"


def test_the_untouched_cells_of_a_shaped_row_keep_their_identity() -> None:
    """Only the cell that needed shaping is replaced, not the row around it."""
    latin = LATIN_PLAIN
    shaped = pdf_table_shaped_rows([[THAI_STACK, latin]])
    assert shaped[0][1] is latin


def test_both_helpers_agree_about_the_face() -> None:
    """The two calls resolve the face separately, so they must not disagree.

    The shaped text carries a private-use codepoint that the unshaped text does
    not. If the bundled face did not cover it, the face commands would come back
    different after shaping and the cell would be drawn in a face that cannot
    draw it, which is a worse failure than the one being fixed.
    """
    raw = [[THAI_STACK], [DEVANAGARI_REORDER]]
    shaped = pdf_table_shaped_rows(raw)
    assert pdf_table_font_commands(shaped) == pdf_table_font_commands(raw)


def test_a_header_row_is_shaped_against_the_header_face() -> None:
    """Header rows are drawn in a different face and still need shaping."""
    rows = [[THAI_STACK], [THAI_STACK]]
    shaped = pdf_table_shaped_rows(rows, base="Helvetica", header_rows=1, header_base=BOLD_FONT)
    assert shaped[0][0] != THAI_STACK, "the header cell was left unshaped"
    assert shaped[1][0] != THAI_STACK, "the body cell was left unshaped"


def test_the_helper_registers_the_face_it_shapes_for() -> None:
    """``shapeStr`` reads its own registry and raises if the face is absent.

    The build path registers lazily through ``pdf_font_for_text``, so this only
    bites a caller that shapes before anything resolved that face. Asserting the
    call rather than the absence of an exception keeps the test honest: these
    faces are process-global, so by the time this runs in a full suite another
    test has almost certainly registered them already and a no-exception
    assertion would pass whether or not the helper does its own registering.
    """
    seen: list[str] = []
    real = pdf_fonts.register_complex_font

    def spy(face: str) -> bool:
        seen.append(face)
        return real(face)

    original = pdf_fonts.register_complex_font
    pdf_fonts.register_complex_font = spy  # type: ignore[assignment]
    try:
        pdf_table_shaped_rows([[THAI_STACK]])
    finally:
        pdf_fonts.register_complex_font = original  # type: ignore[assignment]
    assert THAI_FONT in seen, "the helper shaped without asking for the face to be registered"


def test_shaping_does_not_depend_on_the_size_it_is_asked_at() -> None:
    """Pins the assumption the helper's single size constant rests on.

    The generators draw these tables at 7, 8 and 9 point while the helper shapes
    at one fixed size. That is only sound while the shaper's answer is a function
    of the text and the face alone. If a future reportlab makes it depend on
    size, this fails and names the reason, instead of the tables quietly drawing
    glyphs shaped for a size they are not set in.
    """
    from reportlab.pdfbase.ttfonts import shapeStr

    for text, face in ((THAI_STACK, THAI_FONT), (DEVANAGARI_REORDER, DEVANAGARI_FONT)):
        assert register_complex_font(face), f"the {face} face did not register"
        results = {str(shapeStr(text, face, size)) for size in (6, 7, 8, 9, 10, 12, 18, 36)}
        assert len(results) == 1, f"{face} shapes differently at different sizes: {results}"


def test_the_cid_faces_are_not_reached_by_this_helper() -> None:
    """A guard on the boundary rather than on two example strings.

    Korean and Chinese resolve to CID faces that carry one weight and no shaping.
    Asking the shaper about them would be meaningless at best, so the predicate
    the helper gates on has to answer False for both.
    """
    for face in (CJK_FONT, KOREAN_FONT):
        assert not pdf_fonts.font_needs_shaping(face), f"{face} claims to need shaping"


def test_applying_the_helper_twice_changes_nothing() -> None:
    """Idempotent by identity, which is stronger than idempotent by value.

    Returning the same object proves no cell was shaped on the second pass. An
    equality check would also pass if the helper shaped everything again and
    happened to get the same answer, which is exactly what does not happen here.
    """
    once = pdf_table_shaped_rows([[THAI_STACK], [DEVANAGARI_REORDER]])
    twice = pdf_table_shaped_rows(once)
    assert twice is once, "the second pass rebuilt the rows, so something was shaped twice"


def test_shaping_the_same_text_twice_by_hand_destroys_it() -> None:
    """Why the guard above exists, pinned so nobody removes it as belt and braces.

    ``str`` is called deliberately: it drops reportlab's marker and produces the
    unguarded case. Shaping a shaped Thai stack turns the substituted mark into
    U+FFFF, which no face draws, so the cell prints as boxes with nothing raised
    and nothing logged. If a future reportlab makes shaping idempotent this test
    fails, and that is the right outcome, because the guard is then removable.
    """
    from reportlab.pdfbase.ttfonts import shapeStr

    assert register_complex_font(THAI_FONT), "the Thai face did not register"
    once = shapeStr(THAI_STACK, THAI_FONT, 12)
    twice = shapeStr(str(once), THAI_FONT, 12)
    assert str(twice) != str(once), "shaping twice is now idempotent"
    assert font_can_draw_all(THAI_FONT, str(once)), "one pass should leave drawable text"
    assert not font_can_draw_all(THAI_FONT, str(twice)), "double shaping no longer destroys the text"


def test_a_cell_the_helper_shaped_is_not_shaped_again_by_a_later_pass() -> None:
    """The marker travels on the cell, not on the rows structure around it."""
    shaped_cell = pdf_table_shaped_rows([[THAI_STACK]])[0][0]
    rows = [[shaped_cell, THAI_STACK]]
    out = pdf_table_shaped_rows(rows)
    assert out[0][0] is shaped_cell, "the already shaped cell was replaced"
    assert out[0][1] == shaped_cell, "the raw cell beside it was not shaped"
