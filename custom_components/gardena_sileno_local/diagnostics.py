"""Diagnostics: raw gateway state, for decoding unknown fields."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import GardenaConfigEntry

# Device IDs are replaced by device_0, device_1 ... below. The position is the
# owner's home location.
TO_REDACT = {CONF_PASSWORD, CONF_HOST, "serial_number", "position", "local_bd_address"}


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
        "devices": async_redact_data(devices, TO_REDACT),
    }
