"""Start zone selector: where the mower starts when you press Start."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import GardenaConfigEntry
from .const import MAX_ZONES, ZONE_STATION, zone_name_key
from .decode import LEMONBEAT, decode_lawn_coverage, get_value, is_gen1_mower, zone_distance
from .entity import GardenaEntity

LABELS = {
    "sv": ("Laddstationen", "Zon {n}"),
    "en": ("Charging station", "Zone {n}"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        StartZoneSelect(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if is_gen1_mower(device["data"])
    )


class StartZoneSelect(GardenaEntity, SelectEntity, RestoreEntity):
    _attr_translation_key = "start_zone"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "start_zone")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        zone = last.attributes.get("zone") if last else None
        if isinstance(zone, int):
            self.coordinator.start_zone[self.device_id] = zone

    @property
    def _zones(self) -> list[int]:
        areas = decode_lawn_coverage(get_value(self.device_data, f"{LEMONBEAT}/starting_points"))
        return [ZONE_STATION] + [a.area for a in (areas or [])][:MAX_ZONES]

    def _label(self, zone: int) -> str:
        station, generic = LABELS.get(self.hass.config.language[:2], LABELS["en"])
        if zone == ZONE_STATION:
            return station
        name = self.coordinator.config_entry.options.get(zone_name_key(zone)) or generic.format(n=zone)
        distance = zone_distance(self.device_data, zone)
        return f"{name} ({distance} m)" if distance is not None else name

    @property
    def _selected(self) -> int:
        zone = self.coordinator.start_zone.get(self.device_id, ZONE_STATION)
        return zone if zone in self._zones else ZONE_STATION

    @property
    def options(self) -> list[str]:
        return [self._label(zone) for zone in self._zones]

    @property
    def current_option(self) -> str | None:
        return self._label(self._selected)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"zone": self._selected, "distance_m": zone_distance(self.device_data, self._selected)}

    async def async_select_option(self, option: str) -> None:
        for zone in self._zones:
            if self._label(zone) == option:
                self.coordinator.start_zone[self.device_id] = zone
                self.async_write_ha_state()
                return
        raise ValueError(f"Unknown start zone: {option}")
