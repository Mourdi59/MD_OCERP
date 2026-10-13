# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""One error type for the plant register service, mapped to HTTP by the router.

``code`` is stable and is also the message key ``plant.errors.<code>``. A
refused transition lists every blocker in ``violations`` at once.
"""

from __future__ import annotations

from typing import Any


class PlantError(Exception):
    """A refused plant register operation."""

    def __init__(
        self,
        code: str,
        status_code: int = 422,
        *,
        violations: list[dict[str, Any]] | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.status_code = status_code
        self.violations = violations or []
        self.detail = detail

    def as_detail(self, message: str) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message_key": f"plant.errors.{self.code}", "message": message}
        if self.violations:
            body["violations"] = self.violations
        if self.detail:
            body["info"] = self.detail
        return body


def not_found(code: str) -> PlantError:
    """A 404 that does not say whether the row exists in another project."""
    return PlantError(code, 404)


def conflict(code: str, **kw: Any) -> PlantError:
    return PlantError(code, 409, **kw)


def forbidden(code: str, **kw: Any) -> PlantError:
    return PlantError(code, 403, **kw)


def finding_keys(finding: str) -> tuple[str, str, str | None]:
    """``code[:reason]`` as ``(code, message key of the code, message key of the reason or None)``."""
    code, _, reason = finding.partition(":")
    return code, f"plant.errors.{code}", f"plant.reasons.{reason}" if reason else None


def blocked(violations: list[str]) -> PlantError:
    """A 422 listing every rule that blocks.

    Each row is ``{code, message_key, reason, reason_key}``. ``reason`` is a
    sub-code for machines (which part of the rule), never a text to show:
    ``reason_key`` is its message key, ``None`` when the rule has no sub-reason.
    """
    rows = []
    for v in violations:
        code, key, reason_key = finding_keys(v)
        rows.append({"code": code, "message_key": key, "reason": v.partition(":")[2], "reason_key": reason_key})
    return PlantError(rows[0]["code"] if len(rows) == 1 else "transition_blocked", 422, violations=rows)


def worded(violations: list[dict[str, Any]], locale: str) -> list[dict[str, Any]]:
    """The violations with ``message`` and ``reason_message`` in ``locale``, for a reader."""
    from app.modules.plant_register.messages import translate

    return [
        {
            **v,
            "message": translate(v["message_key"], locale=locale),
            "reason_message": translate(v["reason_key"], locale=locale) if v.get("reason_key") else None,
        }
        for v in violations
    ]
