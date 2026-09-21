from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import anthropic
from TIPCommon.extraction import extract_script_param

from .constants import (
    CLOUD_PLATFORM_SCOPE,
    DEFAULT_ADAPTIVE_THINKING,
    DEFAULT_API_ROOT,
    DEFAULT_EFFORT,
    DEFAULT_GCP_REGION,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_VERIFY_SSL,
    INTEGRATION_IDENTIFIER,
    MAX_OUTPUT_TOKENS_LIMIT,
    MAX_RETRIES,
    MIN_OUTPUT_TOKENS,
    SERVICE_ACCOUNT_TYPE,
    EffortEnum,
    ProviderEnum,
)
from .data_models import IntegrationParameters
from .exceptions import ClaudeIntegrationError, ClaudeInvalidParameterError

if TYPE_CHECKING:
    from google.auth.credentials import Credentials
    from TIPCommon.types import ChronicleSOAR, SingleJson

# Class names of the SOAR SDK objects that can carry the integration configuration.
# Compared by name so this manager module does not import from the SDK.
ACTION_SDK_CLASS: str = "SiemplifyAction"
PARAMETER_BASED_SDK_CLASSES: frozenset[str] = frozenset({"SiemplifyConnectorExecution", "SiemplifyJob"})

ClaudeClient = anthropic.Anthropic | anthropic.AnthropicVertex


def build_auth_params(soar_sdk_object: ChronicleSOAR) -> IntegrationParameters:
    """Extract the integration configuration parameters from the SOAR SDK object.

    Args:
        soar_sdk_object: The SiemplifyAction, SiemplifyConnectorExecution or SiemplifyJob object.

    Returns:
        The integration parameters.

    Raises:
        ClaudeIntegrationError: If the SDK object type is not supported.
        ClaudeInvalidParameterError: If the configuration is invalid.
    """
    sdk_class: str = type(soar_sdk_object).__name__
    input_dictionary: SingleJson
    if sdk_class == ACTION_SDK_CLASS:
        input_dictionary = soar_sdk_object.get_configuration(INTEGRATION_IDENTIFIER)
    elif sdk_class in PARAMETER_BASED_SDK_CLASSES:
        input_dictionary = soar_sdk_object.parameters
    else:
        raise ClaudeIntegrationError(f"Provided SOAR instance is not supported! type: {sdk_class}.")

    def extract(name: str, **kwargs: Any) -> Any:  # noqa: ANN401
        return extract_script_param(soar_sdk_object, input_dictionary=input_dictionary, param_name=name, **kwargs)

    provider_value: str = extract("Provider", default_value=DEFAULT_PROVIDER, print_value=True)
    api_root: str = extract("API Root", default_value=DEFAULT_API_ROOT, print_value=True)
    api_key: str | None = extract("API Key")
    gcp_project_id: str | None = extract("GCP Project ID", print_value=True)
    gcp_region: str = extract("GCP Region", default_value=DEFAULT_GCP_REGION, print_value=True)
    service_account_json: str | None = extract("Service Account JSON")
    model: str = extract("Model", default_value=DEFAULT_MODEL, is_mandatory=True, print_value=True)
    max_output_tokens: int = extract(
        "Max Output Tokens",
        default_value=DEFAULT_MAX_OUTPUT_TOKENS,
        input_type=int,
        is_mandatory=True,
        print_value=True,
    )
    effort: str = extract("Effort", default_value=DEFAULT_EFFORT, print_value=True)
    adaptive_thinking: bool = extract(
        "Adaptive Thinking",
        default_value=DEFAULT_ADAPTIVE_THINKING,
        input_type=bool,
        print_value=True,
    )
    request_timeout: int = extract(
        "Request Timeout",
        default_value=DEFAULT_REQUEST_TIMEOUT,
        input_type=int,
        is_mandatory=True,
        print_value=True,
    )
    verify_ssl: bool = extract(
        "Verify SSL",
        default_value=DEFAULT_VERIFY_SSL,
        input_type=bool,
        is_mandatory=True,
        print_value=True,
    )

    try:
        provider: ProviderEnum = ProviderEnum.from_value(provider_value)
        resolved_effort: EffortEnum = EffortEnum.from_value(effort)
    except ValueError as error:
        raise ClaudeInvalidParameterError(str(error)) from error

    params: IntegrationParameters = IntegrationParameters(
        provider=provider.value,
        api_root=(api_root or DEFAULT_API_ROOT).rstrip("/"),
        api_key=(api_key or "").strip(),
        gcp_project_id=(gcp_project_id or "").strip(),
        gcp_region=(gcp_region or DEFAULT_GCP_REGION).strip(),
        service_account_info=parse_service_account_json(service_account_json),
        model=model.strip(),
        max_output_tokens=max_output_tokens,
        effort=resolved_effort.value,
        adaptive_thinking=adaptive_thinking,
        request_timeout=request_timeout,
        verify_ssl=verify_ssl,
    )
    validate_auth_params(params)
    return params


