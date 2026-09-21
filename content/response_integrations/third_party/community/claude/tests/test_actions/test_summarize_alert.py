from __future__ import annotations

import json
from typing import TYPE_CHECKING

from integration_testing.common import create_entity
from integration_testing.set_meta import set_metadata
from soar_sdk.SiemplifyDataModel import InsightSeverity
from TIPCommon.base.action import EntityTypesEnum, ExecutionState

from claude.actions import summarize_alert
from claude.core.prompts import TRIAGE_OUTPUT_SCHEMA, TRIAGE_SYSTEM_PROMPT
from claude.tests.common import CONFIG_PATH, MOCK_MODEL_ID, build_input_context
from claude.tests.core.mock_data import ALERT_ID, ALERT_NAME, EVENT_COMMAND_LINE

if TYPE_CHECKING:
    from integration_testing.platform.script_output import MockActionOutput
    from TIPCommon.types import Entity, SingleJson

    from claude.tests.core.product import ClaudeMockApi, SoarMockPlatform


IP_IDENTIFIER: str = "203.0.113.45"


def ip_entity() -> Entity:
    return create_entity(IP_IDENTIFIER, EntityTypesEnum.ADDRESS, additional_properties={"VT_detections": "14"})


TRIAGE_RESULT: SingleJson = {
    "summary": "Office spawned encoded PowerShell that downloaded a payload.",
    "verdict": "Malicious",
    "confidence": "High",
    "suggested_severity": "High",
    "attack_narrative": "winword.exe spawned powershell.exe which connected to 203.0.113.45.",
    "key_findings": ["Encoded PowerShell", "External download"],
    "mitre_attack_techniques": [{"technique_id": "T1059.001", "name": "PowerShell"}],
    "indicators_of_compromise": [{"value": "203.0.113.45", "type": "ip_address"}],
    "recommended_actions": ["Isolate WS-FIN-042"],
    "open_questions": ["Was the payload executed?"],
}


def _json_result(action_output: MockActionOutput) -> SingleJson:
    return action_output.results.json_output.json_result


@set_metadata(integration_config_file_path=CONFIG_PATH, input_context=build_input_context(), entities=[ip_entity()])
def test_summarize_alert_success(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_structured(TRIAGE_RESULT)

    summarize_alert.main()

    request: SingleJson = claude_api.last_request
    assert request["system"] == TRIAGE_SYSTEM_PROMPT
    assert request["output_config"]["format"]["schema"] == TRIAGE_OUTPUT_SCHEMA
    content: str = request["messages"][0]["content"]
    assert "<alert_data>" in content
    assert ALERT_NAME in content
    assert EVENT_COMMAND_LINE in content
    assert IP_IDENTIFIER in content
    assert "VT_detections" in content
    assert "<analyst_instructions>" not in content

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message == (
        "Successfully summarized the alert with Claude. Verdict: Malicious (High confidence), suggested severity: High."
    )
    result: SingleJson = _json_result(action_output)
    assert result["verdict"] == "Malicious"
    assert result["mitre_attack_techniques"] == TRIAGE_RESULT["mitre_attack_techniques"]
    assert result["model"] == MOCK_MODEL_ID
    assert result["usage"]["input_tokens"] == 120

    assert len(soar_platform.insights) == 1
    insight: SingleJson = soar_platform.insights[0]
    assert insight["title"] == "Claude Alert Triage"
    assert insight["severity"] == InsightSeverity.ERROR
    assert "<b>Verdict:</b> Malicious (High confidence)" in insight["content"]
    assert "T1059.001 PowerShell" in insight["content"]
    assert "Isolate WS-FIN-042" in insight["content"]
    assert soar_platform.comments == []


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={
        "Additional Instructions": "Finance users often run macros.",
        "Max Events": "1",
        "Include Entity Properties": "false",
        "Create Insight": "false",
        "Add Comment": True,
        "Effort": "max",
    },
    input_context=build_input_context(),
    entities=[ip_entity()],
)
def test_summarize_alert_with_options(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_structured({**TRIAGE_RESULT, "verdict": "Benign", "suggested_severity": "Low"})

    summarize_alert.main()

    request: SingleJson = claude_api.last_request
    content: str = request["messages"][0]["content"]
    assert request["output_config"]["effort"] == "max"
    assert "<analyst_instructions>\nFinance users often run macros.\n</analyst_instructions>" in content
    assert "VT_detections" not in content
    context: SingleJson = json.loads(content.split("<alert_data>\n", 1)[1].split("\n</alert_data>", 1)[0])
    assert context["alert"]["total_events"] == 2
    assert context["alert"]["included_events"] == 1
    assert context["case"]["title"] == ALERT_NAME

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert soar_platform.insights == []
    assert len(soar_platform.comments) == 1
    assert soar_platform.comments[0]["comment"].startswith("Claude Alert Triage\nVerdict: Benign (High confidence)")
    assert "- Isolate WS-FIN-042" in soar_platform.comments[0]["comment"]


@set_metadata(
    integration_config_file_path=CONFIG_PATH, parameters={"Max Events": "0"}, input_context=build_input_context()
)
def test_summarize_alert_invalid_max_events(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    summarize_alert.main()

    assert claude_api.requests == []
    assert action_output.results.execution_state == ExecutionState.FAILED


@set_metadata(integration_config_file_path=CONFIG_PATH, input_context=build_input_context())
def test_summarize_alert_invalid_structured_output(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text("not json", stop_reason="max_tokens")

    summarize_alert.main()

    assert action_output.results.execution_state == ExecutionState.FAILED
    assert "cut off by the max output tokens limit" in action_output.results.output_message


@set_metadata(integration_config_file_path=CONFIG_PATH, input_context=build_input_context())
def test_summarize_alert_without_loadable_alert(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    soar_platform.alert = None
    claude_api.queue_structured(TRIAGE_RESULT)

    summarize_alert.main()

    content: str = claude_api.last_request["messages"][0]["content"]
    assert f'"id": "{ALERT_ID}"' in content
    assert action_output.results.execution_state == ExecutionState.COMPLETED
