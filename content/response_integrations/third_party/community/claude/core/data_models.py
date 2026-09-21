from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from TIPCommon.types import JSON, SingleJson


class IntegrationParameters(NamedTuple):
    api_root: str
    api_key: str
    model: str
    max_output_tokens: int
    effort: str
    adaptive_thinking: bool
    request_timeout: int
    verify_ssl: bool


@dataclasses.dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def to_json(self) -> SingleJson:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ClaudeResponse:
    """A normalized response from the Claude Messages API."""

    text: str
    model: str
    stop_reason: str | None
    usage: TokenUsage
    request_id: str | None = None
    message_id: str | None = None
    structured_output: JSON | None = None

    @property
    def is_truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    def to_json(self) -> SingleJson:
        result: SingleJson = {
            "response": self.text,
            "model": self.model,
            "stop_reason": self.stop_reason,
            "is_truncated": self.is_truncated,
            "message_id": self.message_id,
            "request_id": self.request_id,
            "usage": self.usage.to_json(),
        }
        if self.structured_output is not None:
            result["structured_output"] = self.structured_output

        return result