def parse_service_account_json(raw: str | None) -> SingleJson | None:
    """Parse the contents of a Google service account key file.

    Args:
        raw: The JSON text, or None/empty when not configured.

    Returns:
        The parsed key file, or None when not configured.

    Raises:
        ClaudeInvalidParameterError: If the value is not a service account key file.
    """
    if raw is None or not raw.strip():
        return None

    try:
        info: Any = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ClaudeInvalidParameterError(
            f'"Service Account JSON" is not valid JSON: {error.msg} (line {error.lineno}, column {error.colno}).'
        ) from error

    if not isinstance(info, dict) or info.get("type") != SERVICE_ACCOUNT_TYPE:
        raise ClaudeInvalidParameterError(
            '"Service Account JSON" must be the contents of a service account key file '
            f'(a JSON object with "type": "{SERVICE_ACCOUNT_TYPE}").'
        )

    missing: list[str] = [field for field in ("client_email", "private_key", "token_uri") if not info.get(field)]
    if missing:
        raise ClaudeInvalidParameterError(
            f'"Service Account JSON" is missing the required field(s): {", ".join(missing)}.'
        )

    return info


def validate_auth_params(params: IntegrationParameters) -> None:
    """Validate the integration configuration parameters.

    Args:
        params: The integration parameters.

    Raises:
        ClaudeInvalidParameterError: If any parameter is missing or out of range.
    """
    if params.provider == ProviderEnum.ANTHROPIC.value:
        if not params.api_key:
            raise ClaudeInvalidParameterError('"API Key" must be provided when "Provider" is "Anthropic API".')
    elif params.provider == ProviderEnum.VERTEX.value:
        if not params.gcp_project_id:
            raise ClaudeInvalidParameterError('"GCP Project ID" must be provided when "Provider" is "Vertex AI".')
        if not params.gcp_region:
            raise ClaudeInvalidParameterError('"GCP Region" must be provided when "Provider" is "Vertex AI".')

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


def build_vertex_credentials(service_account_info: SingleJson | None) -> Credentials | None:
    """Build Google credentials for Vertex AI from a service account key.

    Kept as a separate function so tests can replace the credentials.

    Args:
        service_account_info: The parsed service account key file, or None to use
            Application Default Credentials.

    Returns:
        Scoped service account credentials, or None to let the SDK resolve
        Application Default Credentials.
    """
    if service_account_info is None:
        return None

    from google.oauth2 import service_account  # noqa: PLC0415

    return service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=[CLOUD_PLATFORM_SCOPE],
    )


def create_client(params: IntegrationParameters) -> ClaudeClient:
    """Create an authenticated client for the configured provider.

    Args:
        params: The integration parameters.

    Returns:
        An `anthropic.Anthropic` client for the Anthropic API, or an
        `anthropic.AnthropicVertex` client for Claude on Vertex AI.
    """
    if params.provider == ProviderEnum.VERTEX.value:
        return anthropic.AnthropicVertex(
            project_id=params.gcp_project_id,
            region=params.gcp_region,
            credentials=build_vertex_credentials(params.service_account_info),
            timeout=float(params.request_timeout),
            max_retries=MAX_RETRIES,
            http_client=build_http_client(params.verify_ssl),
        )

    return anthropic.Anthropic(
        api_key=params.api_key,
        base_url=params.api_root,
        timeout=float(params.request_timeout),
        max_retries=MAX_RETRIES,
        http_client=build_http_client(params.verify_ssl),
    )
