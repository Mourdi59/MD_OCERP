# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""A table cell longer than its column must not be drawn over the column beside it.

These four documents give their tables explicit column widths, so they always
fitted the page and nothing ever looked wrong about their geometry. What they
also did was hand reportlab bare strings, and a bare string cell is drawn with
``canvas.drawString`` at the column's left edge and simply allowed to run on.
The column width decides where the grid line goes and has no say at all over
where the ink stops. So a certifier's practice name, a site address, an action
item written as a sentence, a subcontractor's name or a trade description would
be printed straight across the column beside it, over whatever that column was
saying, or past the edge of the sheet when it was the last column.

That is invisible to every check that reads the file rather than the page. The
text is all present, extraction returns all of it in the right order, the column
count is right, and the table's own bounding box is the size it was asked to be.
It is only wrong once someone looks at it, which is why the assertions here are
about where ink is drawn and never about which strings the file contains.

Each test names two columns by the text that starts them and asserts that
nothing drawn in the first reaches the second. The boundaries are read off the
page rather than restated from the source, so a change to the column widths
moves the boundary with it and the test keeps asking the same question. Widths
and font sizes are the product's own throughout; nothing here is rendered at a
width chosen to make the arithmetic easy.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pypdf
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth

# The right hand edge of each document's frame, from the page size and the
# margins the generator sets. A run drawn past this is off the printable area.
MINUTES_FRAME_RIGHT = A4[0] - 20 * mm
PUNCHLIST_FRAME_RIGHT = A4[0] - 18 * mm

LONG_CERTIFIER = "Ortega Architects and Associates International Consulting Engineers LLP"
LONG_LOCATION = (
    "Baustelle Nordwest, Bauabschnitt 4, Zufahrt ueber Groessenweg 4, Tor 7, "
    "81829 Muenchen Riem, Bayern, Bundesrepublik Deutschland"
)
LONG_ACTION = (
    "Coordinate the mechanical, electrical and plumbing rough-in with the steel erector "
    "before the third floor deck is poured"
)
# One name, used wherever a document holds a person in a column too narrow
# for it. Nothing about it is unusual except its length.
LONG_PERSON = "Konstantinos Papadopoulos-Michaelides"
LONG_TRADE = "Mechanical, electrical and plumbing rough-in coordination"


@dataclass(frozen=True)
class Run:
    """One piece of text as it was drawn, in page coordinates."""

    text: str
    x0: float
    x1: float
    y: float
    size: float
    face: str


def drawn_runs(pdf_bytes: bytes, page_number: int = 0) -> list[Run]:
    """Every run of text on a page, with the horizontal extent of its ink.

    The width comes from ``stringWidth`` against the face the page itself names,
    which is the same arithmetic reportlab did when it placed the text, so this
    is where the ink ends rather than an estimate of it. The face is read from
    the PDF's own ``/BaseFont`` with the subset prefix removed, so the instrument
    is told which font to measure rather than assuming one.

    A Paragraph carrying inline markup draws each weight as a separate run
    without issuing a new text matrix, so a fragment continuing a line arrives
    carrying the origin of the fragment before it. Those are chained onto the
    end of their predecessor, which is where they are actually drawn. Without
    that, every bold label followed by a value reads as a cell overprinting
    itself.
    """
    page = pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages[page_number]
    found: list[Run] = []
    previous: tuple[tuple[float, float], float] | None = None

    def visit(text: str, cm: list[float], tm: list[float], font_dict: Any, font_size: float) -> None:
        nonlocal previous
        if not text.strip():
            return
        face = str(font_dict.get("/BaseFont", "") if isinstance(font_dict, dict) else "").lstrip("/")
        face = face.split("+", 1)[1] if "+" in face else face
        here = (tm[4] + cm[4], tm[5] + cm[5])
        x0 = previous[1] if previous is not None and previous[0] == here else here[0]
        x1 = x0 + stringWidth("".join(text.splitlines()), face, font_size)
        previous = (here, x1)
        found.append(Run(text.strip(), x0, x1, here[1], font_size, face))

    page.extract_text(visitor_text=visit)
    return found


def column_start(runs: list[Run], label: str) -> float:
    """The x a column begins at, read off the run that draws the given text.

    Matched exactly rather than by prefix, so a heading that happens to begin
    with a column's label cannot quietly become the boundary.
    """
    matches = {round(run.x0, 1) for run in runs if run.text == label}
    assert len(matches) == 1, (
        f"expected exactly one column to start with {label!r} so the boundary is unambiguous, "
        f"found {sorted(matches)}. The document changed and this test is now measuring "
        "something other than what it names"
    )
    return matches.pop()


