# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Readiness evidence providers: the extension point other modules plug gate evidence into.

A module registers ``register_evidence_provider(key, provider)`` where ``key`` is an
area code (``"design"``) or ``"*"`` for every area, and ``provider`` is an async
callable ``(session, project_id, gate_attempt, area) -> list[EvidenceItem]``.
The gate readiness view collects evidence from every provider registered for an
area, shows it, and treats ``not_met`` from a provider registered with
``blocking=True`` as a blocker (``evidence_not_met``). A provider that raises is
logged and shown as one ``unknown`` item; it never breaks the gate page and never
blocks. Areas the project marked not applicable are not asked at all.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

EVIDENCE_STATES = ("met", "not_met", "unknown")
ANY_AREA = "*"


@dataclass(frozen=True)
class GateAttempt:
    """The gate attempt a provider is asked about."""

    gate_id: uuid.UUID
    gate_code: str
    attempt_no: int


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of readiness evidence. Label is an i18n key or a ``{locale: text}`` map."""

    code: str
    state: str
    label_key: str | None = None
    labels: dict[str, str] | None = None
    link: tuple[str, str] | None = None  # (kind, id)
    detail: str = ""

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise ValueError(f"evidence state must be one of {EVIDENCE_STATES}, got {self.state!r}")


Provider = Callable[[Any, uuid.UUID, GateAttempt, Any], Awaitable[list[EvidenceItem]]]


@dataclass(frozen=True)
class RegisteredProvider:
    name: str
    key: str
    provider: Provider
    blocking: bool = False


@dataclass(frozen=True)
class CollectedEvidence:
    area_code: str
    provider: str
    blocking: bool
    item: EvidenceItem
    error: bool = False

    def as_dict(self) -> dict[str, Any]:
        i = self.item
        return {
            "code": i.code,
            "state": i.state,
            "label": {"key": i.label_key, "text": i.labels},
            "link": {"kind": i.link[0], "id": i.link[1]} if i.link else None,
            "detail": i.detail,
            "provider": self.provider,
            "blocking": self.blocking,
            "error": self.error,
        }


_REGISTRY: dict[str, RegisteredProvider] = {}


def register_evidence_provider(
    area_code_or_kind: str, provider: Provider, *, name: str | None = None, blocking: bool = False
) -> None:
    """Register (or replace, by name) a provider for one area code or ``"*"``."""
    pname = name or f"{getattr(provider, '__module__', '')}.{getattr(provider, '__qualname__', repr(provider))}"
    _REGISTRY[pname] = RegisteredProvider(pname, area_code_or_kind, provider, blocking)


def unregister_evidence_provider(name: str) -> None:
    _REGISTRY.pop(name, None)


def evidence_providers() -> list[RegisteredProvider]:
    return list(_REGISTRY.values())


async def collect_evidence(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, areas: list[Any]
) -> list[CollectedEvidence]:
    """Ask every matching provider about every applicable area; failures become ``unknown``."""
    out: list[CollectedEvidence] = []
    for area in areas:
        if not getattr(area, "applicable", True) or getattr(area, "retired", False):
            continue
        for reg in list(_REGISTRY.values()):
            if reg.key not in (ANY_AREA, area.code):
                continue
            try:
                # A savepoint keeps a provider's failed SQL from poisoning the caller's transaction.
                begin_nested = getattr(session, "begin_nested", None)
                if begin_nested is not None:
                    async with begin_nested():
                        items = await reg.provider(session, project_id, attempt, area)
                else:
                    items = await reg.provider(session, project_id, attempt, area)
                for item in items or []:
                    out.append(CollectedEvidence(area.code, reg.name, reg.blocking, item))
                if not items and reg.blocking and reg.key == area.code:
                    # Registered for exactly this area and silent about it: shown as unknown, so the
                    # gate does not read as covered. A provider registered for every area answers
                    # only for its own, and its silence elsewhere is not a missing answer.
                    out.append(
                        CollectedEvidence(
                            area.code,
                            reg.name,
                            reg.blocking,
                            EvidenceItem(code=f"{reg.name}:no_answer", state="unknown"),
                        )
                    )
            except Exception:
                logger.exception("governance evidence provider %s failed for area %s", reg.name, area.code)
                out.append(
                    CollectedEvidence(
                        area.code,
                        reg.name,
                        reg.blocking,
                        EvidenceItem(
                            code=f"{reg.name}:error",
                            state="unknown",
                            label_key="governance.evidence.provider_failed",
                        ),
                        error=True,
                    )
                )
    return out
