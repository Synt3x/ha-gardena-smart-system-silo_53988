"""Lawn mower entity for GARDENA SILENO gen 1."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenaConfigEntry
from .const import (
    CONF_DOCK_MODE,
    CONF_START_MINUTES,
    DEFAULT_DOCK_MODE,
    DEFAULT_START_MINUTES,
    DOCK_FURTHER_NOTICE,
)
from .decode import GEN1_STATUS, MAX_ZONES, ZONE_AUTO, is_gen1_mower, start_zone_distance
from .entity import GardenaEntity

ACTIVITY = {
    "mowing": LawnMowerActivity.MOWING,
    "leaving": LawnMowerActivity.MOWING,
    "returning": LawnMowerActivity.RETURNING,
    "docked": LawnMowerActivity.DOCKED,
    "paused": LawnMowerActivity.PAUSED,
    "error": LawnMowerActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        GardenaMower(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if is_gen1_mower(device["data"])
    )
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "start_mowing_for",
        {
            vol.Required("duration"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Exclusive("zone", "start_point"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=MAX_ZONES)
            ),
            vol.Exclusive("distance", "start_point"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=500)
            ),
        },
        "async_start_mowing_for",
    )
    platform.async_register_entity_service(
        "park_until_next_schedule", {}, "mower_park_until_next_schedule"
    )
    platform.async_register_entity_service(
        "park_until_further_notice", {}, "mower_park_until_further_notice"
    )


class GardenaMower(GardenaEntity, LawnMowerEntity):
    _attr_name = None
    _attr_supported_features = LawnMowerEntityFeature.START_MOWING | LawnMowerEntityFeature.DOCK
    _requires_mower_online = True

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "mower")

    @property
    def activity(self) -> LawnMowerActivity | None:
        status = GEN1_STATUS.get(self.lb("status"))
        return ACTIVITY.get(status[1]) if status and status[1] else None

    async def async_start_mowing(self) -> None:
        """Start from the zone chosen in the Start zone selector."""
        minutes = self.coordinator.config_entry.options.get(
            CONF_START_MINUTES, DEFAULT_START_MINUTES
        )
        zone = self.coordinator.start_zone.get(self.device_id, ZONE_AUTO)
        await self.mower_start(minutes * 60, self._zone_to_distance(zone))

    async def async_start_mowing_for(
        self, duration: int, zone: int | None = None, distance: int | None = None
    ) -> None:
        if zone is not None:
            distance = self._zone_to_distance(zone)
        await self.mower_start(duration * 60, distance or 0)

    def _zone_to_distance(self, zone: int) -> int:
        distance = start_zone_distance(
            self.device_data, self.coordinator.config_entry.options, zone
        )
        if distance is None:
            raise ServiceValidationError(f"The mower has no start zone {zone}")
        return distance

    async def async_dock(self) -> None:
        """Dock mode is a setting: until next schedule (default) or until further notice."""
        mode = self.coordinator.config_entry.options.get(CONF_DOCK_MODE, DEFAULT_DOCK_MODE)
        if mode == DOCK_FURTHER_NOTICE:
            await self.mower_park_until_further_notice()
        else:
            await self.mower_park_until_next_schedule()
