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

A generator that can be handed Chinese - which in this product means any
generator that prints project names, item descriptions or party names, because
that is where Chinese arrives - asks for the face per string instead::

    from app.core.pdf_fonts import pdf_font_for_text, pdf_style_for_text, pdf_table_font_commands

    canvas.setFont(pdf_font_for_text(title, bold=True), 12)
    Paragraph(html.escape(desc), pdf_style_for_text(styles["cell"], desc))
    table.setStyle(TableStyle([*base_commands, *pdf_table_font_commands(rows)]))

Per string rather than per document on purpose. The faces cover different
scripts and none covers all of them, so a document mixing a Chinese supplier
name into German text renders correctly only if the choice is made at the string
that is being drawn.

The choice is made by asking the font, not by testing the codepoint against a
range. ``font_can_draw`` reads the TrueType character map, or a Type-1 built-in's
own encoding vector, and reports whether that face has a glyph. A string is then
given the lowest face on a ladder - the generator's existing face, then the
bundled Unicode face, then the Chinese pack - that can draw every character in
it. Two things follow, and both matter more than the tidiness. A string the old
face could already draw never leaves the first rung, so wiring a generator up
does not move a single byte of its existing Latin output. And a string the old
face could not draw escalates whatever the reason: Cyrillic and Greek get the
same treatment as Han, which a range test named for one script would never have
given them.

Known limitation, right-to-left scripts. Arabic and Hebrew escalate to the
bundled Unicode face like any other script this module cannot draw in the base
face, and that face has the glyphs, so the correct codepoints reach the content
stream and a reader can select and copy the text. What this module does not do
is lay them out. There is no bidirectional reordering and no contextual
shaping, so Arabic letters are drawn in their isolated forms rather than joined
to their neighbours, and both scripts are drawn in logical order rather than
visual order. On the page that reads backwards. The choice is deliberate: boxes
destroy the codepoints and cannot be recovered by anything downstream, whereas
this keeps the data correct and gets the presentation wrong, which is the
better failure on a document whose text has to be verifiable against the
structured data beside it. It is still wrong, and implementing bidi and shaping
is the fix.

``register_pdf_fonts()`` is safe to call from many generators and many times;
it registers at most once and never raises if the bundled TTFs are missing
(it falls back to Helvetica and logs a warning, so PDF generation degrades
rather than crashing).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import Any

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

#: Ideographic codepoint ranges, for :func:`has_cjk` only. This is a statement
#: about scripts, not about any font, and nothing on the face-selection path
#: reads it: see :func:`font_can_draw`, which asks the face.
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0x3400, 0x4DBF),  # unified ideographs extension A
    (0x4E00, 0x9FFF),  # unified ideographs
    (0xF900, 0xFAFF),  # compatibility ideographs
    (0xFF00, 0xFFEF),  # halfwidth and fullwidth forms
    (0x20000, 0x3FFFF),  # the supplementary ideographic plane
)


def has_cjk(text: str | None) -> bool:
    """Whether ``text`` contains a character inside the CID pack's declared ranges.

    Kept for callers that want to ask about scripts rather than about faces.
    It is **not** the face-selection predicate: a range test cannot tell you
    whether a given face has a given glyph, and it answers ``False`` for plenty
    of characters Helvetica cannot draw (Cyrillic, Greek, several accented Latin
    forms). Selection goes through :func:`font_can_draw`, which asks the font.
    """
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


# -- Coverage: ask the font, do not assume from a range -----------------------

#: Answers to "can this face draw this character", keyed by face name and
#: codepoint. The alphabet a document draws is small and fixed in practice - a
#: few hundred distinct characters across a whole run - so this saturates almost
#: immediately and every later question is a dict hit. Never holds an entry for
#: an unregistered face: see :func:`font_can_draw`.
_coverage: dict[tuple[str, int], bool] = {}
_coverage_lock = Lock()

#: reportlab's single-byte encodings, and the Python codec that decides what
#: fits in them. A Type-1 built-in can only draw what its encoding can address.
_ENCODING_CODECS = {
    "WinAnsiEncoding": "cp1252",
    "MacRomanEncoding": "mac_roman",
    "PDFDocEncoding": "cp1252",
}

#: Faces that are already bold, so escalating from one keeps the weight.
_BOLD_FACES = frozenset({"Helvetica-Bold", "Helvetica-BoldOblique", "Times-Bold", "Courier-Bold", BOLD_FONT})


def _encodable(char: str, codec: str) -> bool:
    try:
        char.encode(codec)
    except UnicodeEncodeError:
        return False
    return True


