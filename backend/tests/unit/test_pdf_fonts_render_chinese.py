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