def assert_column_stays_put(runs: list[Run], *, starts_at: float, boundary: float, what: str, beside: str) -> None:
    """Nothing drawn in a column reaches the column to its right.

    ``starts_at`` picks out the cells of one column by their left edge, which is
    shared exactly by every left aligned cell in it, wrapped lines included.
    """
    column = [run for run in runs if abs(run.x0 - starts_at) < 0.5]
    assert column, (
        f"no text was found at x={starts_at:.1f}, so the {what} column was not drawn and this "
        "test proves nothing. Either the value never reached the page or the layout moved"
    )
    worst = max(column, key=lambda run: run.x1)
    assert worst.x1 <= boundary + 0.5, (
        f"{what} is drawn out to {worst.x1:.0f}pt, past {boundary:.0f}pt where {beside} begins, "
        f"so {worst.x1 - boundary:.0f}pt of it is printed on top of the column beside it. "
        f"The run that does it is {worst.text[:40]!r}"
    )


def fill_colour_of(pdf_bytes: bytes, text: str, page_number: int = 0) -> tuple[float, ...]:
    """The fill colour in effect when a given piece of text was drawn."""
    data = pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages[page_number]["/Contents"].get_data()
    ops = re.compile(
        rb"(?P<rgb>[-\d.]+\s+[-\d.]+\s+[-\d.]+\s+rg)"
        rb"|(?P<grey>[-\d.]+\s+g\b)"
        rb"|(?P<show>\[(?:[^\[\]\\]|\\.)*\]\s*TJ|\((?:[^()\\]|\\.)*\)\s*Tj)"
    )
    piece = re.compile(rb"\(((?:[^()\\]|\\.)*)\)")
    wanted = text.encode()
    colour: tuple[float, ...] = ()
    for match in ops.finditer(data):
        operator = match.group("rgb") or match.group("grey")
        if operator:
            numbers = operator.split()[:-1]
            colour = tuple(float(n) for n in numbers)
        elif match.group("show") and wanted in b"".join(piece.findall(match.group("show"))):
            return colour
    raise AssertionError(f"{text!r} was never drawn on page {page_number}, so it has no colour")


# ── The AIA payment application ─────────────────────────────────────────────


def aia_payload(**overrides: Any) -> dict[str, Any]:
    """A payment application carrying every field the renderer reads."""
    payload: dict[str, Any] = {
        "application_number": "APP-014",
        "claim_date": "2026-04-15",
        "period_end": "2026-04-30",
        "currency": "USD",
        "certification": {
            "architect_certified_by": "Ortega Architects",
            "architect_certified_at": "2026-05-01",
            "owner_certified_by": "Harbour Estates",
            "owner_certified_at": "2026-05-02",
            "certified_amount": "1000.00",
        },
        "summary": {
            "original_contract_sum": "1000.00",
            "change_orders_net": "0.00",
            "contract_sum_to_date": "1000.00",
            "total_completed_stored": "1000.00",
            "retainage": "0.00",
            "total_earned_less_retainage": "1000.00",
            "previous_certificates_total": "0.00",
            "current_payment_due": "1000.00",
            "balance_to_finish": "0.00",
        },
        "lines": [
            {
                "item_number": "01",
                "description": "Substructure",
                "scheduled_value": "1000.00",
                "previous_value": "0.00",
                "this_period_value": "1000.00",
                "materials_stored": "0.00",
                "total_completed_stored": "1000.00",
                "percent_complete": "100.00",
                "balance_to_finish": "0.00",
                "retainage": "0.00",
            }
        ],
    }
    payload.update(overrides)
    return payload


def aia_pdf(**overrides: Any) -> bytes:
    from app.modules.contracts.aia_pdf import render_aia_application_pdf

    return render_aia_application_pdf(aia_payload(**overrides))


def test_a_long_certifier_name_is_not_printed_over_the_date_beside_it() -> None:
    """The certification block is 50mm, 90mm and 80mm, and the middle column is
    a name someone types. A practice name wider than 90mm used to be drawn
    straight across the certification date."""
    certification = dict(aia_payload()["certification"], architect_certified_by=LONG_CERTIFIER)
    runs = drawn_runs(aia_pdf(certification=certification))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "Harbour Estates"),
        boundary=column_start(runs, "2026-05-01"),
        what="the architect's practice name",
        beside="the certification date",
    )


def test_the_continuation_sheet_header_is_not_black_on_a_dark_fill() -> None:
    """The header row sits on #1f2937 and asked for white text through a table
    command. Its cells are Paragraphs, which a table command cannot reach, so
    the row was drawn in the default black on a near black fill."""
    colour = fill_colour_of(aia_pdf(), "Scheduled")
    assert colour and max(colour) > 0.5, (
        f"the continuation sheet header is drawn in {colour}, which on the #1f2937 fill behind it "
        "is unreadable. The white it asks for has to be on the paragraph style, because a "
        "TEXTCOLOR table command does not reach a flowable cell"
    )


