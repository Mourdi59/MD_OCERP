# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The whole project handbook as one PDF.

Built on :func:`app.core.register_export.build_record_pdf`: a head with the project and the approval
count, then for every chapter a block with owner, status, version and approval, the chapter text, and one
table per live source (the records of other modules the chapter reads, as they are at the time of
printing). Every label comes from this module's message bundle, in the language of the document.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RecordBlock, RecordDocument, build_record_pdf, caps, grid_rows
from app.modules.project_handbook.messages import translate

EMPTY = "-"


def _t(key: str, locale: str, **params: object) -> str:
    return translate(f"project_handbook.export.{key}", locale=locale, **params)


def _day(value: str | None) -> str:
    return value[:10] if value else EMPTY


def _status(status: str, locale: str) -> str:
    return translate(f"project_handbook.status.{status}", locale=locale)


def _source_title(name: str, locale: str) -> str:
    key = f"project_handbook.source.{name}"
    return translate(key, locale=locale)


def handbook_document(data: dict[str, Any], *, locale: str) -> RecordDocument:
    """The record document of the whole handbook; ``data`` is ``ProjectHandbookService.export_data``."""
    chapters: list[dict[str, Any]] = data["chapters"]
    approved = sum(1 for c in chapters if c["approved_version"] is not None)
    required = [c for c in chapters if c["required"]]
    required_open = sum(1 for c in required if c["approved_version"] is None)
    blocks: list[RecordBlock] = []
    contents = [[f"{i}.", c["title"], _status(c["status"], locale)] for i, c in enumerate(chapters, 1)]
    blocks.append(
        RecordBlock(
            title=_t("contents", locale),
            kind="table",
            rows=[[_t("col_no", locale), _t("col_chapter", locale), _t("col_status", locale)], *contents],
            weights=[0.6, 5.0, 2.0],
            keep_together=[True, False, True],
        )
    )
    for index, chapter in enumerate(chapters, 1):
        version = chapter["approved_version"]
        pairs = grid_rows(
            [
                (_t("owner", locale), chapter["owner_name"] or EMPTY),
                (_t("status", locale), _status(chapter["status"], locale)),
                (_t("version", locale), f"{version}" if version is not None else EMPTY),
                (_t("approved", locale), _approval(chapter, locale)),
            ]
        )
        blocks.append(RecordBlock(title=f"{index}. {chapter['title']}", kind="grid", rows=pairs))
        blocks.append(
            RecordBlock(
                title=_t("text", locale), kind="text", text=chapter["content"], empty_text=_t("no_text", locale)
            )
        )
        for linked in chapter.get("linked") or []:
            rows = [[r["label"], r["detail"] or EMPTY] for r in linked["rows"]]
            blocks.append(
                RecordBlock(
                    title=_t("live_records", locale, source=_source_title(linked["source"], locale)),
                    kind="table",
                    rows=[[_t("col_record", locale), _t("col_detail", locale)], *(rows or [[_t("none", locale), ""]])],
                    weights=[3.0, 2.0],
                )
            )
    head = [
        (_t("chapters", locale), str(len(chapters))),
        (_t("approved_chapters", locale), f"{approved} / {len(chapters)}"),
        (_t("required_open", locale), str(required_open)),
        (_t("edition", locale), data["edition"] or EMPTY),
    ]
    project_label = data["project_name"] + (f" ({data['project_code']})" if data["project_code"] else "")
    return RecordDocument(
        title=data["title"] or _t("title", locale),
        number=data["edition"] or EMPTY,
        project_label=project_label,
        status_text=caps(_t("state_open" if required_open else "state_complete", locale), locale),
        subject=_t("title", locale),
        grid=grid_rows(head),
        blocks=blocks,
        page_label=_t("page", locale),
        generated_label=_t("generated", locale),
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )


def _approval(chapter: dict[str, Any], locale: str) -> str:
    if chapter["approved_version"] is None:
        return EMPTY
    who = chapter["approved_by_name"] or EMPTY
    return f"{who}, {_day(chapter['approved_at'])}"


def render(data: dict[str, Any], *, locale: str) -> bytes:
    """PDF bytes of the whole handbook."""
    return build_record_pdf(handbook_document(data, locale=locale))
