# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The generators ask for the Chinese face, and asking changes nothing else.

An earlier change made the face reachable and wired no generator to it, so
every generated document still printed Chinese as boxes. These tests are about
the documents rather than the helper, and they are written to fail on the
failure mode that a weaker test cannot see: a generator that quietly keeps
using the Latin face still produces a valid PDF and still returns two hundred.

The instrument is the produced bytes. Two facts about them separate a rendered
document from a boxed one, and both were measured before being asserted:

  * With the CID face, the Chinese codepoints survive into the content stream
    as UTF-16BE under the standard Adobe-GB1 CMap, so a reader recovers the
    original characters.
  * With the bundled Latin face, reportlab embeds a DejaVu subset that has no
    Han glyph at all, and every Chinese character is written as glyph zero.
    The text extracted from such a document is a run of NUL characters. That
    is the box, and it is unrecoverable: no reader can undo it.

So "renders Chinese" here means the characters came back and no NUL did. It
does not mean any particular reader owns the outlines - the face is referenced
rather than embedded, deliberately, and :mod:`app.core.pdf_fonts` says so.

Every generator below is checked in both directions. The negative control
disables the switch and asserts the same document then comes out boxed; a test
suite where both directions look alike is measuring the PDF library, not us.
"""

from __future__ import annotations

import io
import types
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pypdf
import pytest

from app.core import pdf_fonts

# Chinese as data, which is what the locale rule permits and what a Chinese
# job actually holds: a project name, a bill section, a measured item, a fee.
CN_PROJECT = "上海办公楼项目"
CN_BOQ = "工程量清单"
CN_SECTION = "土石方工程"
CN_ITEM = "人工挖一般土方，三类土"
CN_MARKUP = "企业管理费"
CN_PERSON = "张伟"
CN_DEVELOPMENT = "浦东锦绣花园"
CN_PLOT = "一期-A12"
CN_SELLER = "上海建工集团股份有限公司"
CN_BUYER = "浦东新区建设发展有限公司"
# The squared metre is the reason the face question cannot be asked about
# scripts. It is not a Chinese character and it appears in Latin bills of
# quantities, but only the Chinese pack draws it.
CN_UNIT = "㎡"

# The control language. Umlauts and the sharp s are the half of this that the
# Chinese face cannot draw, which is why the choice has to stay per string.
DE_PROJECT = "Bürogebäude München"
DE_SECTION = "Erdarbeiten, Größe"
DE_ITEM = "Baugrube ausheben, Bodenklasse 3, Straßenoberfläche"
DE_PERSON = "Jürgen Müller"
DE_DEVELOPMENT = "Wohnpark Grünstraße"
DE_SELLER = "Hochbau Rhein-Main GmbH"
DE_BUYER = "PVG Projektentwicklung Europaviertel GmbH"


# ── Instruments ─────────────────────────────────────────────────────────────


def extracted_text(data: bytes) -> str:
    """All text a reader recovers from the document, whitespace squashed.

    Reportlab breaks a justified line into per-word chunks, so the extracted
    text carries breaks the source string never had. Squashing whitespace
    compares what was written rather than how it was laid out.
    """
    reader = pypdf.PdfReader(io.BytesIO(data))
    return "".join("".join(page.extract_text().split()) for page in reader.pages)


def referenced_faces(data: bytes) -> set[str]:
    """The font faces the document's page resources name."""
    reader = pypdf.PdfReader(io.BytesIO(data))
    faces: set[str] = set()
    for page in reader.pages:
        fonts = page.get("/Resources", {}).get("/Font")
        if not fonts:
            continue
        for ref in fonts.values():
            base = ref.get_object().get("/BaseFont")
            if base:
                # Strip the "AAAAAA+" subset tag reportlab prefixes.
                faces.add(str(base).lstrip("/").split("+")[-1])
    return faces


def assert_renders(data: bytes, *strings: str) -> None:
    """The document draws these strings as glyphs rather than as boxes."""
    assert data.startswith(b"%PDF")
    text = extracted_text(data)
    assert "\x00" not in text, "the document contains glyph-zero runs, which is what a box is"
    for wanted in strings:
        squashed = "".join(wanted.split())
        assert squashed in text, f"{wanted!r} was not recoverable from the produced document"