def test_an_ampersand_in_a_payment_application_is_printed_and_not_escaped() -> None:
    """These cells are parsed as markup now, so the helper escapes them. Escaping
    twice, or not unescaping, would put the entity on a contract document."""
    certification = dict(aia_payload()["certification"], owner_certified_by="R&D Tower <Ltda>")
    text = pypdf.PdfReader(io.BytesIO(aia_pdf(certification=certification))).pages[0].extract_text()
    assert "R&D Tower <Ltda>" in text
    assert "&amp;" not in text
    assert "&lt;" not in text


def test_an_apostrophe_in_a_payment_application_is_printed_and_not_escaped() -> None:
    """html.escape turns an apostrophe into a numeric entity, and a name with
    one in it is ordinary in this document's market."""
    certification = dict(aia_payload()["certification"], owner_certified_by="O'Brien Construction")
    text = pypdf.PdfReader(io.BytesIO(aia_pdf(certification=certification))).pages[0].extract_text()
    assert "O'Brien Construction" in text
    assert "&#x27;" not in text


def test_a_payment_application_that_already_fitted_is_laid_out_where_it_was() -> None:
    """The control. Ordinary values were never the problem and must not move."""
    runs = {run.text: (round(run.x0, 1), round(run.x1, 1)) for run in drawn_runs(aia_pdf())}
    assert runs["Ortega Architects"] == (231.9, 302.3)
    assert runs["Substructure"] == (53.3, 98.6)
    assert runs["Application No."] == (90.2, 159.2)


# ── The meeting minutes ─────────────────────────────────────────────────────


def minutes_pdf(**content_overrides: Any) -> bytes:
    from app.modules.meetings.pdf import build_minutes_pdf

    content: dict[str, Any] = {
        "title": "Site progress meeting",
        "meeting_date": "2026-08-23",
        "location": "Site office",
        "meeting_type": "site_meeting",
        "meeting_number": "001",
        "chairperson": "Jurgen Muller",
        "attendees_present": [{"name": "Jurgen Muller"}],
        "action_items": [
            {"description": "Confirm the survey", "owner": "Ana Silva", "due_date": "2026-09-01", "status": "open"}
        ],
    }
    content.update(content_overrides)
    meeting = SimpleNamespace(title=content["title"], meeting_number="001", meeting_date="2026-08-23")
    minutes = SimpleNamespace(content=content, status="issued", issued_at=datetime.now(tz=UTC))
    return build_minutes_pdf(meeting, minutes, "Northgate Quarter")


def test_a_long_site_address_stays_on_the_meeting_minutes_page() -> None:
    """The information table's second column is the rest of the page, so an
    address too long for it had nowhere to go but off the sheet."""
    runs = drawn_runs(minutes_pdf(location=LONG_LOCATION))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "2026-08-23"),
        boundary=MINUTES_FRAME_RIGHT,
        what="the meeting location",
        beside="the right hand edge of the page",
    )


def test_a_long_action_item_is_not_printed_over_the_owner_beside_it() -> None:
    """The action column is 44 percent of the page and holds a sentence."""
    actions = [{"description": LONG_ACTION, "owner": "Ana Silva", "due_date": "2026-09-01", "status": "open"}]
    runs = drawn_runs(minutes_pdf(action_items=actions))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "Action"),
        boundary=column_start(runs, "Owner"),
        what="the action item description",
        beside="the owner column",
    )


def test_a_long_action_owner_is_not_printed_over_the_due_date_beside_it() -> None:
    """The owner column is 20 percent of the page and holds a person's name."""
    actions = [{"description": "Confirm the survey", "owner": LONG_PERSON, "due_date": "2026-09-01", "status": "open"}]
    runs = drawn_runs(minutes_pdf(action_items=actions))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "Owner"),
        boundary=column_start(runs, "Due"),
        what="the action item owner",
        beside="the due date column",
    )


def test_meeting_minutes_that_already_fitted_are_laid_out_where_they_were() -> None:
    """The control for this document."""
    runs = {run.text: (round(run.x0, 1), round(run.x1, 1)) for run in drawn_runs(minutes_pdf())}
    assert runs["Chairperson:"] == (62.7, 127.8)
    assert runs["Not scheduled"] == (153.4, 218.1)


# ── The punch list ──────────────────────────────────────────────────────────


def punchlist_pdf(**item_overrides: Any) -> bytes:
    from app.modules.punchlist.service import _build_reportlab_pdf

    fields: dict[str, Any] = {
        "title": "Damp external wall",
        "description": "North face, third floor.",
        "status": "open",
        "priority": "high",
        "category": "Waterproofing",
        "trade": "Rohbau",
        "due_date": date(2026, 9, 1),
        "photos": [],
        "resolution_notes": "",
        "reopen_history": [],
        "metadata_": {"code": "PL-001"},
        "location_x": None,
        "location_y": None,
        "document_id": None,
        "page": None,
        "assigned_to": "Ana Silva",
    }
    fields.update(item_overrides)
    item = SimpleNamespace(**fields)
    return _build_reportlab_pdf("11111111-1111-1111-1111-111111111111", [item], {})


