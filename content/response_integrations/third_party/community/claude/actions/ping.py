from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.base_action import ClaudeAction
from ..core.constants import PING_SCRIPT_NAME

if TYPE_CHECKING:
    from typing import NoReturn

    from TIPCommon.types import SingleJson


SUCCESS_MESSAGE: str = (
    "Successfully connected to the Claude API with the provided connection parameters! Model: {model}"
)
ERROR_MESSAGE: str = "Failed to connect to the Claude API!"


class Ping(ClaudeAction):
    def __init__(self) -> None:
        super().__init__(PING_SCRIPT_NAME)
        self.output_message: str = SUCCESS_MESSAGE
        self.error_output_message: str = ERROR_MESSAGE

    def _perform_action(self, _=None) -> None:
        model_info: SingleJson = self.api_client.test_connectivity()
        self.output_message = SUCCESS_MESSAGE.format(model=model_info["id"])


def main() -> NoReturn:
    Ping().run()


if __name__ == "__main__":
    main()
