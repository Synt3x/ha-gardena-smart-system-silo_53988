"""Start zone selector: where the mower starts when you press Start."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import GardenaConfigEntry
from .decode import ZONE_AUTO, StartZone, is_gen1_mower, start_zones
from .entity import GardenaEntity

LABELS = {
    "sv": ("Automatiskt", "Zon {n}"),
    "en": ("Automatic", "Zone {n}"),
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
    def _zones(self) -> dict[int, StartZone | None]:
        """Zone number -> zone. Automatic (0) has no StartZone."""
        zones: dict[int, StartZone | None] = {ZONE_AUTO: None}
        for zone in start_zones(self.device_data, self.coordinator.config_entry.options):
            zones[zone.number] = zone
        return zones

    def _label(self, number: int, zone: StartZone | None) -> str:
        automatic, generic = LABELS.get(self.hass.config.language[:2], LABELS["en"])
        if zone is None:
            return automatic
        return f"{zone.name or generic.format(n=number)} ({zone.distance_m} m)"

    @property
    def _selected(self) -> int:
        number = self.coordinator.start_zone.get(self.device_id, ZONE_AUTO)
        return number if number in self._zones else ZONE_AUTO

    @property
    def options(self) -> list[str]:
        return [self._label(number, zone) for number, zone in self._zones.items()]

    @property
    def current_option(self) -> str | None:
        number = self._selected
        return self._label(number, self._zones[number])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self._zones[self._selected]
        return {
            "zone": self._selected,
            "distance_m": zone.distance_m if zone else 0,
            "source": "automatic" if zone is None else ("mower" if zone.from_mower else "settings"),
        }

    async def async_select_option(self, option: str) -> None:
        for number, zone in self._zones.items():
            if self._label(number, zone) == option:
                self.coordinator.start_zone[self.device_id] = number
                self.async_write_ha_state()
                return
        raise ValueError(f"Unknown start zone: {option}")
