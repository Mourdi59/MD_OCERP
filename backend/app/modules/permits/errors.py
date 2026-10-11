# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""One error type for the permits service, mapped to HTTP by the router.

``code`` is stable and is also the message key ``permits.errors.<code>``.
``violations`` carries the evaluator's findings when a decision is refused, so
the client can list every blocker at once instead of one per round trip.
"""

from __future__ import annotations

from typing import Any


class PermitError(Exception):
    """A refused permits operation."""

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
        body: dict[str, Any] = {"code": self.code, "message_key": f"permits.errors.{self.code}", "message": message}
        if self.violations:
            body["violations"] = self.violations
        if self.detail:
            body["info"] = self.detail
        return body


def not_found(code: str) -> PermitError:
    """A 404 that does not say whether the row exists in another project."""
    return PermitError(code, 404)


def conflict(code: str, **kw: Any) -> PermitError:
    """A 409: the state of the record does not allow this now."""
    return PermitError(code, 409, **kw)


def forbidden(code: str, **kw: Any) -> PermitError:
    """A 403: the caller may see the record but not do this to it."""
    return PermitError(code, 403, **kw)
