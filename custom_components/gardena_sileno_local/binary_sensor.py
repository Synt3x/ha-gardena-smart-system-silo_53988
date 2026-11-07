"""Binary sensors for GARDENA SILENO gen 1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GardenaConfigEntry
from .decode import GEN1_STATUS, LEMONBEAT, decode_paused_until, get_value, is_gen1_mower
from .entity import GardenaEntity

Data = dict[str, Any]


def _problem(data: Data) -> bool | None:
    """Active error: error status, or a non-zero current error code."""
    status = GEN1_STATUS.get(get_value(data, f"{LEMONBEAT}/status"))
    if status and status[1] == "error":
        return True
    codes = get_value(data, "device/0/error_code")
    if isinstance(codes, list):
        return any(code for code in codes)
    return False if status else None


def _schedule_paused(data: Data) -> bool | None:
    raw = get_value(data, f"{LEMONBEAT}/action_paused_until_1")
    if raw is None:
        return None
    return decode_paused_until(raw) is not None


@dataclass(frozen=True, kw_only=True)
class GardenaBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[Data], bool | None]
    requires_online: bool = False


BINARY_SENSORS: tuple[GardenaBinaryDescription, ...] = (
    GardenaBinaryDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        requires_online=True,
        value_fn=_problem,
    ),
    GardenaBinaryDescription(
        key="schedule_paused",
        translation_key="schedule_paused",
        value_fn=_schedule_paused,
    ),
    GardenaBinaryDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: get_value(d, "connection_status/0/online"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        GardenaBinarySensor(coordinator, device_id, description)
        for device_id, device in coordinator.data.items()
        if is_gen1_mower(device["data"])
        for description in BINARY_SENSORS
    )


class GardenaBinarySensor(GardenaEntity, BinarySensorEntity):
    entity_description: GardenaBinaryDescription

    def __init__(self, coordinator, device_id: str, description: GardenaBinaryDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self._requires_mower_online = description.requires_online

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.device_data)