def _cid_pack_covers(char: str) -> bool:
    """Whether the Adobe Simplified Chinese pack carries ``char``.

    This is the one face in the module that cannot be asked directly: reportlab
    holds no CMap and no glyph widths for the Adobe packs, because it names a
    standard CMap and leaves the mapping to the reader. So the question is put
    to the pack's *repertoire* instead, via the two encodings that define it.

    GBK is the character set the Simplified Chinese pack is built around, and
    Python ships the table. It is a far better answer than a hand-written range
    list, which is what stood here before and got two things wrong that matter:
    it missed the squared and cubed metre signs and the degree sign, which are
    ordinary units in a bill of quantities, and it claimed kana were absent when
    the repertoire has carried them since GB 2312.

    The Windows Latin set is unioned in because the pack carries proportional
    roman alongside the ideographs. Without it a mixed string - "规费 (Statutory
    charges)", or a German street next to a Chinese company name - would fail
    every rung and lose its ideographs in order to keep its ASCII.

    Neither encoding reaches Hangul, Thai, Arabic, Hebrew or Devanagari, which
    is correct: this pack does not draw them, and answering ``True`` would swap
    one set of boxes for another while looking like a fix.
    """
    return _encodable(char, "gbk") or _encodable(char, "cp1252")


def _single_byte_encoding_covers(font: Any, char: str) -> bool:
    """Whether a Type-1 built-in's encoding can address ``char``, per its own vector."""
    codec = _ENCODING_CODECS.get(getattr(font, "encName", "") or "")
    if codec is None:
        # An encoding we have no codec for. Claim only ASCII, which every
        # reportlab built-in encoding agrees on.
        return ord(char) < 128
    try:
        code = char.encode(codec)
    except UnicodeEncodeError:
        return False
    vector = getattr(getattr(font, "encoding", None), "vector", None)
    if not vector:
        return True
    index = code[0]
    if index >= len(vector):
        return False
    glyph = vector[index]
    return bool(glyph) and glyph != ".notdef"


def font_can_draw(font_name: str, char: str) -> bool:
    """Whether ``font_name`` has a glyph for ``char``, asked of the font itself.

    Three kinds of face answer three different ways, which is why this exists
    rather than a codepoint range:

    * A TrueType face (DejaVu) carries ``charToGlyph``. A missing character is
      absent from it, or maps to glyph 0, which is ``.notdef`` - the box.
    * A Type-1 built-in (Helvetica) carries a single-byte encoding. It can draw
      exactly what that encoding can address, so the question is whether the
      character encodes and whether the vector slot holds a real glyph name.
    * A CID face (STSong-Light) carries neither in this reportlab build, so it
      answers from :data:`_CJK_RANGES`. That one is a declaration, not a
      measurement, and is documented as such where the table is defined.

    A face reportlab cannot resolve answers ``False`` and the answer is **not**
    cached, because the usual reason is that registration has not run yet and
    caching it would make the miss permanent for the life of the process.
    """
    key = (font_name, ord(char))
    cached = _coverage.get(key)
    if cached is not None:
        return cached

    if font_name == CJK_FONT:
        answer = _cid_pack_covers(char)
    else:
        try:
            from reportlab.pdfbase import pdfmetrics

            font = pdfmetrics.getFont(font_name)
        except Exception:  # noqa: BLE001 - an unresolvable face draws nothing
            return False
        char_to_glyph = getattr(getattr(font, "face", None), "charToGlyph", None)
        if char_to_glyph is not None:
            answer = bool(char_to_glyph.get(ord(char)))
        else:
            answer = _single_byte_encoding_covers(font, char)

    with _coverage_lock:
        _coverage[key] = answer
    return answer


def font_can_draw_all(font_name: str, text: str | None) -> bool:
    """Whether ``font_name`` can draw every character in ``text``."""
    return all(font_can_draw(font_name, ch) for ch in text or "")


def _face_ladder(base: str | None, *, bold: bool) -> tuple[list[str], str]:
    """The faces to try in order, and the one to settle for if none of them fits.

    Lowest rung first, so a string keeps the face it would have had unless that
    face cannot draw it. This is what makes the choice free of side effects for
    existing documents: an ASCII string never leaves rung one, so its bytes do
    not move.

    The settle-for face is the bundled Unicode one rather than the first rung,
    because it is a superset: measured across the whole Windows Latin set it
    draws every character Helvetica draws bar the delete control, which no
    document contains. So a string nothing can fully draw still renders as much
    of itself as this product is able to render, instead of being pinned to the
    narrowest face on the ladder because of one character at the end of it.
    """
    want_bold = bold or (base or "") in _BOLD_FACES
    widest = pdf_font(BOLD_FONT if want_bold else BODY_FONT, bold=want_bold)
    rungs: list[str] = []
    if base:
        rungs.append(base)
    if widest not in rungs:
        rungs.append(widest)
    if register_cjk_font():
        rungs.append(CJK_FONT)
    return rungs, widest


