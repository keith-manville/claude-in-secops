from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, NamedTuple

import anthropic
from TIPCommon.base.interfaces import Apiable

from ..constants import (
    MAX_TOKENS_STOP_REASON,
    REFUSAL_STOP_REASON,
    TEXT_BLOCK_TYPE,
    EffortEnum,
)
from ..data_models import ClaudeResponse, TokenUsage
from ..exceptions import ClaudeApiError, ClaudeRefusalError, ClaudeResponseError

if TYPE_CHECKING:
    from anthropic.types import Message, ModelInfo
    from TIPCommon.base.interfaces.logger import ScriptLogger
    from TIPCommon.types import JSON, SingleJson


class ApiParameters(NamedTuple):
    model: str
    max_output_tokens: int
    effort: str
    adaptive_thinking: bool


class ClaudeApiClient(Apiable):
    """Thin wrapper around the Anthropic SDK that normalizes responses and errors."""

    def __init__(
        self,
        authenticated_session: anthropic.Anthropic,
        configuration: ApiParameters,
        logger: ScriptLogger,
    ) -> None:
        super().__init__(
            authenticated_session=authenticated_session,
            configuration=configuration,
        )
        self.logger: ScriptLogger = logger
        self.client: anthropic.Anthropic = authenticated_session
        self.default_model: str = configuration.model
        self.default_max_output_tokens: int = configuration.max_output_tokens
        self.default_effort: str = configuration.effort
        self.adaptive_thinking: bool = configuration.adaptive_thinking

    def test_connectivity(self) -> SingleJson:
        """Verify the API key and the configured model by retrieving the model.

        Returns:
            Basic information about the configured model.

        Raises:
            ClaudeApiError: If the API key is invalid or the model does not exist.
        """
        try:
            model_info: ModelInfo = self.client.models.retrieve(self.default_model)
        except anthropic.APIError as error:
            raise _wrap_api_error(error) from error

        return {
            "id": model_info.id,
            "display_name": model_info.display_name,
            "created_at": model_info.created_at.isoformat() if model_info.created_at else None,
        }

    def create_message(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_output_tokens: int | None = None,
        effort: str | None = None,
        json_schema: SingleJson | None = None,
    ) -> ClaudeResponse:
        """Send a single-turn request to the Messages API.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            model: Model override. Defaults to the integration's model.
            max_output_tokens: Max output tokens override.
            effort: Effort override (`low`, `medium`, `high`, `xhigh`, `max` or `Default`).
            json_schema: If given, the model is constrained to return JSON matching the schema
                and the parsed object is returned in `ClaudeResponse.structured_output`.

        Returns:
            The normalized response.

        Raises:
            ClaudeApiError: If the request fails.
            ClaudeRefusalError: If Claude declines the request.
            ClaudeResponseError: If the response cannot be interpreted.
        """
        request: dict[str, Any] = self._build_request(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            max_output_tokens=max_output_tokens,
            effort=effort,
            json_schema=json_schema,
        )
        self.logger.info(
            f"Sending request to Claude. model={request['model']}, max_tokens={request['max_tokens']}, "
            f"structured_output={json_schema is not None}"
        )
        try:
            raw = self.client.messages.with_raw_response.create(**request)
            message: Message = raw.parse()
            request_id: str | None = raw.headers.get("request-id")
        except anthropic.APIError as error:
            raise _wrap_api_error(error) from error

        return self._parse_message(message, request_id=request_id, expect_json=json_schema is not None)

    def _build_request(
        self,
        prompt: str,
        system_prompt: str | None,
        model: str | None,
        max_output_tokens: int | None,
        effort: str | None,
        json_schema: SingleJson | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": (model or self.default_model).strip(),
            "max_tokens": max_output_tokens or self.default_max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            request["system"] = system_prompt

        if self.adaptive_thinking:
            request["thinking"] = {"type": "adaptive"}

        output_config: dict[str, Any] = {}
        resolved_effort: EffortEnum = EffortEnum.from_value(effort)
        if resolved_effort is EffortEnum.DEFAULT:
            resolved_effort = EffortEnum.from_value(self.default_effort)

        if resolved_effort is not EffortEnum.DEFAULT:
            output_config["effort"] = resolved_effort.value

        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}

        if output_config:
            request["output_config"] = output_config

        return request

    def _parse_message(self, message: Message, request_id: str | None, expect_json: bool) -> ClaudeResponse:
        if message.stop_reason == REFUSAL_STOP_REASON:
            details = message.stop_details
            category: str | None = getattr(details, "category", None) if details else None
            explanation: str | None = getattr(details, "explanation", None) if details else None
            raise ClaudeRefusalError(
                "Claude declined to process the request"
                + (f" (category: {category})" if category else "")
                + (f": {explanation}" if explanation else "."),
                category=category,
                explanation=explanation,
            )

        text: str = "".join(block.text for block in message.content if block.type == TEXT_BLOCK_TYPE)
        if message.stop_reason == MAX_TOKENS_STOP_REASON:
            self.logger.warn(
                "Claude's response was cut off because the max output tokens limit was reached. "
                "Consider increasing the max output tokens."
            )

        usage: TokenUsage = TokenUsage(
            input_tokens=message.usage.input_tokens or 0,
            output_tokens=message.usage.output_tokens or 0,
            cache_creation_input_tokens=message.usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=message.usage.cache_read_input_tokens or 0,
        )
        structured_output: JSON | None = None
        if expect_json:
            structured_output = _parse_json_output(text, truncated=message.stop_reason == MAX_TOKENS_STOP_REASON)

        self.logger.info(
            f"Received response from Claude. stop_reason={message.stop_reason}, "
            f"input_tokens={usage.input_tokens}, output_tokens={usage.output_tokens}, request_id={request_id}"
        )
        return ClaudeResponse(
            text=text,
            model=message.model,
            stop_reason=message.stop_reason,
            usage=usage,
            request_id=request_id,
            message_id=message.id,
            structured_output=structured_output,
        )


