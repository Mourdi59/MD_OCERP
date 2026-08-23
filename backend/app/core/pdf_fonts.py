# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unicode font registration for every reportlab-generated PDF.

OpenEstimate principle #2 is *i18n EVERYWHERE*. reportlab's built-in Type-1
fonts (Helvetica / Times / Courier) are Latin-1 only, so any PDF that renders
Cyrillic (ru, bg, uk, sr), Greek, or the many accented Latin scripts with the
default font shows empty boxes ("tofu") instead of text. A construction ERP
that ships 29 locales but prints unreadable invoices and contracts in half of
them is broken.

This module bundles **DejaVu Sans** (regular + bold) and registers it with
reportlab once per process. DejaVu covers Latin, Latin-Extended, Cyrillic and
Greek - i.e. every locale this product ships *except* the complex scripts
(Arabic, Hebrew, CJK, Thai, Devanagari), which need much larger Noto fonts and
proper bidi/shaping. For the covered scripts the fix is complete: glyphs
render, not boxes.

Chinese is handled separately and without bundling anything, because reportlab
ships CID font *metrics* for the Adobe Asian font packs and can reference them
by name. ``pdf_font_for_text`` returns the CID face for text that needs it and
the DejaVu face for everything else, so a Chinese document does not change the
face a German one prints in. The other complex scripts remain a documented
follow-up.

**The CID face is referenced, not embedded.** A PDF using it carries the text
and the metrics but not the outlines, so it renders wherever the reader can
supply an Adobe Simplified Chinese face - which every mainstream desktop and
browser viewer does, and an offline or minimal viewer may not. That is the
trade for not carrying a 16 MB font in the repository, and it is a real
limitation rather than a footnote: a document that must render identically
everywhere needs an embedded font, which is a separate decision with a size
cost attached.

Usage in a generator::

    from app.core.pdf_fonts import BODY_FONT, BOLD_FONT, register_pdf_fonts

    register_pdf_fonts()            # idempotent; call once at the top
    canvas.setFont(BODY_FONT, 10)   # instead of "Helvetica"
    canvas.setFont(BOLD_FONT, 12)   # instead of "Helvetica-Bold"

``register_pdf_fonts()`` is safe to call from many generators and many times;
it registers at most once and never raises if the bundled TTFs are missing
(it falls back to Helvetica and logs a warning, so PDF generation degrades
rather than crashing).
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_FONT_DIR = Path(__file__).resolve().parent / "fonts"

#: Registered font names. When registration succeeds these are the DejaVu
#: faces; if the bundled TTFs are somehow unavailable they fall back to the
#: reportlab built-ins so callers never crash (only lose non-Latin glyphs).
BODY_FONT = "DejaVuSans"
BOLD_FONT = "DejaVuSans-Bold"

_FALLBACK_BODY = "Helvetica"
_FALLBACK_BOLD = "Helvetica-Bold"

# Map the reportlab built-in names every legacy generator hard-codes to the
# Unicode faces, so wiring an existing generator is a one-line swap via
# pdf_font("Helvetica") rather than touching every setFont call by hand.
_HELVETICA_MAP = {
    "Helvetica": BODY_FONT,
    "Helvetica-Bold": BOLD_FONT,
    "Helvetica-Oblique": BODY_FONT,
    "Helvetica-BoldOblique": BOLD_FONT,
}

_lock = Lock()
_registered: bool | None = None  # None = not attempted, True/False = outcome


def register_pdf_fonts() -> bool:
    """Register the bundled DejaVu faces with reportlab. Idempotent.

    Returns ``True`` when the Unicode faces are available (either just
    registered or registered earlier in this process), ``False`` when the
    bundled TTFs could not be loaded and callers should expect the
    Helvetica fallback. Never raises.
    """
    global _registered, BODY_FONT, BOLD_FONT
    if _registered is not None:
        return _registered

    with _lock:
        if _registered is not None:
            return _registered

        try:
            from reportlab.lib.fonts import addMapping
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            regular = _FONT_DIR / "DejaVuSans.ttf"
            bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
            if not regular.is_file() or not bold.is_file():
                raise FileNotFoundError(f"bundled DejaVu TTFs missing in {_FONT_DIR}")

            # The _registered gate guarantees this body runs at most once per
            # process, so a plain registerFont is enough (no need to probe the
            # registry first).
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))

            # Let Paragraph markup (<b>, <i>) resolve to the right face. We only
            # bundle regular + bold, so italic maps onto the upright faces.
            pdfmetrics.registerFontFamily(
                "DejaVuSans",
                normal="DejaVuSans",
                bold="DejaVuSans-Bold",
                italic="DejaVuSans",
                boldItalic="DejaVuSans-Bold",
            )
            addMapping("DejaVuSans", 0, 0, "DejaVuSans")
            addMapping("DejaVuSans", 1, 0, "DejaVuSans-Bold")
            addMapping("DejaVuSans", 0, 1, "DejaVuSans")
            addMapping("DejaVuSans", 1, 1, "DejaVuSans-Bold")

            _registered = True
            logger.debug("PDF fonts: registered DejaVu Sans (regular + bold)")
        except Exception as exc:  # noqa: BLE001 - degrade, never break PDF output
            BODY_FONT = _FALLBACK_BODY
            BOLD_FONT = _FALLBACK_BOLD
            _registered = False
            logger.warning(
                "PDF fonts: could not register DejaVu (%s); falling back to Helvetica - non-Latin text may not render",
                exc,
            )
        return _registered


