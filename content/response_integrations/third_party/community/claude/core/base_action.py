from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from TIPCommon.base.action import Action
from TIPCommon.base.action.data_models import CaseInsight, EntityInsight, InsightSeverity, InsightType
from TIPCommon.extraction import extract_action_param
from TIPCommon.validation import ParameterValidator

from .api_client import ApiParameters, ClaudeApiClient
from .auth import build_auth_params, create_client
from .constants import (
    INSIGHT_TRIGGERED_BY,
    MAX_OUTPUT_TOKENS_LIMIT,
    MIN_OUTPUT_TOKENS,
    EffortEnum,
)
from .exceptions import ClaudeInvalidParameterError

if TYPE_CHECKING:
    from TIPCommon.types import Entity

    from .data_models import IntegrationParameters


EFFORT_PARAM_NAME: str = "Effort"
MODEL_PARAM_NAME: str = "Model"
MAX_OUTPUT_TOKENS_PARAM_NAME: str = "Max Output Tokens"


class ClaudeAction(Action, ABC):
    """Base class for all Claude actions."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.integration_params: IntegrationParameters | None = None

    def _init_api_clients(self) -> ClaudeApiClient:
        """Prepare the Claude API client from the integration configuration."""
        self.integration_params = build_auth_params(self.soar_action)
        api_params: ApiParameters = ApiParameters(
            provider=self.integration_params.provider,
            model=self.integration_params.model,
            max_output_tokens=self.integration_params.max_output_tokens,
            effort=self.integration_params.effort,
            adaptive_thinking=self.integration_params.adaptive_thinking,
        )
        return ClaudeApiClient(
            authenticated_session=create_client(self.integration_params),
            configuration=api_params,
            logger=self.logger,
        )

    # ==================== Shared parameter helpers ==================== #

    def _extract_effort_param(self) -> None:
        self.params.effort = extract_action_param(
            self.soar_action,
            param_name=EFFORT_PARAM_NAME,
            default_value=EffortEnum.DEFAULT.value,
            print_value=True,
        )

    def _validate_effort_param(self, validator: ParameterValidator) -> None:
        self.params.effort = validator.validate_ddl(
            param_name=EFFORT_PARAM_NAME,
            value=self.params.effort,
            ddl_values=EffortEnum.values(),
            print_value=True,
        )

    def _extract_model_override_params(self) -> None:
        self.params.model = extract_action_param(
            self.soar_action,
            param_name=MODEL_PARAM_NAME,
            print_value=True,
        )
        self.params.max_output_tokens = extract_action_param(
            self.soar_action,
            param_name=MAX_OUTPUT_TOKENS_PARAM_NAME,
            print_value=True,
        )

    def _validate_model_override_params(self, validator: ParameterValidator) -> None:
        self.params.model = (self.params.model or "").strip() or None
        if self.params.max_output_tokens in (None, ""):
            self.params.max_output_tokens = None
            return

        self.params.max_output_tokens = validator.validate_range(
            param_name=MAX_OUTPUT_TOKENS_PARAM_NAME,
            value=validator.validate_integer(
                param_name=MAX_OUTPUT_TOKENS_PARAM_NAME,
                value=self.params.max_output_tokens,
                print_value=True,
            ),
            min_limit=MIN_OUTPUT_TOKENS,
            max_limit=MAX_OUTPUT_TOKENS_LIMIT,
            print_value=True,
        )

    @staticmethod
    def _validate_positive_int(validator: ParameterValidator, param_name: str, value: str, max_limit: int) -> int:
        parsed: int = validator.validate_integer(param_name=param_name, value=value, print_value=True)
        return validator.validate_range(
            param_name=param_name,
            value=parsed,
            min_limit=1,
            max_limit=max_limit,
            print_value=True,
        )

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise ClaudeInvalidParameterError(message)

    # ==================== Case wall helpers ==================== #

    def _add_case_insight(
        self,
        title: str,
        content: str,
        severity: int = InsightSeverity.INFO,
    ) -> None:
        """Queue a general case insight to be created when the action ends.

        Args:
            title: The insight title.
            content: The insight HTML content.
            severity: The insight severity (`InsightSeverity`).
        """
        self.case_insights.append(
            CaseInsight(
                triggered_by=INSIGHT_TRIGGERED_BY,
                title=title,
                content=content,
                severity=severity,
                insight_type=InsightType.General,
            )
        )

    def _add_entity_insight(self, entity: Entity, message: str) -> None:
        """Queue an entity insight to be created when the action ends.

        Args:
            entity: The entity the insight relates to.
            message: The insight HTML content.
        """
        self.entity_insights.append(
            EntityInsight(
                entity=entity,
                message=message,
                triggered_by=INSIGHT_TRIGGERED_BY,
            )
        )

    def _add_case_comment(self, comment: str) -> None:
        """Add a comment to the current case.

        Args:
            comment: The comment text.
        """
        self._add_comment_to_case(comment=comment)

    @property
    def result_value(self) -> bool:
        return self._result_value

    @result_value.setter
    def result_value(self, value: bool) -> None:
        self._result_value = value
