from __future__ import annotations

import json
from typing import TYPE_CHECKING

from integration_testing.set_meta import set_metadata
from TIPCommon.base.action import ExecutionState

from claude.actions import ask_claude
from claude.core.prompts import DEFAULT_ASK_SYSTEM_PROMPT
from claude.tests.common import CONFIG_PATH, MOCK_MODEL_ID, MOCK_REQUEST_ID, build_input_context
from claude.tests.core.mock_data import ALERT_NAME, EVENT_COMMAND_LINE

if TYPE_CHECKING:
    from integration_testing.platform.script_output import MockActionOutput
    from TIPCommon.types import SingleJson

    from claude.tests.core.product import ClaudeMockApi, SoarMockPlatform


PROMPT: str = "Is the command line powershell -enc malicious?"
ANSWER: str = "Yes. Encoded PowerShell launched from Office is a common loader pattern.\nIsolate the host."
DEFAULT_PARAMETERS: SingleJson = {"Prompt": PROMPT}


def _json_result(action_output: MockActionOutput) -> SingleJson:
    return action_output.results.json_output.json_result


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters=DEFAULT_PARAMETERS)
def test_ask_claude_success(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text(ANSWER)

    ask_claude.main()

    request: SingleJson = claude_api.last_request
    assert request["model"] == MOCK_MODEL_ID
    assert request["max_tokens"] == 8192
    assert request["system"] == DEFAULT_ASK_SYSTEM_PROMPT
    assert request["messages"] == [{"role": "user", "content": PROMPT}]
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "high"}

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert action_output.results.output_message == (
        f"Successfully received a response from Claude. Model: {MOCK_MODEL_ID}, output tokens: 45."
    )
    result: SingleJson = _json_result(action_output)
    assert result["response"] == ANSWER
    assert result["model"] == MOCK_MODEL_ID
    assert result["stop_reason"] == "end_turn"
    assert result["is_truncated"] is False
    assert result["request_id"] == MOCK_REQUEST_ID
    assert result["usage"]["output_tokens"] == 45
    assert result["prompt_preview"] == PROMPT
    assert "structured_output" not in result


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={
        "Prompt": PROMPT,
        "System Prompt": "Answer in one word.",
        "Model": "claude-sonnet-5",
        "Max Output Tokens": "512",
        "Effort": "low",
    },
)
def test_ask_claude_overrides(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text("Yes.")

    ask_claude.main()

    request: SingleJson = claude_api.last_request
    assert request["model"] == "claude-sonnet-5"
    assert request["max_tokens"] == 512
    assert request["system"] == "Answer in one word."
    assert request["output_config"] == {"effort": "low"}
    assert action_output.results.execution_state == ExecutionState.COMPLETED


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    integration_config={
        "API Root": "https://api.anthropic.com",
        "API Key": "sk-ant-test",
        "Model": "claude-haiku-4-5",
        "Max Output Tokens": 1024,
        "Effort": "Default",
        "Adaptive Thinking": "false",
        "Request Timeout": 60,
        "Verify SSL": True,
    },
    parameters=DEFAULT_PARAMETERS,
)
def test_ask_claude_without_thinking_and_effort(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text("Yes.")

    ask_claude.main()

    request: SingleJson = claude_api.last_request
    assert "thinking" not in request
    assert "output_config" not in request
    assert action_output.results.execution_state == ExecutionState.COMPLETED


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={
        "Prompt": PROMPT,
        "JSON Schema": json.dumps({
            "type": "object",
            "properties": {"is_malicious": {"type": "boolean"}},
            "required": ["is_malicious"],
            "additionalProperties": False,
        }),
    },
)
def test_ask_claude_structured_output(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_structured({"is_malicious": True})

    ask_claude.main()

    request: SingleJson = claude_api.last_request
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["output_config"]["format"]["schema"]["properties"] == {"is_malicious": {"type": "boolean"}}
    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert _json_result(action_output)["structured_output"] == {"is_malicious": True}


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={"Prompt": PROMPT, "JSON Schema": '{"type": "array"}'},
)
def test_ask_claude_invalid_json_schema(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    ask_claude.main()

    assert claude_api.requests == []
    assert action_output.results.execution_state == ExecutionState.FAILED
    assert '"JSON Schema" must be a JSON Schema object' in action_output.results.output_message


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={"Prompt": PROMPT, "Create Insight": True, "Add Comment": True},
    input_context=build_input_context(),
)
def test_ask_claude_creates_insight_and_comment(
    action_output: MockActionOutput,
    claude_api: ClaudeMockApi,
    soar_platform: SoarMockPlatform,
) -> None:
    claude_api.queue_text(ANSWER)

    ask_claude.main()

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert len(soar_platform.insights) == 1
    insight: SingleJson = soar_platform.insights[0]
    assert insight["title"] == "Claude Response"
    assert insight["triggered_by"] == "Claude"
    assert insight["content"] == ANSWER.replace("\n", "<br>")
    assert len(soar_platform.comments) == 1
    assert soar_platform.comments[0]["comment"] == f"Claude Response:\n{ANSWER}"


@set_metadata(
    integration_config_file_path=CONFIG_PATH,
    parameters={"Prompt": PROMPT, "Include Alert Context": True},
    input_context=build_input_context(),
)
def test_ask_claude_includes_alert_context(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text(ANSWER)

    ask_claude.main()

    content: str = claude_api.last_request["messages"][0]["content"]
    assert content.startswith(PROMPT)
    assert "<alert_data>" in content and "</alert_data>" in content
    assert ALERT_NAME in content
    assert EVENT_COMMAND_LINE in content
    assert action_output.results.execution_state == ExecutionState.COMPLETED


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters=DEFAULT_PARAMETERS)
def test_ask_claude_refusal(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_refusal(category="cyber", explanation="This request was declined.")

    ask_claude.main()

    assert action_output.results.execution_state == ExecutionState.FAILED
    assert "Claude declined to process the request (category: cyber): This request was declined." in (
        action_output.results.output_message
    )


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters=DEFAULT_PARAMETERS)
def test_ask_claude_truncated_response(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.queue_text("Partial answer", stop_reason="max_tokens")

    ask_claude.main()

    assert action_output.results.execution_state == ExecutionState.COMPLETED
    assert _json_result(action_output)["is_truncated"] is True
    assert action_output.results.output_message.endswith("cut off by the max output tokens limit.")


@set_metadata(integration_config_file_path=CONFIG_PATH, parameters=DEFAULT_PARAMETERS)
def test_ask_claude_api_error(action_output: MockActionOutput, claude_api: ClaudeMockApi) -> None:
    claude_api.fail_next(status_code=400, error_type="invalid_request_error", message="model: unknown model")

    ask_claude.main()

    assert action_output.results.execution_state == ExecutionState.FAILED
    assert "The Claude API rejected the request (HTTP 400): model: unknown model" in (
        action_output.results.output_message
    )
