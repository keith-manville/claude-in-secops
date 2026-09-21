from __future__ import annotations

import html
from typing import TYPE_CHECKING

from TIPCommon.base.action.data_models import InsightSeverity
from TIPCommon.extraction import extract_action_param
from TIPCommon.validation import ParameterValidator

from ..core.alert_context import alert_context_to_string, build_alert_context
from ..core.base_action import ClaudeAction
from ..core.constants import (
    ALERT_DATA_TAG,
    DEFAULT_MAX_EVENTS,
    INSTRUCTIONS_TAG,
    JSON_RESULT_MODEL_KEY,
    JSON_RESULT_USAGE_KEY,
    MAX_EVENTS_LIMIT,
    SUMMARIZE_ALERT_SCRIPT_NAME,
    VerdictEnum,
)
from ..core.prompts import TRIAGE_OUTPUT_SCHEMA, TRIAGE_SYSTEM_PROMPT
from ..core.utils import html_list, text_to_html, wrap_in_tag

if TYPE_CHECKING:
    from typing import NoReturn

    from TIPCommon.types import SingleJson

    from ..core.data_models import ClaudeResponse


INSIGHT_TITLE: str = "Claude Alert Triage"
SUCCESS_MESSAGE: str = (
    "Successfully summarized the alert with Claude. Verdict: {verdict} ({confidence} confidence), "
    "suggested severity: {severity}."
)
TRIAGE_PROMPT: str = (
    "Triage the following Google SecOps alert. Return your assessment in the required JSON format.\n\n{alert}"
)
VERDICT_TO_SEVERITY: dict[str, int] = {
    VerdictEnum.MALICIOUS.value: InsightSeverity.ERROR,
    VerdictEnum.SUSPICIOUS.value: InsightSeverity.WARN,
}


class SummarizeAlert(ClaudeAction):
    def __init__(self) -> None:
        super().__init__(SUMMARIZE_ALERT_SCRIPT_NAME)

    def _extract_action_parameters(self) -> None:
        self.params.additional_instructions = extract_action_param(
            self.soar_action,
            param_name="Additional Instructions",
            print_value=True,
        )
        self.params.max_events = extract_action_param(
            self.soar_action,
            param_name="Max Events",
            default_value=str(DEFAULT_MAX_EVENTS),
            print_value=True,
        )
        self.params.include_entity_properties = extract_action_param(
            self.soar_action,
            param_name="Include Entity Properties",
            default_value=True,
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
        self.params.add_comment = extract_action_param(
            self.soar_action,
            param_name="Add Comment",
            default_value=False,
            input_type=bool,
            print_value=True,
        )
        self._extract_effort_param()

    def _validate_params(self) -> None:
        validator: ParameterValidator = ParameterValidator(self.soar_action)
        self._validate_effort_param(validator)
        self.params.max_events = self._validate_positive_int(
            validator,
            param_name="Max Events",
            value=self.params.max_events,
            max_limit=MAX_EVENTS_LIMIT,
        )

    def _perform_action(self, _=None) -> None:
        self.logger.info("Collecting the current alert context")
        context: SingleJson = build_alert_context(
            self.soar_action,
            logger=self.logger,
            max_events=self.params.max_events,
            include_entity_properties=self.params.include_entity_properties,
        )
        prompt: str = TRIAGE_PROMPT.format(alert=wrap_in_tag(ALERT_DATA_TAG, alert_context_to_string(context)))
        if self.params.additional_instructions:
            prompt = f"{prompt}\n\n{wrap_in_tag(INSTRUCTIONS_TAG, self.params.additional_instructions)}"

        response: ClaudeResponse = self.api_client.create_message(
            prompt=prompt,
            system_prompt=TRIAGE_SYSTEM_PROMPT,
            effort=self.params.effort,
            json_schema=TRIAGE_OUTPUT_SCHEMA,
        )
        triage: SingleJson = response.structured_output
        self.json_results = {
            **triage,
            JSON_RESULT_MODEL_KEY: response.model,
            JSON_RESULT_USAGE_KEY: response.usage.to_json(),
        }

        if self.params.create_insight:
            self._add_case_insight(
                title=INSIGHT_TITLE,
                content=build_triage_html(triage, response.model),
                severity=VERDICT_TO_SEVERITY.get(triage.get("verdict", ""), InsightSeverity.INFO),
            )

        if self.params.add_comment:
            self._add_case_comment(build_triage_comment(triage))

        self.output_message = SUCCESS_MESSAGE.format(
            verdict=triage.get("verdict"),
            confidence=triage.get("confidence"),
            severity=triage.get("suggested_severity"),
        )


def build_triage_html(triage: SingleJson, model: str) -> str:
    """Render the triage result as HTML for a case insight.

    Args:
        triage: The structured triage output.
        model: The model that produced it.

    Returns:
        An HTML string.
    """
    techniques: list[str] = [
        f"{item.get('technique_id', '')} {item.get('name', '')}".strip()
        for item in triage.get("mitre_attack_techniques", [])
    ]
    indicators: list[str] = [
        f"{item.get('value', '')} ({item.get('type', '')})" for item in triage.get("indicators_of_compromise", [])
    ]
    sections: list[tuple[str, str]] = [
        ("Summary", text_to_html(triage.get("summary", ""))),
        ("Attack narrative", text_to_html(triage.get("attack_narrative", ""))),
        ("Key findings", html_list(triage.get("key_findings", []))),
        ("MITRE ATT&CK techniques", html_list(techniques)),
        ("Indicators of compromise", html_list(indicators)),
        ("Recommended actions", html_list(triage.get("recommended_actions", []))),
        ("Open questions", html_list(triage.get("open_questions", []))),
    ]
    header: str = (
        f"<b>Verdict:</b> {html.escape(str(triage.get('verdict', '')))} "
        f"({html.escape(str(triage.get('confidence', '')))} confidence)<br>"
        f"<b>Suggested severity:</b> {html.escape(str(triage.get('suggested_severity', '')))}<br>"
        f"<b>Model:</b> {html.escape(model)}"
    )
    body: str = "".join(f"<h3>{title}</h3>{content}" for title, content in sections if content)
    return f"<p>{header}</p>{body}"


def build_triage_comment(triage: SingleJson) -> str:
    """Render the triage result as plain text for a case comment.

    Args:
        triage: The structured triage output.

    Returns:
        A plain text comment.
    """
    lines: list[str] = [
        f"{INSIGHT_TITLE}",
        f"Verdict: {triage.get('verdict')} ({triage.get('confidence')} confidence)",
        f"Suggested severity: {triage.get('suggested_severity')}",
        "",
        str(triage.get("summary", "")),
    ]
    if triage.get("recommended_actions"):
        lines.append("")
        lines.append("Recommended actions:")
        lines.extend(f"- {action}" for action in triage["recommended_actions"])

    return "\n".join(lines)


def main() -> NoReturn:
    SummarizeAlert().run()


if __name__ == "__main__":
    main()
