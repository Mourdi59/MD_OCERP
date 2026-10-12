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


def blocked(violations: list[str]) -> PlantError:
    """A 422 listing every rule that blocks, each as ``{code, message_key}``."""
    rows = [
        {"code": v.split(":")[0], "reason": v.partition(":")[2], "message_key": f"plant.errors.{v.split(':')[0]}"}
        for v in violations
    ]
    return PlantError(rows[0]["code"] if len(rows) == 1 else "transition_blocked", 422, violations=rows)
