from __future__ import annotations

import html
from typing import TYPE_CHECKING

from soar_sdk.SiemplifyUtils import unix_now
from TIPCommon.base.action.base_enrich_action import EnrichAction
from TIPCommon.extraction import extract_action_param
from TIPCommon.validation import ParameterValidator

from ..core.alert_context import alert_context_to_string, build_alert_context, entity_to_json
from ..core.base_action import ClaudeAction
from ..core.constants import (
    ALERT_DATA_TAG,
    ASSESS_ENTITIES_SCRIPT_NAME,
    DEFAULT_MAX_EVENTS,
    ENRICHMENT_PREFIX,
    ENTITY_DATA_TAG,
    INSTRUCTIONS_TAG,
    JSON_RESULT_MODEL_KEY,
    MAX_ENRICHMENT_VALUE_CHARS,
    EntityScopeEnum,
    EntityTypesEnum,
    EntityVerdictEnum,
)
from ..core.prompts import ENTITY_ASSESSMENT_OUTPUT_SCHEMA, ENTITY_ASSESSMENT_SYSTEM_PROMPT
from ..core.utils import flatten_for_enrichment, html_list, text_to_html, to_json_string, wrap_in_tag

if TYPE_CHECKING:
    from typing import NoReturn

    from TIPCommon.types import Entity, SingleJson

    from ..core.data_models import ClaudeResponse


DEFAULT_ENTITY_SCOPE: str = EntityScopeEnum.ALL.value
ENTITY_PROMPT: str = "Assess the following entity. Return your assessment in the required JSON format.\n\n{entity}"
SUCCESS_MESSAGE: str = "Successfully assessed the following entities with Claude: {entities}"
FAILED_MESSAGE: str = "Failed to assess the following entities: {entities}"
NO_ENTITIES_MESSAGE: str = "No eligible entities were found in the scope of the alert."
ALL_FAILED_MESSAGE: str = "Claude was not able to assess any of the eligible entities."


