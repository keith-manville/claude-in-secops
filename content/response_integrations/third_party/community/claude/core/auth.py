from __future__ import annotations

from typing import TYPE_CHECKING

import anthropic
from soar_sdk.SiemplifyAction import SiemplifyAction
from soar_sdk.SiemplifyConnectors import SiemplifyConnectorExecution
from soar_sdk.SiemplifyJob import SiemplifyJob
from TIPCommon.extraction import extract_script_param

from .constants import (
    DEFAULT_ADAPTIVE_THINKING,
    DEFAULT_API_ROOT,
    DEFAULT_EFFORT,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_VERIFY_SSL,
    INTEGRATION_IDENTIFIER,
    MAX_OUTPUT_TOKENS_LIMIT,
    MAX_RETRIES,
    MIN_OUTPUT_TOKENS,
    EffortEnum,
)
from .data_models import IntegrationParameters
from .exceptions import ClaudeIntegrationError, ClaudeInvalidParameterError

if TYPE_CHECKING:
    from TIPCommon.types import ChronicleSOAR, SingleJson


def build_auth_params(soar_sdk_object: ChronicleSOAR) -> IntegrationParameters:
    """Extract the integration configuration parameters from the SOAR SDK object.

    Args:
        soar_sdk_object: The SiemplifyAction, SiemplifyConnectorExecution or SiemplifyJob object.

    Returns:
        The integration parameters.

    Raises:
        ClaudeIntegrationError: If the SDK object type is not supported.
    """
    sdk_class: str = type(soar_sdk_object).__name__
    input_dictionary: SingleJson
    if sdk_class == SiemplifyAction.__name__:
        input_dictionary = soar_sdk_object.get_configuration(INTEGRATION_IDENTIFIER)
    elif sdk_class in (SiemplifyConnectorExecution.__name__, SiemplifyJob.__name__):
        input_dictionary = soar_sdk_object.parameters
    else:
        raise ClaudeIntegrationError(f"Provided SOAR instance is not supported! type: {sdk_class}.")

    api_root: str = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="API Root",
        default_value=DEFAULT_API_ROOT,
        is_mandatory=True,
        print_value=True,
    )
    api_key: str = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="API Key",
        is_mandatory=True,
    )
    model: str = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="Model",
        default_value=DEFAULT_MODEL,
        is_mandatory=True,
        print_value=True,
    )
    max_output_tokens: int = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="Max Output Tokens",
        default_value=DEFAULT_MAX_OUTPUT_TOKENS,
        input_type=int,
        is_mandatory=True,
        print_value=True,
    )
    effort: str = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="Effort",
        default_value=DEFAULT_EFFORT,
        print_value=True,
    )
    adaptive_thinking: bool = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="Adaptive Thinking",
        default_value=DEFAULT_ADAPTIVE_THINKING,
        input_type=bool,
        print_value=True,
    )
    request_timeout: int = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="Request Timeout",
        default_value=DEFAULT_REQUEST_TIMEOUT,
        input_type=int,
        is_mandatory=True,
        print_value=True,
    )
    verify_ssl: bool = extract_script_param(
        soar_sdk_object,
        input_dictionary=input_dictionary,
        param_name="Verify SSL",
        default_value=DEFAULT_VERIFY_SSL,
        input_type=bool,
        is_mandatory=True,
        print_value=True,
    )

    params: IntegrationParameters = IntegrationParameters(
        api_root=api_root.rstrip("/"),
        api_key=api_key,
        model=model.strip(),
        max_output_tokens=max_output_tokens,
        effort=EffortEnum.from_value(effort).value,
        adaptive_thinking=adaptive_thinking,
        request_timeout=request_timeout,
        verify_ssl=verify_ssl,
    )
    validate_auth_params(params)
    return params


def validate_auth_params(params: IntegrationParameters) -> None:
    """Validate the integration configuration parameters.

    Args:
        params: The integration parameters.

    Raises:
        ClaudeInvalidParameterError: If any parameter is out of range.
    """
    if not params.api_key:
        raise ClaudeInvalidParameterError('"API Key" must be provided.')

    if not params.model:
        raise ClaudeInvalidParameterError('"Model" must be provided.')

    if not MIN_OUTPUT_TOKENS <= params.max_output_tokens <= MAX_OUTPUT_TOKENS_LIMIT:
        raise ClaudeInvalidParameterError(
            f'"Max Output Tokens" must be between {MIN_OUTPUT_TOKENS} and {MAX_OUTPUT_TOKENS_LIMIT}.'
        )

    if params.request_timeout <= 0:
        raise ClaudeInvalidParameterError('"Request Timeout" must be a positive number of seconds.')


def build_http_client(verify_ssl: bool) -> anthropic.DefaultHttpxClient:
    """Build the HTTP client used by the Anthropic SDK.

    Kept as a separate function so tests can replace the transport.

    Args:
        verify_ssl: Whether to validate the API's SSL certificate.

    Returns:
        An HTTP client with the SDK's default limits and timeouts.
    """
    return anthropic.DefaultHttpxClient(verify=verify_ssl)


def create_client(params: IntegrationParameters) -> anthropic.Anthropic:
    """Create an authenticated Anthropic client from the integration parameters.

    Args:
        params: The integration parameters.

    Returns:
        A configured `anthropic.Anthropic` client.
    """
    return anthropic.Anthropic(
        api_key=params.api_key,
        base_url=params.api_root,
        timeout=float(params.request_timeout),
        max_retries=MAX_RETRIES,
        http_client=build_http_client(params.verify_ssl),
    )