def assert_boxed(data: bytes, *strings: str) -> None:
    """The negative control: this document prints those strings as boxes."""
    assert data.startswith(b"%PDF")
    text = extracted_text(data)
    assert "\x00" in text, "the control produced no glyph-zero run, so the switch was never consulted"
    for wanted in strings:
        squashed = "".join(wanted.split())
        assert squashed not in text, f"{wanted!r} came back from a document that was supposed to be boxed"


@pytest.fixture
def switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every generator down the Latin path, whatever the text says.

    This is the only honest way to check that a generator's Chinese rendering
    comes from the wiring rather than from something reportlab does anyway.

    It removes the Chinese rung from the face ladder rather than lying about
    what the text contains. That is the switch the product would really have
    thrown - a reportlab build that cannot provide the Adobe pack - and it
    leaves the coverage predicate telling the truth, so what the control proves
    is that the ladder reached that rung and not that a range test fired.
    """
    monkeypatch.setattr(pdf_fonts, "register_cjk_font", lambda: False)


def ns(**kwargs: Any) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kwargs)


# ── The bill of quantities ──────────────────────────────────────────────────


def boq_fixture(*, boq_name: str, section: str, item: str, markup: str) -> Any:
    position = ns(
        ordinal="01.001",
        description=item,
        unit="m3",
        quantity=Decimal("120.00"),
        unit_rate=Decimal("85.50"),
        total=Decimal("10260.00"),
    )
    return ns(
        name=boq_name,
        description="",
        sections=[ns(ordinal="01", description=section, positions=[position], subtotal=Decimal("10260.00"))],
        positions=[],
        markups=[
            ns(
                name=markup,
                markup_type="percentage",
                percentage=8.0,
                amount=Decimal("820.80"),
                category="overhead",
                is_active=True,
            )
        ],
        direct_cost=Decimal("10260.00"),
        net_total=Decimal("11080.80"),
        grand_total=Decimal("11080.80"),
        status="draft",
    )


def build_boq(*, chinese: bool) -> bytes:
    from app.modules.boq.pdf_export import generate_boq_pdf

    if chinese:
        data = boq_fixture(boq_name=CN_BOQ, section=CN_SECTION, item=CN_ITEM, markup=CN_MARKUP)
        return generate_boq_pdf(data, project_name=CN_PROJECT, currency="CNY", prepared_by=CN_PERSON)
    data = boq_fixture(boq_name="Leistungsverzeichnis", section=DE_SECTION, item=DE_ITEM, markup="Gemeinkosten")
    return generate_boq_pdf(data, project_name=DE_PROJECT, currency="EUR", prepared_by=DE_PERSON)


def test_a_chinese_bill_of_quantities_renders_its_chinese() -> None:
    """The cover, the running header, the section, the measured item and the
    fee name - the five places a Chinese estimator reads first."""
    data = build_boq(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, CN_PROJECT, CN_BOQ, CN_SECTION, CN_ITEM, CN_MARKUP, CN_PERSON)


def test_a_chinese_bill_of_quantities_is_boxed_without_the_wiring(switch_off: None) -> None:
    """The negative control. Same generator, same data, switch forced off."""
    data = build_boq(chinese=True)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_boxed(data, CN_PROJECT, CN_SECTION, CN_ITEM, CN_MARKUP)


def test_a_german_bill_built_after_a_chinese_one_is_unaffected() -> None:
    """The regression the per-document design exists to prevent.

    The face names are module globals that every generator binds at import.
    A choice written into them would re-face every later document in the same
    worker, which no test that builds one document can see. So this builds two,
    Chinese first, and asserts the second is exactly what it would have been.
    """
    build_boq(chinese=True)
    data = build_boq(chinese=False)

    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_renders(data, DE_PROJECT, DE_SECTION, DE_ITEM, DE_PERSON)


def test_the_module_face_names_survive_a_chinese_document() -> None:
    """The same property read at the source rather than through a document."""
    before = (pdf_fonts.BODY_FONT, pdf_fonts.BOLD_FONT)
    build_boq(chinese=True)
    assert before == (pdf_fonts.BODY_FONT, pdf_fonts.BOLD_FONT)


def test_the_chinese_bill_does_not_embed_a_font_for_the_chinese() -> None:
    """The face is referenced, not embedded, and that is a deliberate trade.

    If someone later embeds a CJK font this fails, and the decision gets made
    rather than discovered in a repository size.
    """
    data = build_boq(chinese=True)
    reader = pypdf.PdfReader(io.BytesIO(data))
    for page in reader.pages:
        for ref in (page.get("/Resources", {}).get("/Font") or {}).values():
            font = ref.get_object()
            if pdf_fonts.CJK_FONT in str(font.get("/BaseFont", "")):
                descendants = font.get("/DescendantFonts")
                descriptor = descendants[0].get_object().get("/FontDescriptor") if descendants else None
                assert descriptor is None or not any(key.startswith("/FontFile") for key in descriptor.get_object()), (
                    "the Chinese face is now embedded, which changes what ships"
                )


# ── Tender decision letters ─────────────────────────────────────────────────


def build_award_letter(*, chinese: bool) -> bytes:
    from app.modules.tendering.pdf_documents import generate_award_letter_pdf

    if chinese:
        return generate_award_letter_pdf(
            package_name=CN_SECTION,
            package_ref=CN_BOQ,
            project_name=CN_PROJECT,
            company_name="上海建工集团股份有限公司",
            contact_email="info@datadrivenconstruction.io",
            awarded_amount="1234567.89",
            currency="CNY",
            awarded_by_name=CN_PERSON,
            notes=CN_ITEM,
        )
    return generate_award_letter_pdf(
        package_name=DE_SECTION,
        package_ref="LV-2026-01",
        project_name=DE_PROJECT,
        company_name="Müller Hochbau GmbH",
        contact_email="info@datadrivenconstruction.io",
        awarded_amount="1234567.89",
        currency="EUR",
        awarded_by_name=DE_PERSON,
        notes=DE_ITEM,
    )


def test_a_chinese_award_letter_renders_its_chinese() -> None:
    data = build_award_letter(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, "上海建工集团股份有限公司", CN_PROJECT, CN_ITEM, CN_PERSON)


def test_a_chinese_award_letter_is_boxed_without_the_wiring(switch_off: None) -> None:
    data = build_award_letter(chinese=True)
    assert_boxed(data, "上海建工集团股份有限公司", CN_PROJECT, CN_ITEM)


def test_a_german_award_letter_built_after_a_chinese_one_is_unaffected() -> None:
    build_award_letter(chinese=True)
    data = build_award_letter(chinese=False)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_renders(data, "Müller Hochbau GmbH", DE_PROJECT, DE_PERSON)


# ── Meeting minutes ─────────────────────────────────────────────────────────


def build_minutes(*, chinese: bool) -> bytes:
    from app.modules.meetings.pdf import build_minutes_pdf

    if chinese:
        content = {
            "title": "第一次工地例会",
            "meeting_date": "2026-08-23",
            "location": "上海市浦东新区",
            "meeting_type": "site_meeting",
            "meeting_number": "001",
            "chairperson": CN_PERSON,
            "attendees_present": [{"name": CN_PERSON}, {"name": "李娜"}],
            "agenda": [{"number": "1", "topic": CN_SECTION, "discussion": CN_ITEM, "decision": "同意按图施工"}],
            "action_items": [{"description": CN_ITEM, "owner": "李娜", "due_date": "2026-09-01", "status": "open"}],
            "summary": "本次会议确认了土方工程的开工时间。",
        }
        project = CN_PROJECT
    else:
        content = {
            "title": "Erste Baubesprechung",
            "meeting_date": "2026-08-23",
            "location": "München, Größenweg 4",
            "meeting_type": "site_meeting",
            "meeting_number": "001",
            "chairperson": DE_PERSON,
            "attendees_present": [{"name": DE_PERSON}],
            "agenda": [{"number": "1", "topic": DE_SECTION, "discussion": DE_ITEM, "decision": "Freigabe erteilt"}],
            "action_items": [{"description": DE_ITEM, "owner": DE_PERSON, "due_date": "2026-09-01", "status": "open"}],
            "summary": "Der Aushub beginnt am Montag.",
        }
        project = DE_PROJECT

    meeting = ns(title=content["title"], meeting_number="001", meeting_date="2026-08-23")
    minutes = ns(content=content, status="issued", issued_at=datetime.now(tz=UTC))
    return build_minutes_pdf(meeting, minutes, project)


def test_chinese_meeting_minutes_render_their_chinese() -> None:
    """The action-item owner and the location live in bare table cells, which
    a per-paragraph choice cannot reach. They are asserted for that reason."""
    data = build_minutes(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, CN_PROJECT, "第一次工地例会", "上海市浦东新区", "李娜", CN_ITEM)


def test_chinese_meeting_minutes_are_boxed_without_the_wiring(switch_off: None) -> None:
    data = build_minutes(chinese=True)
    assert_boxed(data, "第一次工地例会", "上海市浦东新区", "李娜")


def test_german_meeting_minutes_built_after_chinese_ones_are_unaffected() -> None:
    build_minutes(chinese=True)
    data = build_minutes(chinese=False)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_renders(data, DE_PROJECT, "Erste Baubesprechung", "München, Größenweg 4", DE_PERSON)


# ── The punch list ──────────────────────────────────────────────────────────


# Canonical lowercase hyphenated form, which is what ``str()`` of the real
# ``uuid.UUID`` the route parses produces. The builder only interpolates it, so
# this renders the same characters the product renders.
PROJECT_ID = "11111111-1111-1111-1111-111111111111"
ASSIGNEE_ID = "6f1d2c3b-0000-4000-8000-000000000001"


def build_punchlist(*, chinese: bool) -> bytes:
    from app.modules.punchlist.service import _build_reportlab_pdf

    if chinese:
        item = ns(
            title="外墙渗漏",
            description="三层北侧外墙存在渗漏，需重新做防水层。",
            status="open",
            priority="high",
            category="防水",
            trade="土建",
            due_date=date(2026, 9, 1),
            photos=[],
            resolution_notes="已安排班组返工。",
            reopen_history=[],
            metadata_={"code": "PL-001"},
            location_x=None,
            location_y=None,
            document_id=None,
            page=None,
            assigned_to="李强",
        )
    else:
        item = ns(
            title="Feuchte Außenwand",
            description="Nordseite im dritten Obergeschoss, Abdichtung erneuern.",
            status="open",
            priority="high",
            category="Abdichtung",
            trade="Rohbau",
            due_date=date(2026, 9, 1),
            photos=[],
            resolution_notes="Nacharbeit beauftragt.",
            reopen_history=[],
            metadata_={"code": "PL-001"},
            location_x=None,
            location_y=None,
            document_id=None,
            page=None,
            assigned_to="Jürgen Müller",
        )
    # ``assigned_to`` is a free-text column and ``_party_label`` prints
    # ``names.get(raw) or raw``, so the printed assignee reaches the page by
    # two different routes in production: the assignment control writes a user
    # id and the name arrives in the resolved-names map, while the seeder and
    # the field integrations sometimes write the name straight into the
    # column. The Chinese fixture drives the map route, which is the one that
    # would hide a fault, and the German one drives the stored-name route.
    if chinese:
        item.assigned_to = ASSIGNEE_ID
        return _build_reportlab_pdf(PROJECT_ID, [item], {ASSIGNEE_ID: "李强"})
    return _build_reportlab_pdf(PROJECT_ID, [item], {})


def test_a_chinese_punch_list_renders_its_chinese() -> None:
    """The category and the trade are bare table cells governed by a FONT
    command, so this is the case a paragraph-only wiring would miss."""
    data = build_punchlist(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, "外墙渗漏", "防水", "土建", "李强", "已安排班组返工。")


def test_a_chinese_punch_list_is_boxed_without_the_wiring(switch_off: None) -> None:
    data = build_punchlist(chinese=True)
    assert_boxed(data, "外墙渗漏", "防水", "土建", "李强")


def test_a_german_punch_list_built_after_a_chinese_one_is_unaffected() -> None:
    build_punchlist(chinese=True)
    data = build_punchlist(chinese=False)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_renders(data, "Feuchte Außenwand", "Abdichtung", "Nacharbeit beauftragt.")


# ── The report exporter ─────────────────────────────────────────────────────


def build_report(*, chinese: bool) -> bytes:
    # ``Report.generated_at`` is a String(40) column, not a datetime, and
    # ``export_report`` forwards it to the builder untouched. The builder
    # interpolates it into a paragraph, so handing it a datetime here would
    # print a different timestamp than the product ever prints.
    from app.modules.reporting.exporters import _export_pdf

    generated_at = "2026-08-23T09:15:00+00:00"
    if chinese:
        return _export_pdf(
            title="工程量清单汇总表",
            project_name=CN_PROJECT,
            report_type="boq_summary",
            currency="CNY",
            generated_at=generated_at,
            template_data={},
            data_snapshot={"summary": {"分部工程": CN_SECTION, "清单项目": CN_ITEM}},
        )
    return _export_pdf(
        title="Kostenübersicht",
        project_name=DE_PROJECT,
        report_type="boq_summary",
        currency="EUR",
        generated_at=generated_at,
        template_data={},
        data_snapshot={"summary": {"Gewerk": DE_SECTION, "Position": DE_ITEM}},
    )


def test_a_chinese_report_renders_its_chinese() -> None:
    data = build_report(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, "工程量清单汇总表", CN_PROJECT, CN_SECTION, CN_ITEM)


def test_a_chinese_report_is_boxed_without_the_wiring(switch_off: None) -> None:
    data = build_report(chinese=True)
    assert_boxed(data, "工程量清单汇总表", CN_PROJECT, CN_SECTION)


def test_a_german_report_built_after_a_chinese_one_is_unaffected() -> None:
    build_report(chinese=True)
    data = build_report(chinese=False)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_renders(data, "Kostenübersicht", DE_PROJECT, DE_SECTION, DE_ITEM)


# ── The property reservation receipt ────────────────────────────────────────
#
# This one is worth its own section. The template chrome follows a locale, but
# the receipt ships no Chinese translation, so a Chinese job produces English
# chrome around Chinese names. A document-level switch keyed on the locale
# would face the wrong half of it; this checks the per-string choice instead.


def build_receipt(*, chinese: bool) -> bytes:
    from app.modules.property_dev.document_templates import render_reservation_receipt_pdf

    if chinese:
        return render_reservation_receipt_pdf(
            {
                "reservation_number": "RES-CN-001",
                "currency": "CNY",
                "deposit_amount": Decimal("120000"),
                "cooling_off_days": 14,
            },
            {"plot_number": CN_PLOT, "area_m2": 118, "currency": "CNY"},
            {"name": CN_DEVELOPMENT},
            [{"full_name": CN_PERSON, "email": "buyer@example.cn"}],
            locale="zh",
        )
    return render_reservation_receipt_pdf(
        {
            "reservation_number": "RES-DE-001",
            "currency": "EUR",
            "deposit_amount": Decimal("25000"),
            "cooling_off_days": 14,
        },
        {"plot_number": "WE-07", "area_m2": 96, "currency": "EUR"},
        {"name": DE_DEVELOPMENT},
        [{"full_name": DE_PERSON, "email": "buyer@example.de"}],
        locale="de",
    )


def test_a_chinese_reservation_receipt_renders_its_chinese() -> None:
    data = build_receipt(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, CN_DEVELOPMENT, CN_PERSON, CN_PLOT)


def test_a_chinese_reservation_receipt_is_boxed_without_the_wiring(switch_off: None) -> None:
    data = build_receipt(chinese=True)
    assert_boxed(data, CN_DEVELOPMENT, CN_PERSON)


def test_a_german_reservation_receipt_built_after_a_chinese_one_is_unaffected() -> None:
    build_receipt(chinese=True)
    data = build_receipt(chinese=False)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data)
    assert_renders(data, DE_DEVELOPMENT, DE_PERSON)


def test_the_receipt_style_table_is_not_refaced_by_a_chinese_document() -> None:
    """The styles are built per render, so prove the factory still hands out Latin.

    This is the trap the per-document approach would have fallen into: face the
    style table for a Chinese document and every later document served from the
    same table comes out Chinese-faced.
    """
    from app.modules.property_dev.document_templates import _styles

    build_receipt(chinese=True)
    for name, style in _styles("de").items():
        assert style.fontName != pdf_fonts.CJK_FONT, f"the {name} style kept the Chinese face"


# ── The hybrid e-invoice ────────────────────────────────────────────────────
#
# This one is drawn straight onto a canvas at fixed millimetre offsets, with no
# tables and no paragraphs, and it was left on Helvetica when the rest were
# converted. It is also the document with the strictest requirement attached:
# every invoice this product has ever issued is Latin, and none of their bytes
# may move. So the face is chosen per string and only when Helvetica cannot
# draw that string, which the first test below holds to byte equality.


def invoice_payload(*, seller: str, buyer: str, description: str, unit: str) -> dict[str, Any]:
    return {
        "invoice_number": "AR-2026-014",
        "invoice_direction": "receivable",
        "invoice_date": "2026-04-15",
        "due_date": "2026-05-15",
        "currency_code": "EUR",
        "amount_subtotal": Decimal("1850000.00"),
        "tax_amount": Decimal("351500.00"),
        "retention_amount": Decimal("0"),
        "amount_total": Decimal("2201500.00"),
        "notes": None,
        "metadata": {
            "einvoice": {
                "vat_rate": "19",
                "buyer_reference": "06-4300251-83",
                "payee_iban": "DE89370400440532013000",
                "payee_account_name": seller,
                "seller": {
                    "name": seller,
                    "vat_id": "DE812345678",
                    "city": "Frankfurt am Main",
                    "postcode": "60327",
                    "country_code": "DE",
                },
                "buyer": {
                    "name": buyer,
                    "city": "Frankfurt am Main",
                    "postcode": "60308",
                    "country_code": "DE",
                },
            }
        },
        "_lines": [
            {
                "description": description,
                "unit": unit,
                "quantity": Decimal("1"),
                "unit_rate": Decimal("1850000.00"),
                "amount": Decimal("1850000.00"),
            }
        ],
    }


def build_invoice_page(*, chinese: bool) -> bytes:
    """The readable page only, which is the part a face can change.

    Deliberately not the hybrid: ``build_facturx_pdf`` runs the page through
    pypdf to attach the CII, and comparing that output would be comparing
    pypdf's serialiser as much as our drawing.
    """
    from app.modules.einvoice import build_einvoice
    from app.modules.einvoice.pdf_embed import _readable_pdf

    payload = (
        invoice_payload(seller=CN_SELLER, buyer=CN_BUYER, description=CN_ITEM, unit=CN_UNIT)
        if chinese
        else invoice_payload(seller=DE_SELLER, buyer=DE_BUYER, description=DE_ITEM, unit="psch")
    )
    lines = payload.pop("_lines")
    return _readable_pdf(build_einvoice(invoice=payload, line_items=lines, profile="zugferd"), "de")


def test_a_latin_invoice_is_byte_for_byte_what_it_was_before_the_wiring() -> None:
    """The whole point of choosing the face per string rather than per document.

    reportlab writes a Tf operator for every setFont call whether or not the
    font changed, and the Latin and Chinese faces do not share a width table,
    so a generator that selected a face unconditionally would move the bytes of
    every invoice already issued. This asserts the opposite directly: the page
    produced today is identical to the page produced by the builder as it stood
    before any of this, down to the byte.

    The comparison runs against the real previous implementation, read out of
    git rather than reimplemented here, so it cannot pass by agreeing with a
    copy of itself. reportlab's invariant mode fixes the creation date and the
    document identifier, which are the only bytes that would otherwise differ
    for reasons that have nothing to do with fonts.
    """
    import subprocess

    import reportlab.rl_config as rl_config

    from app.modules.einvoice import build_einvoice
    from app.modules.einvoice.pdf_embed import _readable_pdf

    source = subprocess.run(
        ["git", "show", "HEAD:backend/app/modules/einvoice/pdf_embed.py"],
        capture_output=True,
        cwd=Path(__file__).resolve().parents[3],
        check=True,
    ).stdout.decode("utf-8")
    if "def put(" in source:
        pytest.skip("HEAD already carries the wiring, so there is no earlier builder to compare against")

    module = types.ModuleType("pdf_embed_before")
    module.__file__ = "pdf_embed_before.py"
    exec(compile(source, "pdf_embed_before.py", "exec"), module.__dict__)  # noqa: S102

    previous = rl_config.invariant
    rl_config.invariant = 1
    try:
        payload = invoice_payload(seller=DE_SELLER, buyer=DE_BUYER, description=DE_ITEM, unit="psch")
        lines = payload.pop("_lines")
        for locale in ("de", "en"):
            invoice = build_einvoice(invoice=payload, line_items=lines, profile="zugferd")
            was = module._readable_pdf(invoice, locale)
            now = _readable_pdf(invoice, locale)
            assert was == now, f"the {locale} Latin invoice page changed, and it was not supposed to"

        # The control: this comparison can tell two pages apart at all.
        chinese = invoice_payload(seller=CN_SELLER, buyer=CN_BUYER, description=CN_ITEM, unit=CN_UNIT)
        chinese_lines = chinese.pop("_lines")
        other = _readable_pdf(build_einvoice(invoice=chinese, line_items=chinese_lines, profile="zugferd"), "de")
        assert other != now, "a Chinese invoice produced the same bytes as a German one, so nothing is being compared"
    finally:
        rl_config.invariant = previous


def test_a_chinese_invoice_renders_its_chinese() -> None:
    data = build_invoice_page(chinese=True)
    assert pdf_fonts.CJK_FONT in referenced_faces(data)
    assert_renders(data, CN_SELLER, CN_BUYER, CN_ITEM)


def test_a_chinese_invoice_is_boxed_without_the_wiring(switch_off: None) -> None:
    assert_boxed(build_invoice_page(chinese=True), CN_SELLER, CN_BUYER, CN_ITEM)


def test_a_german_invoice_built_after_a_chinese_one_is_unaffected() -> None:
    """Per document, not once per process, on the generator that draws bare."""
    build_invoice_page(chinese=True)
    data = build_invoice_page(chinese=False)
    assert pdf_fonts.CJK_FONT not in referenced_faces(data), "a German invoice picked up the Chinese face"
    assert_renders(data, DE_SELLER, DE_BUYER, DE_ITEM)


def test_the_invoice_keeps_helvetica_for_the_strings_helvetica_can_draw() -> None:
    """A Chinese invoice is not a Chinese-faced invoice.

    Every label on the page, the invoice number, the IBAN and every amount are
    still drawn in Helvetica. Only the strings that need it escalate, which is
    what keeps the layout of a mixed invoice where it was.
    """
    faces = referenced_faces(build_invoice_page(chinese=True))
    assert "Helvetica" in faces, "the Chinese invoice moved its Latin text off Helvetica"
    assert pdf_fonts.CJK_FONT in faces


def test_the_invoice_does_not_embed_a_font_for_the_chinese() -> None:
    """Referenced rather than embedded, asserted on the shipped hybrid file."""
    from app.modules.einvoice import build_einvoice
    from app.modules.einvoice.pdf_embed import build_facturx_pdf

    payload = invoice_payload(seller=CN_SELLER, buyer=CN_BUYER, description=CN_ITEM, unit=CN_UNIT)
    lines = payload.pop("_lines")
    data = build_facturx_pdf(build_einvoice(invoice=payload, line_items=lines, profile="zugferd"), locale="de")
    for marker in (b"/FontFile", b"/FontFile2", b"/FontFile3"):
        assert marker not in data, f"{marker.decode()} appeared, so a font program is now being shipped"


def test_the_invoice_still_carries_its_machine_readable_half() -> None:
    """The face work must not disturb what the receiver's software reads."""
    from app.modules.einvoice import build_einvoice
    from app.modules.einvoice.pdf_embed import build_facturx_pdf

    payload = invoice_payload(seller=CN_SELLER, buyer=CN_BUYER, description=CN_ITEM, unit=CN_UNIT)
    lines = payload.pop("_lines")
    data = build_facturx_pdf(build_einvoice(invoice=payload, line_items=lines, profile="zugferd"), locale="de")
    assert b"<rsm:CrossIndustryInvoice" in data, "the embedded CII is gone"
    assert b"urn:factur-x:pdfa" in data, "the Factur-X XMP is gone"
    assert b"/AFRelationship" in data, "the associated-file relationship is gone"


