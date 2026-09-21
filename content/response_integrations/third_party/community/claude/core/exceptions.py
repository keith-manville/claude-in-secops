from __future__ import annotations


class ClaudeIntegrationError(Exception):
    """General exception for the Claude integration."""


class ClaudeInvalidParameterError(ClaudeIntegrationError):
    """Raised when an integration or action parameter is invalid."""


class ClaudeApiError(ClaudeIntegrationError):
    """Raised when the Claude API returns an error or cannot be reached."""

    def __init__(
        self,
        message: str,
        *args: object,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, *args)
        self.status_code: int | None = status_code
        self.request_id: str | None = request_id


class ClaudeRefusalError(ClaudeIntegrationError):
    """Raised when Claude declines a request (stop_reason == refusal)."""

    def __init__(
        self,
        message: str,
        *args: object,
        category: str | None = None,
        explanation: str | None = None,
    ) -> None:
        super().__init__(message, *args)
        self.category: str | None = category
        self.explanation: str | None = explanation


class ClaudeResponseError(ClaudeIntegrationError):
    """Raised when a response from Claude cannot be interpreted."""
