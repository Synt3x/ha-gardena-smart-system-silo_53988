"""Buttons for GARDENA SILENO gen 1."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenaConfigEntry
from .decode import has_lona, is_gen1_mower
from .entity import GardenaEntity

POSITION_REPORT_SECONDS = 3600  # schema maximum


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    for device_id, device in coordinator.data.items():
        if not is_gen1_mower(device["data"]):
            continue
        entities += [
            ParkUntilNextSchedule(coordinator, device_id),
            ParkUntilFurtherNotice(coordinator, device_id),
            RefreshState(coordinator, device_id),
        ]
        if has_lona(device["data"]):
            entities.append(StartPositionReporting(coordinator, device_id))
    async_add_entities(entities)


class ParkUntilNextSchedule(GardenaEntity, ButtonEntity):
    _attr_translation_key = "park_until_next_schedule"
    _requires_mower_online = True

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "park_until_next_schedule")

    async def async_press(self) -> None:
        await self.mower_park_until_next_schedule()


class ParkUntilFurtherNotice(GardenaEntity, ButtonEntity):
    _attr_translation_key = "park_until_further_notice"
    _requires_mower_online = True

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "park_until_further_notice")

    async def async_press(self) -> None:
        await self.mower_park_until_further_notice()


class StartPositionReporting(GardenaEntity, ButtonEntity):
    """LONA: report GPS position while parked. It reports anyway while mowing."""

    _attr_translation_key = "start_position_reporting"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _requires_mower_online = True

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "start_position_reporting")

    async def async_press(self) -> None:
        await self.write_lemonbeat("position_timer", {"vi": POSITION_REPORT_SECONDS})


class RefreshState(GardenaEntity, ButtonEntity):
    """Read the full state from the gateway again."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
