# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""One error type for the project handbook service, mapped to HTTP by the router.

``code`` is stable and is also the message key ``project_handbook.errors.<code>``.
"""

from __future__ import annotations

from typing import Any


class HandbookError(Exception):
    """A refused handbook operation."""

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
            "message_key": f"project_handbook.errors.{self.code}",
            "message": message,
        }
        if self.violations:
            body["violations"] = self.violations
        if self.detail:
            body["info"] = self.detail
        return body


def not_found(code: str) -> HandbookError:
    """A 404 that does not say whether the row exists in another project."""
    return HandbookError(code, 404)


def conflict(code: str, **kw: Any) -> HandbookError:
    """A 409: the state of the record does not allow this now."""
    return HandbookError(code, 409, **kw)


def forbidden(code: str, **kw: Any) -> HandbookError:
    """A 403: the caller may see the record but not do this to it."""
    return HandbookError(code, 403, **kw)
