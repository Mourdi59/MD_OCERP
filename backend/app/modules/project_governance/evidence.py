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

An item may carry ``link=(kind, id)``. The module that owns the kind says once
where it opens, ``register_evidence_link(kind, "/projects/{project_id}/...")``,
and the gate page gets the finished path with the item. The screen holds no
table of kinds; a kind nobody registered is shown without a link.
"""

from __future__ import annotations

import logging
import string
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ``warning``: by the provider's own rule the gate may pass, and something is still outstanding.
# It never blocks; a go has to name it, exactly like an unknown item of a blocking provider.
EVIDENCE_STATES = ("met", "not_met", "unknown", "warning")
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

    def as_dict(self, project_id: uuid.UUID | str | None = None) -> dict[str, Any]:
        i = self.item
        return {
            "code": i.code,
            "state": i.state,
            "label": {"key": i.label_key, "text": i.labels},
            "link": (
                {"kind": i.link[0], "id": i.link[1], "href": evidence_link_href(i.link[0], i.link[1], project_id)}
                if i.link
                else None
            ),
            "detail": i.detail,
            "provider": self.provider,
            "blocking": self.blocking,
            "error": self.error,
        }


_REGISTRY: dict[str, RegisteredProvider] = {}

_LINK_FIELDS = frozenset({"id", "project_id"})
_LINK_ROUTES: dict[str, str] = {}


def register_evidence_link(kind: str, route: str) -> None:
    """Say where evidence links of ``kind`` open: a path of the web app.

    ``route`` starts with ``/`` and may use ``{project_id}`` (the project of
    the gate) and ``{id}`` (the second half of the item's link). Registering a
    kind again replaces its route. Raises ``ValueError`` on anything else, at
    import time of the module that registers it.
    """
    fields = {name for _, name, _, _ in string.Formatter().parse(route) if name is not None}
    if not kind or not route.startswith("/") or route.startswith("//") or not fields <= _LINK_FIELDS:
        raise ValueError(
            f"evidence link route for {kind!r} must be a path using only {sorted(_LINK_FIELDS)}: {route!r}"
        )
    _LINK_ROUTES[kind] = route


def unregister_evidence_link(kind: str) -> None:
    _LINK_ROUTES.pop(kind, None)


def evidence_link_href(kind: str, link_id: str, project_id: uuid.UUID | str | None) -> str | None:
    """The path a link of ``kind`` opens, or ``None`` when no module registered the kind."""
    route = _LINK_ROUTES.get(kind)
    if route is None or (project_id is None and "{project_id}" in route):
        return None
    return route.format(id=link_id, project_id=project_id)


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
