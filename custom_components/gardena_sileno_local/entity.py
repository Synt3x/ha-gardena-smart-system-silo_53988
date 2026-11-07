"""Base entity and mower commands for GARDENA SILENO local."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GardenaCoordinator
from .api import GardenaLocalError
from .const import DOMAIN, MODEL_NAMES
from .decode import (
    LEMONBEAT,
    PARK_INDEFINITELY,
    encode_start_mowing,
    get_value,
    has_lona,
    opaque_payload,
)


class GardenaEntity(CoordinatorEntity[GardenaCoordinator]):
    _attr_has_entity_name = True
    # Live-state entities go unavailable while the gateway can't reach the
    # mower, instead of showing a stale "Mowing". Counters keep their value.
    _requires_mower_online = False

    def __init__(self, coordinator: GardenaCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        data = self.device_data
        model_number = get_value(data, "device/0/model_number")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="GARDENA",
            name="GARDENA SILENO",
            model=MODEL_NAMES.get(str(model_number), f"Mower {model_number}"),
            model_id=str(model_number) if model_number else None,
            serial_number=get_value(data, "device/0/serial_number"),
            sw_version=get_value(data, "device/0/firmware_version"),
            hw_version=get_value(data, "device/0/hardware_version"),
        )

    @property
    def device_data(self) -> dict[str, Any]:
        device = (self.coordinator.data or {}).get(self.device_id)
        return device["data"] if device else {}

    def lb(self, resource: str) -> Any:
        return get_value(self.device_data, f"{LEMONBEAT}/{resource}")

    @property
    def mower_online(self) -> bool:
        return get_value(self.device_data, "connection_status/0/online") is not False

    @property
    def available(self) -> bool:
        if not (super().available and self.device_id in (self.coordinator.data or {})):
            return False
        return self.mower_online or not self._requires_mower_online

    async def write_lemonbeat(self, resource: str, payload: dict[str, Any]) -> None:
        try:
            await self.coordinator.client.write(
                self.device_id, f"{LEMONBEAT}/{resource}", payload
            )
        except GardenaLocalError as err:
            raise HomeAssistantError(f"The gateway rejected the command: {err}") from err

    # Mower commands. Payloads follow GARDENA's official library.

    async def mower_start(self, seconds: int, meters_from_station: int = 0) -> None:
        """seconds = 0 means park until the next scheduled start."""
        if has_lona(self.device_data):
            await self.write_lemonbeat(
                "mower_timer_with_distance",
                opaque_payload(encode_start_mowing(seconds, meters_from_station)),
            )
        else:
            await self.write_lemonbeat("mower_timer", {"vi": seconds})

    async def mower_park_until_next_schedule(self) -> None:
        await self.mower_start(0, 0)

    async def mower_park_until_further_notice(self) -> None:
        await self.write_lemonbeat("action_paused_until_1", opaque_payload(PARK_INDEFINITELY))
