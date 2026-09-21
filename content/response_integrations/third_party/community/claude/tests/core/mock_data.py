"""Mock case and alert payloads returned by the mocked SOAR SDK endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from TIPCommon.types import SingleJson

CASE_ID: int = 1
ALERT_ID: str = "ALERT-1"
ALERT_NAME: str = "Suspicious PowerShell spawned by Office"
EVENT_COMMAND_LINE: str = "powershell.exe -w hidden -enc SQBFAFgA"

MOCK_CASE_METADATA: SingleJson = {
    "identifier": str(CASE_ID),
    "creation_time": 1758400000000,
    "modification_time": 1758400000000,
    "alert_count": 1,
    "priority": 60,
    "is_touched": False,
    "is_merged": False,
    "is_important": False,
    "environment": "Default Environment",
    "assigned_user": "@Tier1",
    "title": ALERT_NAME,
    "description": "Case created from EDR alert",
    "status": "Opened",
    "is_incident": False,
    "stage": "Triage",
    "has_suspicious_entity": False,
    "high_risk_products": [],
    "is_locked": False,
    "has_workflow": True,
    "sla_expiration_unix_time": 0,
    "additional_properties": {},
}

MOCK_ALERT: SingleJson = {
    "identifier": ALERT_ID,
    "alert_group_identifier": "GROUP-1",
    "creation_time": 1758400000000,
    "modification_time": 1758400000000,
    "case_identifier": str(CASE_ID),
    "reporting_vendor": "Example EDR",
    "reporting_product": "Endpoint Protection",
    "environment": "Default Environment",
    "name": ALERT_NAME,
    "description": "winword.exe spawned an encoded PowerShell command",
    "external_id": "edr-4471",
    "severity": 80,
    "rule_generator": "Office Application Spawning PowerShell",
    "tags": ["edr", "powershell"],
    "detected_time": 1758399990000,
    "security_events": [
        {
            "identifier": "EVENT-1",
            "creation_time": 1758399990000,
            "modification_time": 1758399990000,
            "case_identifier": str(CASE_ID),
            "alert_identifier": ALERT_ID,
            "name": "Process creation",
            "event_type": "process_start",
            "device_product": "Endpoint Protection",
            "device_vendor": "Example EDR",
            "source_host_name": "WS-FIN-042",
            "source_user_name": "jdoe",
            "process": "powershell.exe",
            "parent_process": "winword.exe",
            "additional_properties": {"command_line": EVENT_COMMAND_LINE},
        },
        {
            "identifier": "EVENT-2",
            "creation_time": 1758399995000,
            "modification_time": 1758399995000,
            "case_identifier": str(CASE_ID),
            "alert_identifier": ALERT_ID,
            "name": "Network connection",
            "event_type": "network",
            "source_host_name": "WS-FIN-042",
            "destination_address": "203.0.113.45",
            "destination_port": "80",
            "destination_url": "http://203.0.113.45/s2",
            "additional_properties": {},
        },
    ],
    "domain_relations": [],
    "domain_entities": [],
    "additional_properties": {},
    "additional_data": None,
}
