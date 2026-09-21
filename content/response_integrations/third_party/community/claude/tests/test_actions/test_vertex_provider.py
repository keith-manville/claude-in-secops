from __future__ import annotations

import json
from typing import TYPE_CHECKING

from integration_testing.set_meta import set_metadata
from TIPCommon.base.action import ExecutionState

from claude.actions import ask_claude, ping
from claude.tests.common import (
    CONFIG_PATH,
    MOCK_MODEL_ID,
    MOCK_VERTEX_PROJECT,
    MOCK_VERTEX_REGION,
    vertex_config,
)

if TYPE_CHECKING:
    from integration_testing.platform.script_output import MockActionOutput
    from TIPCommon.types import SingleJson

    from claude.tests.core.product import ClaudeMockApi, FakeGoogleCredentials


VERTEX_MODELS_PREFIX: str = (
    f"/v1/projects/{MOCK_VERTEX_PROJECT}/locations/{MOCK_VERTEX_REGION}/publishers/anthropic/models/"
)


@set_metadata(integration_config_file_path=CONFIG_PATH, integration_config=vertex_config())
def test_ping_vertex_uses_count_tokens(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    vertex_credentials: FakeGoogleCredentials,
) -> None:
    ping.main()

    assert claude_api.model_requests == []
    assert claude_api.request_paths == [f"{VERTEX_MODELS_PREFIX}count-tokens:rawPredict"]
    assert claude_api.request_headers[0]["authorization"] == f"Bearer {vertex_credentials.token}"
    assert claude_api.count_token_requests[0]["messages"] == [{"role": "user", "content": "ping"}]
    assert claude_api.count_token_requests[0]["model"] == MOCK_MODEL_ID

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message == (
        "Successfully connected to the Claude API with the provided connection parameters! "
        f"Provider: Vertex AI, model: {MOCK_MODEL_ID}"
    )


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    integration_config=vertex_config(),
    parameters={"Prompt": "Is 203.0.113.45 malicious?"},
)
def test_ask_claude_vertex_uses_raw_predict(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text("Unknown from the data provided.")

    ask_claude.main()

    assert claude_api.request_paths == [f"{VERTEX_MODELS_PREFIX}{MOCK_MODEL_ID}:rawPredict"]
    request: SingleJson = claude_api.last_request
    assert "model" not in request
    assert request["anthropic_version"] == "vertex-2023-10-16"
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "high"}
    assert request["messages"] == [{"role": "user", "content": "Is 203.0.113.45 malicious?"}]

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.json_output.json_result["model"] == MOCK_MODEL_ID
    assert action_output.results.json_output.json_result["response"] == "Unknown from the data provided."


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    integration_config=vertex_config(**{"Service Account JSON": ""}),
)
def test_ping_vertex_without_service_account_uses_default_credentials(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
) -> None:
    ping.main()

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert len(claude_api.count_token_requests) == 1


@set_metadata(integration_config_file_path=CONFIG_PATH, integration_config=vertex_config(**{"GCP Project ID": ""}))
def test_ping_vertex_requires_project(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    ping.main()

    assert claude_api.request_paths == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert '"GCP Project ID" must be provided when "Provider" is "Vertex AI"' in action_output.results.output_message


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    integration_config=vertex_config(**{"Service Account JSON": "{not json"}),
)
def test_ping_vertex_rejects_invalid_service_account_json(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
) -> None:
    ping.main()

    assert claude_api.request_paths == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert '"Service Account JSON" is not valid JSON' in action_output.results.output_message


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    integration_config=vertex_config(**{"Service Account JSON": json.dumps({"type": "authorized_user"})}),
)
def test_ping_vertex_rejects_non_service_account_key(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
) -> None:
    ping.main()

    assert claude_api.request_paths == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert '"Service Account JSON" must be the contents of a service account key file' in (
        action_output.results.output_message
    )


@set_metadata(integration_config_file_path=CONFIG_PATH, integration_config=vertex_config(Model="claude-nope"))
def test_ping_vertex_unknown_model(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.fail_next(status_code=404, error_type="not_found_error", message="Publisher Model not found")

    ping.main()

    assert action_output.results.execution_state == ExecutionState.FAILED
    assert "The requested resource was not found" in action_output.results.output_message
    assert "HTTP 404" in action_output.results.output_message


@set_metadata(integration_config_file_path=CONFIG_PATH, integration_config=vertex_config(Provider="Bedrock"))
def test_ping_rejects_unknown_provider(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    ping.main()

    assert claude_api.request_paths == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert "Unsupported provider: 'Bedrock'" in action_output.results.output_message


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    integration_config={
        "Provider": "Anthropic API",
        "API Root": "https://api.anthropic.com",
        "API Key": "",
        "GCP Project ID": MOCK_VERTEX_PROJECT,
        "Model": MOCK_MODEL_ID,
        "Max Output Tokens": 8192,
        "Request Timeout": 300,
        "Verify SSL": True,
    },
)
def test_ping_anthropic_requires_api_key(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    ping.main()

    assert claude_api.request_paths == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert '"API Key" must be provided when "Provider" is "Anthropic API"' in action_output.results.output_message
