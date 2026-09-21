from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, Any

from .constants import MAX_FIELD_CHARS, MAX_INSIGHT_CHARS

if TYPE_CHECKING:
    from collections.abc import Iterable

    from TIPCommon.types import JSON, SingleJson

TRUNCATION_SUFFIX: str = "...[truncated]"


def truncate_text(value: str, max_chars: int = MAX_FIELD_CHARS) -> str:
    """Truncate a string to `max_chars` characters, appending a marker when cut.

    Args:
        value: The string to truncate.
        max_chars: Maximum number of characters to keep.

    Returns:
        The original string if short enough, otherwise a truncated copy.
    """
    if len(value) <= max_chars:
        return value

    return value[: max(max_chars - len(TRUNCATION_SUFFIX), 0)] + TRUNCATION_SUFFIX


def truncate_values(data: Any, max_chars: int = MAX_FIELD_CHARS) -> Any:  # noqa: ANN401
    """Recursively truncate every string leaf inside a JSON-like structure.

    Args:
        data: A dict, list, or scalar.
        max_chars: Maximum characters for each string leaf.

    Returns:
        A copy of `data` with long string values truncated.
    """
    if isinstance(data, dict):
        return {str(key): truncate_values(value, max_chars) for key, value in data.items()}

    if isinstance(data, (list, tuple)):
        return [truncate_values(item, max_chars) for item in data]

    if isinstance(data, str):
        return truncate_text(data, max_chars)

    return data


def compact_dict(data: SingleJson) -> SingleJson:
    """Drop keys whose values are None, empty strings, empty lists or empty dicts.

    Args:
        data: The dictionary to clean.

    Returns:
        A new dictionary without empty values.
    """
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def to_json_string(data: JSON, indent: int | None = 2) -> str:
    """Serialize JSON-like data deterministically, tolerating non-serializable values.

    Args:
        data: The data to serialize.
        indent: JSON indentation.

    Returns:
        A JSON string.
    """
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def wrap_in_tag(tag: str, content: str) -> str:
    """Wrap content in an XML-style tag so the model can tell data from instructions.

    Args:
        tag: The tag name.
        content: The content to wrap.

    Returns:
        The wrapped content.
    """
    return f"<{tag}>\n{content}\n</{tag}>"


def text_to_html(text: str, max_chars: int = MAX_INSIGHT_CHARS) -> str:
    """Convert plain text into HTML that renders line breaks in SOAR insights.

    Args:
        text: The plain text.
        max_chars: Maximum characters to keep.

    Returns:
        HTML-escaped text with `<br>` line breaks.
    """
    return html.escape(truncate_text(text, max_chars)).replace("\n", "<br>")


def html_list(items: Iterable[Any]) -> str:
    """Render an iterable as an HTML unordered list.

    Args:
        items: The items to render.

    Returns:
        An HTML `<ul>` string, or an empty string when there are no items.
    """
    rendered: list[str] = [f"<li>{html.escape(str(item))}</li>" for item in items if item not in (None, "")]
    if not rendered:
        return ""

    return "<ul>" + "".join(rendered) + "</ul>"


def flatten_for_enrichment(data: SingleJson, max_value_chars: int) -> dict[str, str]:
    """Flatten a structured assessment into string values suitable for entity enrichment.

    Lists are joined with `; ` and nested objects are serialized to JSON.

    Args:
        data: The structured data to flatten.
        max_value_chars: Maximum characters per value.

    Returns:
        A flat dictionary of string values.
    """
    flat: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, list):
            rendered = "; ".join(
                to_json_string(item, indent=None) if isinstance(item, (dict, list)) else str(item) for item in value
            )
        elif isinstance(value, dict):
            rendered = to_json_string(value, indent=None)
        elif value is None:
            continue
        else:
            rendered = str(value)

        flat[key] = truncate_text(rendered, max_value_chars)

    return flat