def pdf_font_for_text(text: str | None, *, bold: bool = False, base: str | None = None) -> str:
    """Pick the lowest face on the ladder that can draw every character in ``text``.

    Per call, never per process, and per string rather than per document: the
    unit of the decision is the string being drawn, so a Chinese supplier name
    inside a German invoice gets the face it needs without moving anything
    around it.

    ``base`` is where the ladder starts, and it is how a generator keeps its
    existing output byte for byte. Pass the face the generator draws in today
    (``"Helvetica"`` for the legacy ones) and any string that face can already
    draw comes straight back unchanged; only strings it cannot draw escalate.
    Pass the exact face including its weight (``"Helvetica-Bold"``), because the
    first rung is used verbatim; ``bold`` only decides which weight the
    escalation rungs use. Omitting ``base`` starts at the bundled Unicode face,
    which is the right default for a generator that has already been converted.

    ``bold`` is honoured for the Latin faces and ignored for Chinese, which has
    one weight. When no face on the ladder covers the whole string - Hangul and
    Thai are the live examples, since neither the bundled TTF nor the Chinese
    pack carries them - the widest face is returned rather than the narrowest.
    Those characters still will not render, but everything around them does, and
    the gap stays visible instead of being swapped for a different box.
    """
    ladder, widest = _face_ladder(base, bold=bold)
    for face in ladder:
        if font_can_draw_all(face, text):
            return face
    return widest


def pdf_style_for_text(style: Any, text: str | None, *, base: str | None = None) -> Any:
    """Return ``style``, or a clone of it faced for a script its own face cannot draw.

    A ``ParagraphStyle`` carries its face in ``fontName``, so a generator that
    builds its styles once cannot serve a Chinese paragraph from them. Mutating
    the style in place would be the same process-wide trap as reassigning
    :data:`BODY_FONT`, one flowable earlier: the style object outlives the
    document. This returns a fresh clone instead and leaves the original alone,
    so the choice is per paragraph and the caller keeps one style table.

    The ladder starts at the style's own ``fontName`` unless ``base`` overrides
    it, so text that face can already draw gets the original object back -
    unchanged, not copied, and identical by identity, not merely by value.
    Nothing about an existing document changes by routing it through here.

    Args:
        style: A reportlab ``ParagraphStyle`` (or anything with ``clone``).
        text: The string this style is about to render.
        base: Start the ladder at this face instead of the style's own.

    Returns:
        The same style, or a clone of it faced for the string.
    """
    start = base or getattr(style, "fontName", None) or BODY_FONT
    face = pdf_font_for_text(text, base=start)
    if face == start:
        return style
    return style.clone(f"{getattr(style, 'name', 'Style')}-{face}", fontName=face)


def pdf_table_font_commands(
    rows: Sequence[Sequence[Any]],
    *,
    base: str | None = None,
    header_rows: int = 0,
    header_base: str | None = None,
) -> list[tuple[str, tuple[int, int], tuple[int, int], str]]:
    """``FONTNAME`` commands for exactly the table cells their base face cannot draw.

    A bare string in a reportlab table is drawn with the face the ``TableStyle``
    names, so a per-paragraph choice never reaches it: this is where a
    half-wired generator keeps printing boxes while every other assertion
    passes. Append the returned commands after the table's own style and the
    later command wins for those cells only.

    ``base`` is the face those cells are drawn in today. A cell that face can
    already draw produces no command at all, so the table's Latin output is
    untouched and its column widths do not move. Pass what the table actually
    uses, and note that this is rarely one face: a table that names a
    ``FONTNAME`` for its header row and none for its body has a bold Unicode
    header sitting on top of a body that reportlab draws in **Helvetica**,
    because that is what a cell with no ``FONTNAME`` over it falls back to.
    Give the header rows with ``header_rows`` and ``header_base`` so they are
    measured against the face they really have. Getting that wrong is not
    harmless: a header already drawn in a bold Unicode face would otherwise be
    handed a command putting it back to the regular weight.

    Cells holding a flowable (a ``Paragraph``) are skipped, because a flowable
    draws itself with its own style and a ``FONTNAME`` command would not reach
    it anyway. Give those the treatment from :func:`pdf_style_for_text`.

    Bold cells resolve to the same single-weight CJK face, so a Chinese heading
    is legible and simply not heavier. That is the same trade
    :func:`register_cjk_font` documents.

    Args:
        rows: The table's data, row-major, as handed to ``Table``.
        base: The face the table draws its body cells in today.
        header_rows: How many leading rows are drawn in a different face.
        header_base: The face those rows are drawn in; defaults to the bold
            Unicode face, which is what a header ``FONTNAME`` usually names.

    Returns:
        A possibly empty list of ``("FONTNAME", (col, row), (col, row), face)``.
    """
    body_base = base or BODY_FONT
    head_base = header_base or BOLD_FONT
    commands: list[tuple[str, tuple[int, int], tuple[int, int], str]] = []
    for row_index, row in enumerate(rows):
        start = head_base if row_index < header_rows else body_base
        for col_index, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            face = pdf_font_for_text(cell, base=start)
            if face != start:
                commands.append(("FONTNAME", (col_index, row_index), (col_index, row_index), face))
    return commands


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
    "font_can_draw",
    "font_can_draw_all",
    "has_cjk",
    "pdf_font",
    "pdf_font_for_text",
    "pdf_style_for_text",
    "pdf_table_font_commands",
    "register_cjk_font",
    "register_pdf_fonts",
]