def test_a_long_assignee_is_not_printed_over_the_punch_list_label_beside_it() -> None:
    """The meta table is 26mm, 55mm, 26mm, 55mm, and the assignee lives in the
    second of those. A name wider than 55mm used to be drawn over the Due Date
    label, which is the one thing on that row a reader needs to find."""
    runs = drawn_runs(punchlist_pdf(assigned_to=LONG_PERSON), page_number=1)
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "open"),
        boundary=column_start(runs, "Due Date"),
        what="the punch item assignee",
        beside="the Due Date label",
    )


def test_a_long_trade_stays_on_the_punch_list_page() -> None:
    """The trade is the last column, so nothing was to its right to be printed
    over and it ran off the sheet instead."""
    runs = drawn_runs(punchlist_pdf(trade=LONG_TRADE), page_number=1)
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "high"),
        boundary=PUNCHLIST_FRAME_RIGHT,
        what="the punch item trade",
        beside="the right hand edge of the page",
    )


def test_a_punch_list_that_already_fitted_is_laid_out_where_it_was() -> None:
    """The control for this document."""
    runs = {run.text: (round(run.x0, 1), round(run.x1, 1)) for run in drawn_runs(punchlist_pdf(), page_number=1)}
    assert runs["Assignee"] == (74.0, 119.9)
    assert runs["Due Date"] == (303.6, 350.7)
    assert runs["2026-09-01"] == (377.3, 429.6)


# ── The meeting export route ────────────────────────────────────────────────


class _OneRow:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _StubSession:
    """Answers the two queries the export route makes and nothing else."""

    def __init__(self, *answers: Any) -> None:
        self._answers = list(answers)

    async def execute(self, _statement: Any) -> _OneRow:
        return _OneRow(self._answers.pop(0))


async def meeting_export_pdf(monkeypatch: pytest.MonkeyPatch, **meeting_fields: Any) -> bytes:
    from app.modules.meetings import router as meetings_router

    async def allow(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(meetings_router, "verify_project_access", allow)
    fields: dict[str, Any] = {
        "id": "22222222-2222-2222-2222-222222222222",
        "project_id": "11111111-1111-1111-1111-111111111111",
        "title": "Site progress meeting",
        "meeting_number": "001",
        "meeting_date": "2026-08-23",
        "location": "Site office",
        "meeting_type": "site_meeting",
        "status": "confirmed",
        "attendees": [{"name": "Ana Silva", "company": "Silva Engineering", "status": "present"}],
        "agenda_items": [],
        "action_items": [
            {"description": "Confirm the survey", "owner": "Ana Silva", "due_date": "2026-09-01", "status": "open"}
        ],
    }
    fields.update(meeting_fields)
    meeting = SimpleNamespace(**fields)
    session = _StubSession(meeting, "Northgate Quarter")
    response = await meetings_router.export_meeting_pdf(meeting.id, session, "a-user")  # type: ignore[arg-type]
    return b"".join([chunk async for chunk in response.body_iterator])


async def test_a_long_attendee_company_is_not_printed_over_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """The attendance table's company column is 35 percent of the page."""
    attendees = [
        {
            "name": "Ana Silva",
            "company": "Silva Engineering and Environmental Consultants Limited Partnership",
            "status": "present",
        }
    ]
    runs = drawn_runs(await meeting_export_pdf(monkeypatch, attendees=attendees, action_items=[]))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "Company"),
        boundary=column_start(runs, "Status"),
        what="the attendee's company",
        beside="the status column",
    )


async def test_a_long_exported_action_item_is_not_printed_over_the_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same action item table as the minutes, reached through the route."""
    actions = [{"description": LONG_ACTION, "owner": "Ana Silva", "due_date": "2026-09-01", "status": "open"}]
    runs = drawn_runs(await meeting_export_pdf(monkeypatch, action_items=actions, attendees=[]))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "Description"),
        boundary=column_start(runs, "Owner"),
        what="the exported action item description",
        beside="the owner column",
    )


async def test_a_long_exported_site_address_stays_on_the_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route's information table, whose second column is the rest of the page."""
    runs = drawn_runs(await meeting_export_pdf(monkeypatch, location=LONG_LOCATION))
    assert_column_stays_put(
        runs,
        starts_at=column_start(runs, "2026-08-23"),
        boundary=MINUTES_FRAME_RIGHT,
        what="the exported meeting location",
        beside="the right hand edge of the page",
    )
