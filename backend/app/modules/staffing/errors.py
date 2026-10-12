# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""One error type for the staffing service, mapped to HTTP by the router.

``code`` is stable and is also the message key ``staffing.errors.<code>``.
``violations`` carries the rule findings when an operation is refused, so
the client can list every blocker at once instead of one per round trip.
"""

from __future__ import annotations

from typing import Any


class StaffingError(Exception):
    """A refused staffing operation."""

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
        """The ``detail`` body of the HTTP error."""
        body: dict[str, Any] = {
            "code": self.code,
            "message_key": f"staffing.errors.{self.code}",
            "message": message,
        }
        if self.violations:
            body["violations"] = self.violations
        if self.detail:
            body["info"] = self.detail
        return body


def not_found(code: str) -> StaffingError:
    """A 404 that does not say whether the row exists in another project."""
    return StaffingError(code, 404)


def conflict(code: str, **kw: Any) -> StaffingError:
    """A 409: the state of the record does not allow this now."""
    return StaffingError(code, 409, **kw)


def forbidden(code: str, **kw: Any) -> StaffingError:
    """A 403: the caller may see the record but not do this to it."""
    return StaffingError(code, 403, **kw)