def pdf_font(name: str, *, bold: bool = False) -> str:
    """Resolve a font name to its Unicode-capable equivalent.

    Accepts a reportlab built-in name (``"Helvetica"`` / ``"Helvetica-Bold"``)
    and returns the registered DejaVu face, or honours an explicit ``bold``
    flag. Registers fonts on first use so callers need not remember to.

    When DejaVu registration failed (bundled TTFs missing) it returns the
    matching reportlab built-in instead, so the caller always gets a name
    reportlab can actually resolve.
    """
    ok = register_pdf_fonts()
    if not ok:
        want_bold = bold or name in ("Helvetica-Bold", "Helvetica-BoldOblique")
        return _FALLBACK_BOLD if want_bold else _FALLBACK_BODY
    if name in _HELVETICA_MAP:
        return _HELVETICA_MAP[name]
    if bold:
        return BOLD_FONT
    return name or BODY_FONT


# -- Chinese ------------------------------------------------------------------

#: The Adobe CID face for Simplified Chinese. reportlab knows its metrics and
#: references it by name, so nothing is bundled and nothing is embedded.
CJK_FONT = "STSong-Light"

_cjk_lock = Lock()
_cjk_registered: bool | None = None

#: Codepoint ranges that DejaVu cannot draw and this face can. Han, the CJK
#: punctuation a Chinese sentence needs (、。《》), and the fullwidth forms.
#: Kana and Hangul are deliberately absent: STSong-Light does not carry them,
#: so claiming them here would swap a face that cannot draw the text for
#: another that also cannot, and hide the gap behind a different set of boxes.
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0x3400, 0x4DBF),  # unified ideographs extension A
    (0x4E00, 0x9FFF),  # unified ideographs
    (0xF900, 0xFAFF),  # compatibility ideographs
    (0xFF00, 0xFFEF),  # halfwidth and fullwidth forms
    (0x20000, 0x3FFFF),  # the supplementary ideographic plane
)


def has_cjk(text: str | None) -> bool:
    """Whether ``text`` contains a character the Latin faces cannot draw."""
    return any(any(low <= ord(ch) <= high for low, high in _CJK_RANGES) for ch in text or "")


def register_cjk_font() -> bool:
    """Register the Simplified Chinese CID face with reportlab. Idempotent.

    Separate from :func:`register_pdf_fonts` and lazy on purpose. It costs
    nothing to skip in a process that never prints Chinese, and it must never
    become the process-wide body face: :data:`BODY_FONT` and :data:`BOLD_FONT`
    are module globals that generators bind at import, so reassigning them for
    one document would change the face of every later German and Russian one in
    the same worker.

    Returns ``True`` when the face is usable, ``False`` when this reportlab
    build cannot provide it. Never raises.
    """
    global _cjk_registered
    if _cjk_registered is not None:
        return _cjk_registered

    with _cjk_lock:
        if _cjk_registered is not None:
            return _cjk_registered
        try:
            from reportlab.lib.fonts import addMapping
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont

            pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))
            # The pack carries one weight. Bold Paragraph markup resolves to
            # the same face rather than to a synthesised one, so a heading is
            # legible and simply not heavier. Mapping it to a Latin bold would
            # be worse: the run would render as boxes.
            pdfmetrics.registerFontFamily(
                CJK_FONT,
                normal=CJK_FONT,
                bold=CJK_FONT,
                italic=CJK_FONT,
                boldItalic=CJK_FONT,
            )
            for bold_flag in (0, 1):
                for italic_flag in (0, 1):
                    addMapping(CJK_FONT, bold_flag, italic_flag, CJK_FONT)
            _cjk_registered = True
            logger.debug("PDF fonts: registered CID face %s (referenced, not embedded)", CJK_FONT)
        except Exception as exc:  # noqa: BLE001 - degrade, never break PDF output
            _cjk_registered = False
            logger.warning(
                "PDF fonts: could not register the CID face %s (%s); Chinese text will not render",
                CJK_FONT,
                exc,
            )
        return _cjk_registered


def pdf_font_for_text(text: str | None, *, bold: bool = False) -> str:
    """Pick the face that can actually draw ``text``.

    Per call, never per process. Chinese text gets the CID face; everything
    else gets the ordinary answer from :func:`pdf_font`, so nothing about a
    Latin or Cyrillic document changes by this function existing.

    ``bold`` is honoured for the Latin faces and ignored for Chinese, which has
    one weight. When the CID face is unavailable the Latin face is returned:
    the text will not render, but reportlab is handed a name it can resolve and
    the document is still produced.
    """
    if has_cjk(text) and register_cjk_font():
        return CJK_FONT
    return pdf_font(BOLD_FONT if bold else BODY_FONT, bold=bold)


# Register eagerly, at import time. Generators capture the face names with
# ``from app.core.pdf_fonts import BODY_FONT, BOLD_FONT``, which snapshots the
# string values at the moment of import. If registration only ran later (inside
# a generator), the Helvetica fallback - implemented by reassigning these module
# globals on failure - would never reach the names those modules already bound,
# so an install with the bundled TTFs missing would hand reportlab the
# unregistered "DejaVuSans" and raise instead of degrading gracefully. Running
# it here finalises BODY_FONT / BOLD_FONT before any importer can read them, and
# the _registered gate keeps every later call a no-op.
register_pdf_fonts()


__all__ = [
    "BODY_FONT",
    "BOLD_FONT",
    "CJK_FONT",
    "has_cjk",
    "pdf_font",
    "pdf_font_for_text",
    "register_cjk_font",
    "register_pdf_fonts",
]
