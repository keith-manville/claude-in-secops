from __future__ import annotations

import json
import pathlib
import time

INTEGRATION_PATH: pathlib.Path = pathlib.Path(__file__).parent.parent
CONFIG_PATH: pathlib.Path = pathlib.Path.joinpath(INTEGRATION_PATH, "tests", "config.json")

MOCK_REQUEST_ID: str = "req_test_0123456789"
MOCK_MODEL_ID: str = "claude-opus-5"
MOCK_VERTEX_PROJECT: str = "secops-demo-project"
MOCK_VERTEX_REGION: str = "global"
MOCK_SERVICE_ACCOUNT: dict = {
    "type": "service_account",
    "project_id": MOCK_VERTEX_PROJECT,
    "private_key_id": "abc123",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n",
    "client_email": "soar-claude@secops-demo-project.iam.gserviceaccount.com",
    "client_id": "1234567890",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def build_input_context(case_id: int = 1, alert_id: str = "ALERT-1") -> dict:
    """Build a fresh script input context bound to a case and alert.

    A new dictionary is returned on every call because `set_metadata` stores the
    action parameters inside the context it receives.

    Args:
        case_id: The case identifier.
        alert_id: The alert identifier.

    Returns:
        The input context dictionary.
    """
    deadline: int = int(time.time() * 1000) + 10 * 60 * 1000
    return {"case_id": case_id, "alert_id": alert_id, "execution_deadline_unix_time_ms": deadline}


def vertex_config(**overrides: object) -> dict:
    """Build an integration configuration that targets Claude on Vertex AI.

    Args:
        overrides: Parameter values that replace the defaults.

    Returns:
        The configuration dictionary.
    """
    config: dict = {
        "Provider": "Vertex AI",
        "API Root": "https://api.anthropic.com",
        "API Key": "",
        "GCP Project ID": MOCK_VERTEX_PROJECT,
        "GCP Region": MOCK_VERTEX_REGION,
        "Service Account JSON": json.dumps(MOCK_SERVICE_ACCOUNT),
        "Model": MOCK_MODEL_ID,
        "Max Output Tokens": 8192,
        "Effort": "high",
        "Adaptive Thinking": True,
        "Request Timeout": 300,
        "Verify SSL": True,
    }
    config.update(overrides)
    return config
