from __future__ import annotations

import json
from typing import TYPE_CHECKING

from TIPCommon.extraction import extract_action_param
from TIPCommon.validation import ParameterValidator

from ..core.alert_context import alert_context_to_string, build_alert_context
from ..core.base_action import ClaudeAction
from ..core.constants import (
    ALERT_DATA_TAG,
    ASK_CLAUDE_SCRIPT_NAME,
    DEFAULT_MAX_EVENTS,
    MAX_INSIGHT_CHARS,
)
from ..core.exceptions import ClaudeInvalidParameterError
from ..core.prompts import DEFAULT_ASK_SYSTEM_PROMPT
from ..core.utils import text_to_html, truncate_text, wrap_in_tag

if TYPE_CHECKING:
    from typing import NoReturn

    from TIPCommon.types import SingleJson

    from ..core.data_models import ClaudeResponse


INSIGHT_TITLE: str = "Claude Response"
SUCCESS_MESSAGE: str = "Successfully received a response from Claude. Model: {model}, output tokens: {tokens}."
TRUNCATED_SUFFIX: str = " Note: the response was cut off by the max output tokens limit."


class AskClaude(ClaudeAction):
    def __init__(self) -> None:
        super().__init__(ASK_CLAUDE_SCRIPT_NAME)

    def _extract_action_parameters(self) -> None:
        self.params.prompt = extract_action_param(
            self.soar_action,
            param_name="Prompt",
            is_mandatory=True,
            print_value=True,
        )
        self.params.system_prompt = extract_action_param(
            self.soar_action,
            param_name="System Prompt",
            print_value=True,
        )
        self.params.json_schema = extract_action_param(
            self.soar_action,
            param_name="JSON Schema",
            print_value=True,
        )
        self.params.include_alert_context = extract_action_param(
            self.soar_action,
            param_name="Include Alert Context",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self.params.create_insight = extract_action_param(
            self.soar_action,
            param_name="Create Insight",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self.params.add_comment = extract_action_param(
            self.soar_action,
            param_name="Add Comment",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self._extract_effort_param()
        self._extract_model_override_params()

    def _validate_params(self) -> None:
        validator: ParameterValidator = ParameterValidator(self.soar_action)
        self._require(bool(self.params.prompt and self.params.prompt.strip()), '"Prompt" must not be empty.')
        self._validate_effort_param(validator)
        self._validate_model_override_params(validator)
        self.params.json_schema = self._parse_json_schema(validator)

    def _parse_json_schema(self, validator: ParameterValidator) -> SingleJson | None:
        if not self.params.json_schema or not self.params.json_schema.strip():
            return None

        schema: SingleJson = validator.validate_json(
            param_name="JSON Schema",
            json_string=self.params.json_schema,
            print_value=False,
        )
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ClaudeInvalidParameterError('"JSON Schema" must be a JSON Schema object with "type": "object".')

        return schema

    def _perform_action(self, _=None) -> None:
        prompt: str = self.params.prompt
        if self.params.include_alert_context:
            self.logger.info("Collecting the current alert context for the prompt")
            context: SingleJson = build_alert_context(
                self.soar_action,
                logger=self.logger,
                max_events=DEFAULT_MAX_EVENTS,
            )
            prompt = f"{prompt}\n\n{wrap_in_tag(ALERT_DATA_TAG, alert_context_to_string(context))}"

        response: ClaudeResponse = self.api_client.create_message(
            prompt=prompt,
            system_prompt=self.params.system_prompt or DEFAULT_ASK_SYSTEM_PROMPT,
            model=self.params.model,
            max_output_tokens=self.params.max_output_tokens,
            effort=self.params.effort,
            json_schema=self.params.json_schema,
        )
        self.json_results = response.to_json()

        display_text: str = (
            json.dumps(response.structured_output, indent=2, ensure_ascii=False)
            if response.structured_output is not None
            else response.text
        )
        if self.params.create_insight:
            self._add_case_insight(title=INSIGHT_TITLE, content=text_to_html(display_text))

        if self.params.add_comment:
            self._add_case_comment(f"{INSIGHT_TITLE}:\n{truncate_text(display_text, MAX_INSIGHT_CHARS)}")

        self.output_message = SUCCESS_MESSAGE.format(model=response.model, tokens=response.usage.output_tokens)
        if response.is_truncated:
            self.output_message += TRUNCATED_SUFFIX


def main() -> NoReturn:
    AskClaude().run()


if __name__ == "__main__":
    main()
