"""GPS position (LONA mowers only)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenaConfigEntry
from .decode import LEMONBEAT, Position, decode_position, get_value, has_lona, is_gen1_mower
from .entity import GardenaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        GardenaPosition(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if is_gen1_mower(device["data"]) and has_lona(device["data"])
    )


class GardenaPosition(GardenaEntity, TrackerEntity):
    """Only updates while position reporting runs (see the button)."""

    _attr_translation_key = "position"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "position")
        self._last: Position | None = None

    def _position(self) -> Position | None:
        position = decode_position(get_value(self.device_data, f"{LEMONBEAT}/position"))
        if position is not None:
            self._last = position
        return self._last

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        position = self._position()
        return position.latitude if position else None

    @property
    def longitude(self) -> float | None:
        position = self._position()
        return position.longitude if position else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        position = self._position()
        if position is None:
            return None
        return {
            "heading": position.heading,
            "lona_ready": position.lona_ready,
            "gnss_latitude": position.gnss_latitude,
            "gnss_longitude": position.gnss_longitude,
            "gnss_accuracy_raw": position.gnss_accuracy,
            "compass_heading": position.compass_heading,
            "compass_calibrated": position.compass_calibrated,
        }
