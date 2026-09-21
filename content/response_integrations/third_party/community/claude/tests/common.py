from __future__ import annotations

import pathlib
import time

INTEGRATION_PATH: pathlib.Path = pathlib.Path(__file__).parent.parent
CONFIG_PATH: pathlib.Path = pathlib.Path.joinpath(INTEGRATION_PATH, "tests", "config.json")

MOCK_REQUEST_ID: str = "req_test_0123456789"
MOCK_MODEL_ID: str = "claude-opus-5"


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
