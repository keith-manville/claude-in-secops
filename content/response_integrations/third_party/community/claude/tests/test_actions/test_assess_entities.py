from __future__ import annotations

from typing import TYPE_CHECKING

from integration_testing.common import create_entity
from integration_testing.set_meta import set_metadata
from TIPCommon.base.action import EntityTypesEnum, ExecutionState

from claude.actions import assess_entities
from claude.core.prompts import ENTITY_ASSESSMENT_OUTPUT_SCHEMA, ENTITY_ASSESSMENT_SYSTEM_PROMPT
from claude.tests.common import CONFIG_PATH, MOCK_MODEL_ID, build_input_context
from claude.tests.core.mock_data import ALERT_NAME

if TYPE_CHECKING:
    from integration_testing.platform.script_output import MockActionOutput
    from TIPCommon.types import Entity, SingleJson

    from claude.tests.core.product import ClaudeMockApi, SoarMockPlatform


IP_IDENTIFIER: str = "203.0.113.45"
USER_IDENTIFIER: str = "JDOE"


def ip_entity() -> Entity:
    return create_entity(IP_IDENTIFIER, EntityTypesEnum.ADDRESS, additional_properties={"VT_detections": "14"})


def user_entity() -> Entity:
    return create_entity(USER_IDENTIFIER, EntityTypesEnum.USER, additional_properties={"Department": "Finance"})


MALICIOUS_ASSESSMENT: SingleJson = {
    "verdict": "Malicious",
    "confidence": "High",
    "risk_score": 92,
    "summary": "Known payload host.",
    "reasoning": "14 detections in VT_detections.",
    "recommended_actions": ["Block at the firewall"],
}
BENIGN_ASSESSMENT: SingleJson = {
    "verdict": "Benign",
    "confidence": "Medium",
    "risk_score": 10,
    "summary": "Regular finance user.",
    "reasoning": "No anomalies in the provided data.",
    "recommended_actions": [],
}


def _json_result(action_output: MockActionOutput) -> list[SingleJson]:
    return action_output.results.json_output.json_result


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={"Entity Type": "All Entities", "Mark Malicious Entities As Suspicious": True},
    input_context=build_input_context(),
    entities=[ip_entity(), user_entity()],
)
def test_assess_entities_success(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_structured(MALICIOUS_ASSESSMENT)
    claude_api.queue_structured(BENIGN_ASSESSMENT)

    assess_entities.main()

    assert len(claude_api.requests) == 2
    first: SingleJson = claude_api.requests[0]
    assert first["system"] == ENTITY_ASSESSMENT_SYSTEM_PROMPT
    assert first["output_config"]["format"]["schema"] == ENTITY_ASSESSMENT_OUTPUT_SCHEMA
    content: str = first["messages"][0]["content"]
    assert "<entity_data>" in content
    assert IP_IDENTIFIER in content
    assert "VT_detections" in content
    assert "<alert_data>" not in content

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.result_value is True
    assert action_output.results.output_message == (
        f"Successfully assessed the following entities with Claude: {IP_IDENTIFIER}, {USER_IDENTIFIER}\n"
        f"Marked as suspicious: {IP_IDENTIFIER}"
    )

    results: list[SingleJson] = _json_result(action_output)
    assert {item["Entity"] for item in results} == {IP_IDENTIFIER, USER_IDENTIFIER}
    ip_result: SingleJson = next(item["EntityResult"] for item in results if item["Entity"] == IP_IDENTIFIER)
    assert ip_result["verdict"] == "Malicious"
    assert ip_result["risk_score"] == 92
    assert ip_result["model"] == MOCK_MODEL_ID

    assert len(soar_platform.entity_updates) == 1
    updated: list[SingleJson] = soar_platform.entity_updates[0]
    by_id: dict[str, SingleJson] = {entity["identifier"]: entity for entity in updated}
    ip_update: SingleJson = by_id[IP_IDENTIFIER]
    assert ip_update["is_suspicious"] is True
    assert ip_update["is_enriched"] is True
    assert ip_update["additional_properties"]["Claude_verdict"] == "Malicious"
    assert ip_update["additional_properties"]["Claude_risk_score"] == "92"
    assert ip_update["additional_properties"]["Claude_recommended_actions"] == "Block at the firewall"
    assert ip_update["additional_properties"]["VT_detections"] == "14"
    user_update: SingleJson = by_id[USER_IDENTIFIER]
    assert user_update["is_suspicious"] is False
    assert user_update["additional_properties"]["Claude_verdict"] == "Benign"

    assert len(soar_platform.insights) == 2
    assert soar_platform.insights[0]["entity_identifier"] == IP_IDENTIFIER
    assert "<b>Risk score:</b> 92/100" in soar_platform.insights[0]["content"]


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={
        "Entity Type": "IP Address",
        "Include Alert Context": True,
        "Additional Instructions": "10.0.0.0/8 is our corporate range.",
        "Create Insight": "false",
    },
    input_context=build_input_context(),
    entities=[ip_entity(), user_entity()],
)
def test_assess_entities_scoped_with_context(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_structured(MALICIOUS_ASSESSMENT)

    assess_entities.main()

    assert len(claude_api.requests) == 1
    content: str = claude_api.last_request["messages"][0]["content"]
    assert "<alert_data>" in content
    assert ALERT_NAME in content
    assert "<analyst_instructions>\n10.0.0.0/8 is our corporate range.\n</analyst_instructions>" in content

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message == (
        f"Successfully assessed the following entities with Claude: {IP_IDENTIFIER}"
    )
    assert soar_platform.insights == []
    updated: list[SingleJson] = soar_platform.entity_updates[0]
    assert [entity["identifier"] for entity in updated] == [IP_IDENTIFIER]
    assert updated[0]["is_suspicious"] is False


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    input_context=build_input_context(),
    entities=[ip_entity(), user_entity()],
)
def test_assess_entities_partial_failure(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.fail_next(status_code=400, error_type="invalid_request_error", message="boom")
    claude_api.queue_structured(BENIGN_ASSESSMENT)

    assess_entities.main()

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.result_value is True
    assert action_output.results.output_message == (
        f"Successfully assessed the following entities with Claude: {USER_IDENTIFIER}\n"
        f"Failed to assess the following entities: {IP_IDENTIFIER}"
    )
    results: list[SingleJson] = _json_result(action_output)
    failed: SingleJson = next(item["EntityResult"] for item in results if item["Entity"] == IP_IDENTIFIER)
    assert "boom" in failed["execution_status"]


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={"Entity Type": "Hostname"},
    input_context=build_input_context(),
    entities=[ip_entity()],
)
def test_assess_entities_no_matching_entities(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    assess_entities.main()

    assert claude_api.requests == []
    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.result_value is False
    assert action_output.results.output_message == "No eligible entities were found in the scope of the alert."
