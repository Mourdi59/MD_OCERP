# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""A generated PDF can print Chinese, and printing it changes nothing else.

The bundled DejaVu faces have no Han glyphs at all - not a thin subset, none -
so until now every Chinese string in every generated PDF came out as boxes.
The fix references an Adobe CID face that reportlab already carries metrics
for, which costs no dependency and no bundled megabytes.

Two properties matter and they pull against each other. The face has to be
reachable when the text needs it, and it must not become the face anything
else prints in: ``BODY_FONT`` and ``BOLD_FONT`` are module globals that every
generator binds at import time, so a per-document choice that wrote to them
would change every later German and Russian document in the same worker. The
selection is therefore per call, and the assertions below check both halves.
"""

from __future__ import annotations

import io

import pytest

from app.core import pdf_fonts
from app.core.pdf_fonts import (
    BODY_FONT,
    CJK_FONT,
    has_cjk,
    pdf_font_for_text,
    register_cjk_font,
)

CHINESE = "工程量清单计价"
GERMAN = "Straßenbauarbeiten, Größe"
RUSSIAN = "Строительные работы"


# ── Detection, in both directions ───────────────────────────────────────────


@pytest.mark.parametrize("text", [CHINESE, "综合单价", "措施项目费 (Preliminaries)", "面积：120㎡"])
def test_chinese_text_is_detected(text: str) -> None:
    assert has_cjk(text) is True


@pytest.mark.parametrize("text", [GERMAN, RUSSIAN, "", "Preliminaries 8.0%", "m3", None])
def test_latin_and_cyrillic_text_is_not_detected(text: str | None) -> None:
    """The negative control is the load-bearing half.

    A detector that answered yes to everything would satisfy every assertion
    above and would route every document in the product to a Chinese face.
    """
    assert has_cjk(text) is False


def test_a_mixed_string_is_detected_by_its_chinese_half() -> None:
    """Our own labels are mixed, so this is the realistic case rather than an
    edge one: the regional markup names read ``措施项目费 (Preliminaries)``."""
    assert has_cjk("规费 (Statutory charges)") is True


# ── Registration ────────────────────────────────────────────────────────────


def test_the_cid_face_is_available_from_reportlab_alone() -> None:
    """No bundled TTF, no new dependency, no download at runtime."""
    assert register_cjk_font() is True


def test_registration_is_idempotent() -> None:
    assert register_cjk_font() is True
    assert register_cjk_font() is True


# ── Selection is per call, and leaves the process alone ─────────────────────


def test_chinese_text_selects_the_cid_face() -> None:
    assert pdf_font_for_text(CHINESE) == CJK_FONT


@pytest.mark.parametrize("text", [GERMAN, RUSSIAN, "", None])
def test_other_text_keeps_the_latin_face(text: str | None) -> None:
    assert pdf_font_for_text(text) != CJK_FONT


def test_printing_chinese_does_not_change_the_face_anything_else_prints_in() -> None:
    """The regression this design exists to prevent, asserted as equality.

    ``BODY_FONT`` is read once, at import, by every generator in the product.
    If the Chinese path reassigned it - the way the Helvetica fallback path
    legitimately does - then one Chinese invoice would silently re-face every
    document produced afterwards by the same process.
    """
    body_before, bold_before = pdf_fonts.BODY_FONT, pdf_fonts.BOLD_FONT

    assert pdf_font_for_text(CHINESE) == CJK_FONT

    assert (body_before, bold_before) == (pdf_fonts.BODY_FONT, pdf_fonts.BOLD_FONT)
    assert pdf_font_for_text(GERMAN) == body_before


def test_bold_chinese_is_the_same_face_rather_than_a_latin_bold() -> None:
    """The pack carries one weight. A heading is legible and not heavier;
    falling back to a Latin bold would render the heading as boxes."""
    assert pdf_font_for_text(CHINESE, bold=True) == CJK_FONT


# ── The document itself ─────────────────────────────────────────────────────


def test_a_pdf_containing_chinese_is_produced_and_names_the_face() -> None:
    """The second instrument: the assertions above are about our own helpers,
    and this one is about a file reportlab actually wrote."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont(pdf_font_for_text(CHINESE), 14)
    pdf.drawString(72, 720, CHINESE)
    pdf.save()
    data = buffer.getvalue()

    assert data.startswith(b"%PDF")
    assert b"STSong" in data, "the document does not reference the CID face it was told to use"


