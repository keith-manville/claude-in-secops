"""Builds a compact, JSON-serializable description of the current case and alert."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .constants import (
    ENRICHMENT_PREFIX,
    MAX_CONTEXT_CHARS,
    MAX_FIELD_CHARS,
)
from .utils import compact_dict, to_json_string, truncate_text, truncate_values

if TYPE_CHECKING:
    from soar_sdk.SiemplifyAction import SiemplifyAction
    from TIPCommon.base.interfaces.logger import ScriptLogger
    from TIPCommon.types import Entity, SingleJson


_INTERNAL_ENTITY_PROPERTIES: frozenset[str] = frozenset({
    "IsInternalAsset",
    "IsEnriched",
    "IsSuspicious",
    "IsVulnerable",
    "IsPivot",
    "IsArtifact",
    "IsAttacker",
    "IsFromLdapString",
    "IsManuallyCreated",
    "OriginalIdentifier",
})


def build_alert_context(
    soar_action: SiemplifyAction,
    logger: ScriptLogger,
    max_events: int,
    include_entity_properties: bool = True,
) -> SingleJson:
    """Collect the current case, alert, events and entities into one JSON document.

    Every part is loaded defensively, so a failure to load one part (for example when
    the action runs without an alert context) does not fail the whole action.

    Args:
        soar_action: The SiemplifyAction SDK object.
        logger: The action logger.
        max_events: Maximum number of security events to include.
        include_entity_properties: Whether to include entity enrichment properties.

    Returns:
        A dictionary describing the case and alert.
    """
    context: SingleJson = {
        "case": _load_case(soar_action, logger),
        "alert": _load_alert(soar_action, logger, max_events),
        "entities": [
            entity_to_json(entity, include_properties=include_entity_properties)
            for entity in _load_entities(soar_action, logger)
        ],
    }
    return truncate_values(context, MAX_FIELD_CHARS)


def alert_context_to_string(context: SingleJson) -> str:
    """Serialize the alert context, keeping it under the prompt size budget.

    Args:
        context: The alert context.

    Returns:
        A JSON string.
    """
    return truncate_text(to_json_string(context), MAX_CONTEXT_CHARS)


def entity_to_json(entity: Entity, include_properties: bool = True) -> SingleJson:
    """Describe a SOAR entity as JSON, excluding platform bookkeeping properties.

    Args:
        entity: The entity.
        include_properties: Whether to include enrichment properties.

    Returns:
        A dictionary describing the entity.
    """
    result: SingleJson = {
        "identifier": entity.identifier,
        "type": entity.entity_type,
        "is_suspicious": bool(entity.is_suspicious),
        "is_internal": bool(entity.is_internal),
        "is_enriched": bool(entity.is_enriched),
        "is_artifact": bool(entity.is_artifact),
    }
    if include_properties:
        properties: dict[str, Any] = entity.additional_properties or {}
        result["properties"] = {
            key: value
            for key, value in properties.items()
            if key not in _INTERNAL_ENTITY_PROPERTIES and not key.startswith(ENRICHMENT_PREFIX)
        }

    return compact_dict(result)


def _load_case(soar_action: SiemplifyAction, logger: ScriptLogger) -> SingleJson:
    try:
        case = soar_action.case
    except Exception as error:  # noqa: BLE001
        logger.warn(f"Could not load case details for the prompt context: {error}")
        return compact_dict({"id": soar_action.case_id})

    return compact_dict({
        "id": soar_action.case_id,
        "title": getattr(case, "title", None),
        "description": getattr(case, "description", None),
        "priority": getattr(case, "priority", None),
        "stage": getattr(case, "stage", None),
        "status": getattr(case, "status", None),
        "environment": getattr(case, "environment", None),
        "is_important": getattr(case, "is_important", None),
        "alert_count": getattr(case, "alert_count", None),
    })


def _load_alert(soar_action: SiemplifyAction, logger: ScriptLogger, max_events: int) -> SingleJson:
    try:
        alert = soar_action.current_alert
    except Exception as error:  # noqa: BLE001
        logger.warn(f"Could not load alert details for the prompt context: {error}")
        return compact_dict({"id": soar_action.alert_id})

    if alert is None:
        return compact_dict({"id": soar_action.alert_id})

    events: list[SingleJson] = [_event_to_json(event) for event in getattr(alert, "security_events", [])[:max_events]]
    total_events: int = len(getattr(alert, "security_events", []))
    return compact_dict({
        "id": getattr(alert, "identifier", None) or soar_action.alert_id,
        "name": getattr(alert, "name", None),
        "description": getattr(alert, "description", None),
        "severity": getattr(alert, "severity", None),
        "vendor": getattr(alert, "reporting_vendor", None),
        "product": getattr(alert, "reporting_product", None),
        "rule_generator": getattr(alert, "rule_generator", None),
        "external_id": getattr(alert, "external_id", None),
        "detected_time": getattr(alert, "detected_time", None),
        "tags": list(getattr(alert, "tags", None) or []),
        "total_events": total_events,
        "included_events": len(events),
        "events": events,
    })


def _load_entities(soar_action: SiemplifyAction, logger: ScriptLogger) -> list[Entity]:
    try:
        return list(soar_action.target_entities or [])
    except Exception as error:  # noqa: BLE001
        logger.warn(f"Could not load entities for the prompt context: {error}")
        return []


def _event_to_json(event: Any) -> SingleJson:  # noqa: ANN401
    data: dict[str, Any] = dict(getattr(event, "__dict__", {}))
    additional: dict[str, Any] = data.pop("additional_properties", None) or {}
    result: SingleJson = compact_dict({key: value for key, value in data.items() if not key.startswith("_")})
    if additional:
        result["fields"] = compact_dict(additional)

    return result
