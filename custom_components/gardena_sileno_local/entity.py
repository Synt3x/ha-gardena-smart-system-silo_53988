"""Base entity and mower commands for GARDENA SILENO local."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GardenaCoordinator
from .api import CannotConnect, GardenaLocalError
from .const import DOMAIN, MODEL_NAMES
from .decode import (
    LEMONBEAT,
    PARK_INDEFINITELY,
    encode_start_mowing,
    get_value,
    has_lona,
    is_gen1_mower,
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
            name=self._device_name(),
            model=MODEL_NAMES.get(str(model_number), f"Mower {model_number}"),
            model_id=str(model_number) if model_number else None,
            serial_number=get_value(data, "device/0/serial_number"),
            sw_version=get_value(data, "device/0/firmware_version"),
            hw_version=get_value(data, "device/0/hardware_version"),
        )

    def _device_name(self) -> str:
        """Tell mowers on the same gateway apart by the end of the serial number."""
        mowers = sum(is_gen1_mower(dev["data"]) for dev in self.coordinator.data.values())
        serial = get_value(self.device_data, "device/0/serial_number")
        if mowers < 2 or not serial:
            return "GARDENA SILENO"
        return f"GARDENA SILENO {str(serial)[-4:]}"

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
    def winter_storage(self) -> bool:
        """Winter mode is on and the mower is offline, as expected.

        While the mower is online, winter mode changes nothing.
        """
        return self.device_id in self.coordinator.winter and not self.mower_online

    @property
    def available(self) -> bool:
        if self.device_id not in (self.coordinator.data or {}):
            return False
        if self.winter_storage:
            return True
        if not super().available:
            return False
        return self.mower_online or not self._requires_mower_online

    async def write_lemonbeat(self, resource: str, payload: dict[str, Any]) -> None:
        if self.winter_storage:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="winter_offline"
            )
        try:
            await self.coordinator.client.write(
                self.device_id, f"{LEMONBEAT}/{resource}", payload
            )
        except CannotConnect as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="gateway_unreachable"
            ) from err
        except GardenaLocalError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"error": str(err)},
            ) from err

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
