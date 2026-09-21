from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from TIPCommon.base.action import EntityTypesEnum

if TYPE_CHECKING:
    from collections.abc import Mapping


# Integration Identifiers
INTEGRATION_IDENTIFIER: str = "Claude"
INTEGRATION_DISPLAY_NAME: str = "Claude"

# Script Identifiers
PING_SCRIPT_NAME: str = f"{INTEGRATION_IDENTIFIER} - Ping"
ASK_CLAUDE_SCRIPT_NAME: str = f"{INTEGRATION_IDENTIFIER} - Ask Claude"
SUMMARIZE_ALERT_SCRIPT_NAME: str = f"{INTEGRATION_IDENTIFIER} - Summarize Alert"
ASSESS_ENTITIES_SCRIPT_NAME: str = f"{INTEGRATION_IDENTIFIER} - Assess Entities"
EXTRACT_INDICATORS_SCRIPT_NAME: str = f"{INTEGRATION_IDENTIFIER} - Extract Indicators"

# Default Configuration Parameter Values
DEFAULT_API_ROOT: str = "https://api.anthropic.com"
DEFAULT_MODEL: str = "claude-opus-5"
DEFAULT_MAX_OUTPUT_TOKENS: int = 8192
DEFAULT_EFFORT: str = "high"
DEFAULT_ADAPTIVE_THINKING: bool = True
DEFAULT_REQUEST_TIMEOUT: int = 300
DEFAULT_VERIFY_SSL: bool = True

# Limits
# The Anthropic SDK refuses non-streaming requests that could take longer than
# 10 minutes to complete, which is roughly 21,333 output tokens.
MAX_OUTPUT_TOKENS_LIMIT: int = 20_000
MIN_OUTPUT_TOKENS: int = 1
MAX_RETRIES: int = 2
DEFAULT_MAX_EVENTS: int = 25
MAX_EVENTS_LIMIT: int = 200
MAX_FIELD_CHARS: int = 1_000
MAX_CONTEXT_CHARS: int = 150_000
MAX_INSIGHT_CHARS: int = 15_000
MAX_ENRICHMENT_VALUE_CHARS: int = 2_000

# Platform constants
INSIGHT_TRIGGERED_BY: str = INTEGRATION_IDENTIFIER
ENRICHMENT_PREFIX: str = f"{INTEGRATION_IDENTIFIER}_"
JSON_RESULT_MODEL_KEY: str = "model"
JSON_RESULT_USAGE_KEY: str = "usage"

# Refusal stop reason returned by Claude's safety classifiers.
REFUSAL_STOP_REASON: str = "refusal"
MAX_TOKENS_STOP_REASON: str = "max_tokens"
TEXT_BLOCK_TYPE: str = "text"

# Untrusted content boundaries used in prompts.
ALERT_DATA_TAG: str = "alert_data"
ENTITY_DATA_TAG: str = "entity_data"
INPUT_TEXT_TAG: str = "input_text"
INSTRUCTIONS_TAG: str = "analyst_instructions"


class DDLEnum(Enum):
    @classmethod
    def values(cls) -> list[str]:
        return [item.value for item in cls]


class EffortEnum(DDLEnum):
    DEFAULT = "Default"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"

    @classmethod
    def from_value(cls, value: str | None) -> EffortEnum:
        """Parse an effort value case-insensitively, falling back to Default.

        Args:
            value: The raw effort string.

        Returns:
            The matching EffortEnum member.

        Raises:
            ValueError: If the value is not a supported effort level.
        """
        if value is None or not str(value).strip():
            return cls.DEFAULT
        normalized: str = str(value).strip().lower()
        for member in cls:
            if member.value.lower() == normalized:
                return member
        raise ValueError(f"Unsupported effort level: {value!r}. Supported values: {', '.join(cls.values())}")


class EntityScopeEnum(DDLEnum):
    ALL = "All Entities"
    IP = "IP Address"
    HOSTNAME = "Hostname"
    DOMAIN = "Domain"
    URL = "URL"
    FILE_HASH = "File Hash"
    FILE_NAME = "File Name"
    USER = "User"
    PROCESS = "Process"
    EMAIL = "Email Subject"

    def to_entity_type_enum_list(self) -> list[EntityTypesEnum]:
        match self:
            case EntityScopeEnum.IP:
                return [EntityTypesEnum.ADDRESS]
            case EntityScopeEnum.HOSTNAME:
                return [EntityTypesEnum.HOST_NAME]
            case EntityScopeEnum.DOMAIN:
                return [
                    EntityTypesEnum.DOMAIN,
                    EntityTypesEnum.SOURCE_DOMAIN,
                    EntityTypesEnum.DESTINATION_DOMAIN,
                ]
            case EntityScopeEnum.URL:
                return [EntityTypesEnum.URL]
            case EntityScopeEnum.FILE_HASH:
                return [
                    EntityTypesEnum.FILE_HASH,
                    EntityTypesEnum.CHILD_HASH,
                    EntityTypesEnum.PARENT_HASH,
                ]
            case EntityScopeEnum.FILE_NAME:
                return [EntityTypesEnum.FILE_NAME]
            case EntityScopeEnum.USER:
                return [EntityTypesEnum.USER]
            case EntityScopeEnum.PROCESS:
                return [
                    EntityTypesEnum.PROCESS,
                    EntityTypesEnum.PARENT_PROCESS,
                    EntityTypesEnum.CHILD_PROCESS,
                ]
            case EntityScopeEnum.EMAIL:
                return [EntityTypesEnum.EMAIL_MESSAGE]
            case EntityScopeEnum.ALL:
                return list(EntityTypesEnum)
            case _:
                raise ValueError(f"Unfamiliar entity scope {self}")


class VerdictEnum(DDLEnum):
    MALICIOUS = "Malicious"
    SUSPICIOUS = "Suspicious"
    BENIGN = "Benign"
    INCONCLUSIVE = "Inconclusive"


class EntityVerdictEnum(DDLEnum):
    MALICIOUS = "Malicious"
    SUSPICIOUS = "Suspicious"
    BENIGN = "Benign"
    UNKNOWN = "Unknown"


# Mapping from the indicator lists returned by the Extract Indicators action to
# Google SecOps entity types.
INDICATOR_KEY_TO_ENTITY_TYPE: Mapping[str, EntityTypesEnum] = {
    "ip_addresses": EntityTypesEnum.ADDRESS,
    "domains": EntityTypesEnum.DOMAIN,
    "urls": EntityTypesEnum.URL,
    "file_hashes": EntityTypesEnum.FILE_HASH,
    "email_addresses": EntityTypesEnum.USER,
    "file_names": EntityTypesEnum.FILE_NAME,
    "cves": EntityTypesEnum.CVE,
}