def _parse_json_output(text: str, truncated: bool) -> JSON:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        reason: str = (
            "the response was cut off by the max output tokens limit"
            if truncated
            else f"the response is not valid JSON ({error.msg})"
        )
        raise ClaudeResponseError(f"Failed to parse Claude's structured output: {reason}.") from error


def _wrap_api_error(error: anthropic.APIError) -> ClaudeApiError:
    """Translate SDK exceptions into a single integration exception with a clear message.

    Args:
        error: The exception raised by the Anthropic SDK.

    Returns:
        A `ClaudeApiError` describing the failure.
    """
    if isinstance(error, anthropic.APIStatusError):
        request_id: str | None = error.response.headers.get("request-id") if error.response is not None else None
        prefix: str
        if isinstance(error, anthropic.AuthenticationError):
            prefix = "Authentication with the Claude API failed. Check the API Key"
        elif isinstance(error, anthropic.PermissionDeniedError):
            prefix = "The API Key does not have permission to perform this request"
        elif isinstance(error, anthropic.NotFoundError):
            prefix = "The requested resource was not found. Check the Model and API Root"
        elif isinstance(error, anthropic.RateLimitError):
            prefix = "The Claude API rate limit was exceeded"
        elif isinstance(error, anthropic.BadRequestError):
            prefix = "The Claude API rejected the request"
        elif error.status_code >= 500:
            prefix = "The Claude API returned a server error"
        else:
            prefix = "The Claude API returned an error"

        return ClaudeApiError(
            f"{prefix} (HTTP {error.status_code}): {_extract_error_message(error)}",
            status_code=error.status_code,
            request_id=request_id,
        )

    if isinstance(error, anthropic.APITimeoutError):
        return ClaudeApiError("The request to the Claude API timed out. Consider increasing the Request Timeout.")

    if isinstance(error, anthropic.APIConnectionError):
        return ClaudeApiError(f"Failed to connect to the Claude API: {error}")

    return ClaudeApiError(f"Unexpected Claude API error: {error}")


def _extract_error_message(error: anthropic.APIStatusError) -> str:
    body: object = error.body
    if isinstance(body, dict):
        nested: object = body.get("error", body)
        if isinstance(nested, dict) and nested.get("message"):
            return str(nested["message"])

    return error.message
