from __future__ import annotations

from typing import TYPE_CHECKING

from integration_testing.set_meta import set_metadata
from TIPCommon.base.action import ExecutionState

from claude.actions import extract_indicators
from claude.core.prompts import IOC_EXTRACTION_OUTPUT_SCHEMA, IOC_EXTRACTION_SYSTEM_PROMPT
from claude.tests.common import CONFIG_PATH, build_input_context

if TYPE_CHECKING:
    from integration_testing.platform.script_output import MockActionOutput
    from TIPCommon.types import SingleJson

    from claude.tests.core.product import ClaudeMockApi, SoarMockPlatform


TEXT: str = (
    "The loader beacons to hxxp://203[.]0[.]113[.]45/s2 and drops stage2.dll (md5 44d88612fea8a8f36de82e1278abb02f)."
)
EXTRACTED: SingleJson = {
    "ip_addresses": ["203.0.113.45"],
    "domains": [],
    "urls": ["http://203.0.113.45/s2"],
    "file_hashes": [{"value": "44d88612fea8a8f36de82e1278abb02f", "hash_type": "MD5"}],
    "email_addresses": [],
    "file_names": ["stage2.dll"],
    "cves": [],
    "mitre_attack_techniques": ["T1105"],
    "summary": "Loader beaconing to an external host.",
}
EMPTY: SingleJson = {
    "ip_addresses": [],
    "domains": [],
    "urls": [],
    "file_hashes": [],
    "email_addresses": [],
    "file_names": [],
    "cves": [],
    "mitre_attack_techniques": [],
    "summary": "No indicators.",
}


def _json_result(action_output: MockActionOutput) -> SingleJson:
    return action_output.results.json_output.json_result


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters={"Text": TEXT})
def test_extract_indicators_success(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_structured(EXTRACTED)

    extract_indicators.main()

    request: SingleJson = claude_api.last_request
    assert request["system"] == IOC_EXTRACTION_SYSTEM_PROMPT
    assert request["output_config"]["format"]["schema"] == IOC_EXTRACTION_OUTPUT_SCHEMA
    assert f"<input_text>\n{TEXT}\n</input_text>" in request["messages"][0]["content"]

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message == (
        "Successfully extracted 5 indicators with Claude: 1 ip addresses, 1 urls, 1 file hashes, 1 file names, "
        "1 mitre attack techniques."
    )
    result: SingleJson = _json_result(action_output)
    assert result["ip_addresses"] == ["203.0.113.45"]
    assert result["file_hashes"] == EXTRACTED["file_hashes"]
    assert result["model"] == "claude-opus-5"
    assert soar_platform.created_entities == []


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={"Text": TEXT, "Add Indicators As Entities": True, "Mark Entities As Suspicious": True},
    input_context=build_input_context(),
)
def test_extract_indicators_adds_entities(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_structured(EXTRACTED)

    extract_indicators.main()

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message.endswith("Added 4 indicators as entities to the alert.")
    created: dict[str, SingleJson] = {entity["entity_identifier"]: entity for entity in soar_platform.created_entities}
    assert set(created) == {"203.0.113.45", "http://203.0.113.45/s2", "44d88612fea8a8f36de82e1278abb02f", "stage2.dll"}
    assert created["203.0.113.45"]["entity_type"] == "ADDRESS"
    assert created["203.0.113.45"]["is_suspicious"] is True
    assert created["203.0.113.45"]["properties"]["Claude_indicator_type"] == "ip_addresses"
    assert created["44d88612fea8a8f36de82e1278abb02f"]["entity_type"] == "FILEHASH"
    assert created["44d88612fea8a8f36de82e1278abb02f"]["properties"]["Claude_hash_type"] == "MD5"
    assert created["http://203.0.113.45/s2"]["entity_type"] == "DestinationURL"
    assert created["stage2.dll"]["entity_type"] == "FILENAME"


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters={"Text": "Nothing to see here."})
def test_extract_indicators_none_found(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_structured(EMPTY)

    extract_indicators.main()

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message == "Claude did not find any indicators in the provided text."


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters={"Text": "   "})
def test_extract_indicators_empty_text(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    extract_indicators.main()

    assert claude_api.requests == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert '"Text" must not be empty' in action_output.results.output_message