# ── One document, two scripts ───────────────────────────────────────────────


def test_a_german_document_carrying_one_chinese_name_renders_both() -> None:
    """Why the choice is per string and not per document.

    Neither face covers both scripts. DejaVu has no Han at all. The Adobe
    Simplified Chinese pack does carry part of the accented Latin range - the
    u-umlaut among it, which an earlier version of this docstring denied - but
    it stops short of the o-umlaut, the sharp s and the euro sign, all three of
    which appear in an ordinary German invoice. So a bill written in German for
    a Chinese subcontractor has to draw each string with the face that can draw
    it, and a document-level switch would sacrifice one of them whichever way
    it fell.
    """
    from app.modules.boq.pdf_export import generate_boq_pdf

    data = generate_boq_pdf(
        boq_fixture(boq_name="Leistungsverzeichnis", section=DE_SECTION, item=CN_ITEM, markup="Gemeinkosten"),
        project_name=DE_PROJECT,
        currency="EUR",
        prepared_by=DE_PERSON,
    )
    faces = referenced_faces(data)
    assert pdf_fonts.CJK_FONT in faces, "the Chinese item did not reach the Chinese face"
    assert pdf_fonts.BODY_FONT in faces, "the German text lost the face that can draw it"
    assert_renders(data, DE_SECTION, CN_ITEM, DE_PROJECT, DE_PERSON)
