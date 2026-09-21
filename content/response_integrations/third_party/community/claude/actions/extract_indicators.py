from __future__ import annotations

from typing import TYPE_CHECKING

from TIPCommon.extraction import extract_action_param
from TIPCommon.validation import ParameterValidator

from ..core.base_action import ClaudeAction
from ..core.constants import (
    ENRICHMENT_PREFIX,
    EXTRACT_INDICATORS_SCRIPT_NAME,
    INDICATOR_KEY_TO_ENTITY_TYPE,
    INPUT_TEXT_TAG,
    INSTRUCTIONS_TAG,
    JSON_RESULT_MODEL_KEY,
    JSON_RESULT_USAGE_KEY,
    MAX_CONTEXT_CHARS,
)
from ..core.prompts import IOC_EXTRACTION_OUTPUT_SCHEMA, IOC_EXTRACTION_SYSTEM_PROMPT
from ..core.utils import truncate_text, wrap_in_tag

if TYPE_CHECKING:
    from typing import NoReturn

    from TIPCommon.types import SingleJson

    from ..core.data_models import ClaudeResponse


EXTRACTION_PROMPT: str = "Extract all indicators of compromise from the following text.\n\n{text}"
SUCCESS_MESSAGE: str = "Successfully extracted {count} indicators with Claude: {breakdown}."
NO_INDICATORS_MESSAGE: str = "Claude did not find any indicators in the provided text."
ENTITIES_MESSAGE: str = " Added {count} indicators as entities to the alert."
ENTITY_FAILURES_MESSAGE: str = " Failed to add {count} indicators as entities, see logs for details."
INDICATOR_TYPE_PROPERTY: str = f"{ENRICHMENT_PREFIX}indicator_type"
EXTRACTED_PROPERTY: str = f"{ENRICHMENT_PREFIX}extracted_from_text"


class ExtractIndicators(ClaudeAction):
    def __init__(self) -> None:
        super().__init__(EXTRACT_INDICATORS_SCRIPT_NAME)
        self.created_entities: int = 0
        self.failed_entities: int = 0

    def _extract_action_parameters(self) -> None:
        self.params.text = extract_action_param(
            self.soar_action,
            param_name="Text",
            is_mandatory=True,
            print_value=False,
        )
        self.params.additional_instructions = extract_action_param(
            self.soar_action,
            param_name="Additional Instructions",
            print_value=True,
        )
        self.params.add_entities = extract_action_param(
            self.soar_action,
            param_name="Add Indicators As Entities",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self.params.mark_suspicious = extract_action_param(
            self.soar_action,
            param_name="Mark Entities As Suspicious",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self._extract_effort_param()

    def _validate_params(self) -> None:
        validator: ParameterValidator = ParameterValidator(self.soar_action)
        self._require(bool(self.params.text and self.params.text.strip()), '"Text" must not be empty.')
        self._validate_effort_param(validator)

    def _perform_action(self, _=None) -> None:
        text: str = truncate_text(self.params.text, MAX_CONTEXT_CHARS)
        prompt: str = EXTRACTION_PROMPT.format(text=wrap_in_tag(INPUT_TEXT_TAG, text))
        if self.params.additional_instructions:
            prompt = f"{prompt}\n\n{wrap_in_tag(INSTRUCTIONS_TAG, self.params.additional_instructions)}"

        response: ClaudeResponse = self.api_client.create_message(
            prompt=prompt,
            system_prompt=IOC_EXTRACTION_SYSTEM_PROMPT,
            effort=self.params.effort,
            json_schema=IOC_EXTRACTION_OUTPUT_SCHEMA,
        )
        indicators: SingleJson = response.structured_output
        self.json_results = {
            **indicators,
            JSON_RESULT_MODEL_KEY: response.model,
            JSON_RESULT_USAGE_KEY: response.usage.to_json(),
        }

        counts: dict[str, int] = {
            key: len(indicators.get(key, []))
            for key in (*INDICATOR_KEY_TO_ENTITY_TYPE.keys(), "mitre_attack_techniques")
            if indicators.get(key)
        }
        total: int = sum(counts.values())
        if self.params.add_entities:
            self._add_indicators_as_entities(indicators)

        if total:
            breakdown: str = ", ".join(f"{count} {key.replace('_', ' ')}" for key, count in counts.items())
            self.output_message = SUCCESS_MESSAGE.format(count=total, breakdown=breakdown)
        else:
            self.output_message = NO_INDICATORS_MESSAGE

        if self.created_entities:
            self.output_message += ENTITIES_MESSAGE.format(count=self.created_entities)
        if self.failed_entities:
            self.output_message += ENTITY_FAILURES_MESSAGE.format(count=self.failed_entities)

    def _add_indicators_as_entities(self, indicators: SingleJson) -> None:
        for key, entity_type in INDICATOR_KEY_TO_ENTITY_TYPE.items():
            for item in indicators.get(key, []):
                identifier: str = str(item.get("value", "") if isinstance(item, dict) else item).strip()
                if not identifier:
                    continue

                properties: dict[str, str] = {
                    INDICATOR_TYPE_PROPERTY: key,
                    EXTRACTED_PROPERTY: "true",
                }
                if isinstance(item, dict) and item.get("hash_type"):
                    properties[f"{ENRICHMENT_PREFIX}hash_type"] = str(item["hash_type"])

                try:
                    self.logger.info(f"Adding entity {identifier} ({entity_type.value}) to the alert")
                    self.soar_action.add_entity_to_case(
                        entity_identifier=identifier,
                        entity_type=entity_type.value,
                        is_internal=False,
                        is_suspicous=self.params.mark_suspicious,
                        is_enriched=False,
                        is_vulnerable=False,
                        properties=properties,
                    )
                    self.created_entities += 1
                except Exception as error:  # noqa: BLE001
                    self.failed_entities += 1
                    self.logger.error(f"Failed to add entity {identifier} ({entity_type.value}): {error}")


def main() -> NoReturn:
    ExtractIndicators().run()


if __name__ == "__main__":
    main()
