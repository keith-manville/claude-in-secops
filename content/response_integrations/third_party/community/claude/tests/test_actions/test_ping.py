from __future__ import annotations

from typing import TYPE_CHECKING

from integration_testing.set_meta import set_metadata
from TIPCommon.base.action import ExecutionState

from claude.actions import ping
from claude.tests.common import CONFIG_PATH, MOCK_MODEL_ID

if TYPE_CHECKING:
    from integration_testing.platform.script_output import MockActionOutput

    from claude.tests.core.product import ClaudeMockApi


class TestPing:
    @set_metadata(integration_config_file_path=CONFIG_PATH)
    def test_ping_success(self, action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
        ping.main()

        assert claude_api.model_requests == [MOCK_MODEL_ID]
        assert action_output.results.execution_state == ExecutionState.COMPLETED
        assert action_output.results.result_value is True
        assert action_output.results.output_message == (
            "Successfully connected to the Claude API with the provided connection parameters! "
            f"Provider: Anthropic API, model: {MOCK_MODEL_ID}"
        )

    @set_metadata(integration_config_file_path=CONFIG_PATH)
    def test_ping_invalid_api_key(self, action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
        with claude_api.fail_requests(status_code=401, error_type="authentication_error"):
            ping.main()

        assert action_output.results.execution_state == ExecutionState.FAILED
        assert action_output.results.result_value is False
        assert action_output.results.output_message.startswith("Failed to connect to the Claude API!")
        assert "Authentication with the Claude API failed" in action_output.results.output_message
        assert "HTTP 401" in action_output.results.output_message

    @set_metadata(
        integration_config_file_path=CONFIG_PATH,
        integration_config={
            "API Root": "https://api.anthropic.com",
            "API Key": "",
            "Model": "claude-opus-5",
            "Max Output Tokens": 8192,
            "Request Timeout": 300,
            "Verify SSL": True,
        },
    )
    def test_ping_missing_api_key_fails_validation(self, action_output: MockActionOutput) -> None:
        ping.main()

        assert action_output.results.execution_state == ExecutionState.FAILED
        assert '"API Key" must be provided when "Provider" is "Anthropic API"' in action_output.results.output_message

    @set_metadata(
        integration_config_file_path=CONFIG_PATH,
        integration_config={
            "API Root": "https://api.anthropic.com",
            "API Key": "sk-ant-test",
            "Model": "claude-opus-5",
            "Max Output Tokens": 999999,
            "Request Timeout": 300,
            "Verify SSL": True,
        },
    )
    def test_ping_max_tokens_out_of_range_fails_validation(self, action_output: MockActionOutput) -> None:
        ping.main()

        assert action_output.results.execution_state == ExecutionState.FAILED
        assert '"Max Output Tokens" must be between' in action_output.results.output_message
