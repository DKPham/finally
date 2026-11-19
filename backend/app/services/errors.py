"""Service-layer error type, mapped to an HTTP error response by the API layer."""

from __future__ import annotations


class ServiceError(Exception):
    """A business-rule or validation failure with an HTTP status and a human-readable detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        return self.detail
