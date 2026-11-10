"""Diagnostics: raw gateway state, for decoding unknown fields."""

from __future__ import annotations

import base64
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import GardenaConfigEntry

# Device IDs are replaced by device_0, device_1 ... below. The position is the
# owner's home location.
TO_REDACT = {CONF_PASSWORD, CONF_HOST, "serial_number", "position", "local_bd_address"}


def _with_hex(node: Any) -> Any:
    """Add a readable "hex" next to every base64 "vo" value.

    Runs after redaction, so redacted fields (already plain strings) are skipped.
    """
    if not isinstance(node, dict):
        return node
    result = {key: _with_hex(value) for key, value in node.items()}
    raw = node.get("vo")
    if isinstance(raw, str):
        try:
            result["hex"] = base64.b64decode(raw).hex(" ")
        except ValueError:
            pass
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GardenaConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    devices = {
        f"device_{index}": {"service": device["service"], "data": device["data"]}
        for index, device in enumerate((coordinator.data or {}).values())
    }
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "connected": coordinator.client.connected,
        "devices": _with_hex(async_redact_data(devices, TO_REDACT)),
    }
