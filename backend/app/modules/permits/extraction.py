# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Reading the conditions out of a permit notice with the platform's AI provider (SPEC rule 15).

The AI proposes, a person confirms. This module builds the request, and turns
the provider's answer into condition proposals that pass the same validation a
typed condition passes. It talks to nothing itself: the service fetches the
document text and calls the provider, so everything here is a pure function.

A proposal carries two references into the document. ``text_span`` is a short
locator (page or clause). ``passage`` is the sentence quoted from the notice;
it is kept only when it really occurs in the document text, so the screen never
shows as a quotation something the model made up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, get_args

from pydantic import ValidationError

from app.modules.permits.conditions import text_hash
from app.modules.permits.schemas import ConditionKind, ConditionProposal, Topic

# The notice text sent to the provider is capped; a longer document is cut and the caller is told.
MAX_DOCUMENT_CHARS = 60_000
MAX_PROPOSALS = 200
PASSAGE_MAX = 2000

# Triggers a proposal may carry: those that need no further field. A stage, a date or an event is
# for the reviewer to enter, so any other trigger arrives empty and the reviewer sets it.
SIMPLE_TRIGGERS: tuple[str, ...] = ("before_start", "before_occupation", "ongoing", "after_completion")


def system_prompt() -> str:
    """The instruction, with the allowed values read off the request schema so the two cannot drift."""
    kinds = ", ".join(get_args(ConditionKind))
    topics = ", ".join(get_args(Topic))
    triggers = ", ".join(SIMPLE_TRIGGERS)
    return (
        "You read the decision notice of a building or planning permit and list the conditions the authority "
        'attached to it. Answer with JSON only, no prose: an object {"conditions": [...]} where each item has '
        '"number" (the number or letter the condition has in the notice, as a string), "text" (the condition, '
        f'complete and in the language of the notice), "kind" (one of: {kinds}), "trigger" (one of: {triggers}, '
        f'or an empty string when the notice does not say or names a stage, a date or an event), "topic" (one of: '
        f'{topics}), "confidence" (a number from 0 to 1: how sure you are that this is a condition and that kind '
        'and trigger are right), "text_span" (where it stands, at most 40 characters, for example a page or '
        'clause reference) and "passage" (the sentence of the notice the condition is taken from, copied '
        'exactly). List only what the notice states. If it states no conditions, answer {"conditions": []}.'
    )


@dataclass(frozen=True)
class Parsed:
    """Proposals that passed validation, and how many items of the answer did not."""

    proposals: list[dict[str, Any]]
    rejected: int


def build_prompt(document_text: str) -> tuple[str, bool]:
    """The user message and whether the document had to be cut to fit."""
    text = document_text.strip()
    cut = len(text) > MAX_DOCUMENT_CHARS
    return "Decision notice:\n\n" + text[:MAX_DOCUMENT_CHARS], cut


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def _confidence(value: Any) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= number <= 1:
        return None
    return f"{number:.4f}".rstrip("0").rstrip(".") or "0"


def parse_response(data: Any, document_text: str) -> Parsed | None:
    """Proposals from the provider's parsed JSON; ``None`` when the answer has no usable shape at all.

    An item that fails validation is counted and left out, never repaired: a guessed kind or a
    made-up number would look like something the notice says.
    """
    items = data.get("conditions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    haystack = _squash(document_text)
    seen: set[str] = set()
    proposals: list[dict[str, Any]] = []
    rejected = 0
    for item in items[:MAX_PROPOSALS]:
        if not isinstance(item, dict):
            rejected += 1
            continue
        passage = str(item.get("passage") or "").strip()[:PASSAGE_MAX]
        body = {
            "number": str(item.get("number") or "").strip(),
            "text": str(item.get("text") or "").strip(),
            "kind": item.get("kind"),
            "trigger": item.get("trigger") if item.get("trigger") in SIMPLE_TRIGGERS else "",
            "topic": item.get("topic") or "other",
            "confidence": _confidence(item.get("confidence")),
            "text_span": str(item.get("text_span") or "").strip()[:40],
            # A quotation that is not in the document is not a quotation.
            "passage": passage if passage and _squash(passage) in haystack else "",
        }
        if body["confidence"] is None:
            rejected += 1
            continue
        try:
            proposal = ConditionProposal(**body)
        except ValidationError:
            rejected += 1
            continue
        key = text_hash(proposal.text)
        if not proposal.number.strip() or not proposal.text.strip() or key in seen:
            rejected += 1
            continue
        seen.add(key)
        proposals.append(proposal.model_dump())
    rejected += max(0, len(items) - MAX_PROPOSALS)
    return Parsed(proposals, rejected)