def test_the_face_is_referenced_and_not_embedded() -> None:
    """Stated as a test so the caveat cannot quietly stop being true.

    A referenced face keeps the document small and depends on the reader
    supplying the outlines. If someone later embeds a Chinese font, this fails
    and the change gets noticed rather than discovered in a repository size.
    """
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont(pdf_font_for_text(CHINESE), 14)
    pdf.drawString(72, 720, CHINESE * 40)
    pdf.save()
    data = buffer.getvalue()

    assert b"/FontFile" not in data
    assert len(data) < 100_000, f"a referenced CID face should keep this tiny, got {len(data)} bytes"


def test_a_latin_document_is_unaffected_by_the_chinese_path() -> None:
    """Negative control on the document rather than on the helper."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont(pdf_font_for_text(GERMAN), 14)
    pdf.drawString(72, 720, GERMAN)
    pdf.save()
    data = buffer.getvalue()

    assert data.startswith(b"%PDF")
    assert b"STSong" not in data
    assert BODY_FONT.encode() in data or b"Helvetica" in data


# ── Right-to-left scripts: a pinned, known-wrong baseline ───────────────────
#
# Arabic and Hebrew escalate to the bundled Unicode face rather than being left
# to draw as boxes. That is deliberate and it is only half right: the face has
# the glyphs, so the codepoints survive and a reader can select the text, but
# nothing here reorders or shapes them, so the page reads backwards and the
# Arabic is unjoined.
#
# These tests pin what we do today so that whoever implements bidirectional
# reordering and contextual shaping has a baseline that FAILS when they
# succeed. A test that keeps passing through that work would be worthless.

AR_COMPANY = "شركة الإنشاءات المتحدة"
HE_COMPANY = "חברת הבנייה המאוחדת"


def _drawn(text: str) -> str:
    """What a reader recovers from a page that drew ``text`` once."""
    import pypdf
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from app.core.pdf_fonts import pdf_font_for_text

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont(pdf_font_for_text(text, base="Helvetica"), 12)
    pdf.drawString(50, 700, text)
    pdf.showPage()
    pdf.save()
    pages = pypdf.PdfReader(io.BytesIO(buffer.getvalue())).pages
    return "".join(page.extract_text() for page in pages).strip()


@pytest.mark.parametrize(("label", "text"), [("Arabic", AR_COMPANY), ("Hebrew", HE_COMPANY)])
def test_a_right_to_left_name_escalates_instead_of_boxing(label: str, text: str) -> None:
    """The half that is right, and the reason the trade was taken.

    Boxes are unrecoverable: the codepoint is replaced by glyph zero and no
    reader can undo it. Escalating puts the real codepoints in the content
    stream, so the text layer of the document carries the right characters and
    can be checked against the structured data the document also carries.
    """
    assert not pdf_fonts.font_can_draw_all("Helvetica", text), f"{label} no longer needs to escalate"
    assert pdf_fonts.font_can_draw_all(BODY_FONT, text), f"the bundled face lost its {label} glyphs"
    drawn = _drawn(text)
    assert "\x00" not in drawn, f"{label} came out as boxes, which is the failure this avoids"
    assert sorted(drawn) == sorted(text), f"{label} lost or gained codepoints on the way to the page"


@pytest.mark.parametrize(("label", "text"), [("Arabic", AR_COMPANY), ("Hebrew", HE_COMPANY)])
def test_a_right_to_left_name_is_not_reordered_and_this_is_the_bug(label: str, text: str) -> None:
    """The half that is wrong, pinned deliberately.

    No bidirectional algorithm runs, so the characters go down in logical order
    and come back in the reverse of the order they should read on the page.
    This asserts the exact reversal rather than merely "not equal", because a
    partial implementation that reorders some runs and not others would be a
    different state again and should also fail here.

    When bidi and shaping land, this test SHOULD fail. Delete it then, and
    replace it with one asserting the visual order is right.
    """
    assert _drawn(text) == text[::-1], (
        f"{label} no longer comes back exactly reversed. If bidi or shaping was implemented, "
        "this test has done its job and should be replaced with a real layout assertion."
    )