class AssessEntities(EnrichAction, ClaudeAction):
    def __init__(self) -> None:
        super().__init__(ASSESS_ENTITIES_SCRIPT_NAME)
        self.assessed_entities: list[str] = []
        self.failed_entities: list[str] = []
        self.suspicious_entities: list[str] = []
        self._alert_context_prompt: str | None = None

    def _extract_action_parameters(self) -> None:
        self.params.entity_scope = extract_action_param(
            self.soar_action,
            param_name="Entity Type",
            default_value=DEFAULT_ENTITY_SCOPE,
            print_value=True,
        )
        self.params.additional_instructions = extract_action_param(
            self.soar_action,
            param_name="Additional Instructions",
            print_value=True,
        )
        self.params.include_alert_context = extract_action_param(
            self.soar_action,
            param_name="Include Alert Context",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self.params.mark_suspicious = extract_action_param(
            self.soar_action,
            param_name="Mark Malicious Entities As Suspicious",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self.params.create_insight = extract_action_param(
            self.soar_action,
            param_name="Create Insight",
            default_value=True,
            input_type=bool,
            print_value=True,
        )
        self._extract_effort_param()

    def _validate_params(self) -> None:
        validator: ParameterValidator = ParameterValidator(self.soar_action)
        self.params.entity_scope = validator.validate_ddl(
            param_name="Entity Type",
            value=self.params.entity_scope,
            ddl_values=EntityScopeEnum.values(),
            print_value=True,
        )
        self._validate_effort_param(validator)

    def _get_entity_types(self) -> list[EntityTypesEnum]:
        return EntityScopeEnum(self.params.entity_scope).to_entity_type_enum_list()

    def _perform_enrich_action(self, current_entity: Entity) -> None:
        self.logger.info(f"Asking Claude to assess entity {current_entity.identifier}")
        response: ClaudeResponse = self.api_client.create_message(
            prompt=self._build_prompt(current_entity),
            system_prompt=ENTITY_ASSESSMENT_SYSTEM_PROMPT,
            effort=self.params.effort,
            json_schema=ENTITY_ASSESSMENT_OUTPUT_SCHEMA,
        )
        assessment: SingleJson = response.structured_output
        verdict: str = str(assessment.get("verdict", EntityVerdictEnum.UNKNOWN.value))

        self.entity_results = {**assessment, JSON_RESULT_MODEL_KEY: response.model}
        self.enrichment_data = {
            f"{ENRICHMENT_PREFIX}{key}": value
            for key, value in flatten_for_enrichment(
                {**assessment, "model": response.model, "assessed_at": unix_now()},
                max_value_chars=MAX_ENRICHMENT_VALUE_CHARS,
            ).items()
        }
        if self.params.mark_suspicious and verdict == EntityVerdictEnum.MALICIOUS.value:
            self.logger.info(f"Marking entity {current_entity.identifier} as suspicious")
            current_entity.is_suspicious = True
            self.suspicious_entities.append(current_entity.identifier)

        if self.params.create_insight:
            self._add_entity_insight(current_entity, build_assessment_html(assessment, response.model))

        self.assessed_entities.append(current_entity.identifier)
        self.logger.info(f"Finished assessing entity {current_entity.identifier}. Verdict: {verdict}")

    def _build_prompt(self, entity: Entity) -> str:
        prompt: str = ENTITY_PROMPT.format(
            entity=wrap_in_tag(ENTITY_DATA_TAG, to_json_string(entity_to_json(entity))),
        )
        if self.params.include_alert_context:
            prompt = f"{prompt}\n\n{self._get_alert_context_prompt()}"

        if self.params.additional_instructions:
            prompt = f"{prompt}\n\n{wrap_in_tag(INSTRUCTIONS_TAG, self.params.additional_instructions)}"

        return prompt

    def _get_alert_context_prompt(self) -> str:
        if self._alert_context_prompt is None:
            self.logger.info("Collecting the current alert context")
            context: SingleJson = build_alert_context(
                self.soar_action,
                logger=self.logger,
                max_events=DEFAULT_MAX_EVENTS,
            )
            self._alert_context_prompt = wrap_in_tag(ALERT_DATA_TAG, alert_context_to_string(context))

        return self._alert_context_prompt

    def _on_entity_failure(self, current_entity: Entity, error: Exception) -> None:
        self.failed_entities.append(current_entity.identifier)
        # EnrichAction wraps the original error without a message, so surface the cause.
        cause: BaseException = error.__cause__ if not str(error) and error.__cause__ else error
        self.json_results[current_entity.original_identifier] = {"execution_status": str(cause)}

    def _finalize_action_on_success(self) -> None:
        messages: list[str] = []
        if self.assessed_entities:
            messages.append(SUCCESS_MESSAGE.format(entities=", ".join(self.assessed_entities)))
        if self.suspicious_entities:
            messages.append(f"Marked as suspicious: {', '.join(self.suspicious_entities)}")
        if self.failed_entities:
            messages.append(FAILED_MESSAGE.format(entities=", ".join(self.failed_entities)))

        if not self.assessed_entities:
            self.result_value = False
            messages.append(ALL_FAILED_MESSAGE if self.failed_entities else NO_ENTITIES_MESSAGE)

        self.output_message = "\n".join(messages)


def build_assessment_html(assessment: SingleJson, model: str) -> str:
    """Render an entity assessment as HTML for an entity insight.

    Args:
        assessment: The structured assessment.
        model: The model that produced it.

    Returns:
        An HTML string.
    """
    header: str = (
        f"<b>Verdict:</b> {html.escape(str(assessment.get('verdict', '')))} "
        f"({html.escape(str(assessment.get('confidence', '')))} confidence)<br>"
        f"<b>Risk score:</b> {html.escape(str(assessment.get('risk_score', '')))}/100<br>"
        f"<b>Model:</b> {html.escape(model)}"
    )
    sections: list[tuple[str, str]] = [
        ("Summary", text_to_html(str(assessment.get("summary", "")))),
        ("Reasoning", text_to_html(str(assessment.get("reasoning", "")))),
        ("Recommended actions", html_list(assessment.get("recommended_actions", []))),
    ]
    body: str = "".join(f"<h3>{title}</h3>{content}" for title, content in sections if content)
    return f"<p>{header}</p>{body}"


def main() -> NoReturn:
    AssessEntities().run()


if __name__ == "__main__":
    main()
