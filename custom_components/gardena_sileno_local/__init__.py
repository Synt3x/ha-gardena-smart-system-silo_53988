"""GARDENA SILENO (gen 1) via the smart Gateway's local WebSocket API."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DEFAULT_PORT, CannotConnect, GardenaLocalClient, GardenaLocalError, InvalidAuth
from .const import DOMAIN
from .decode import get_value, is_gen1_mower, mower_activity, offline_copy

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LAWN_MOWER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
]

# Entities removed in 0.4.0 (always 0 or constant, or replaced by the
# Continuous position reporting switch). Their registry entries are deleted.
REMOVED_ENTITY_KEYS = (
    "manual_operation",
    "supported_starting_points",
    "supported_wires",
    "start_delay",
    "start_position_reporting",
)

RECONNECT_DELAY = 5
MAX_RECONNECT_DELAY = 300
# The gateway pushes every change. The periodic full read is only a safety net.
SAFETY_REFRESH = timedelta(minutes=15)
WINTER_STORAGE_VERSION = 1


def _winter_store(hass: HomeAssistant, entry: ConfigEntry) -> Store[dict[str, dict[str, Any]]]:
    return Store(hass, WINTER_STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.winter")


class GardenaCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holds device state, updated by pushed events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: GardenaLocalClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SAFETY_REFRESH
        )
        self.client = client
        # device id -> selected start zone (0 = automatic)
        self.start_zone: dict[str, int] = {}
        # Winter mode: device id -> the mower's state when it was turned on.
        # Saved, so the entities can be set up while the gateway is unplugged.
        self.winter: dict[str, dict[str, Any]] = {}
        self.started_offline = False
        self._winter_store = _winter_store(hass, entry)
        self._last_out: dict[str, bool] = {}

    async def async_load_winter(self) -> None:
        self.winter = await self._winter_store.async_load() or {}

    async def async_set_winter(self, device_id: str, on: bool) -> None:
        self._last_out.pop(device_id, None)
        if on:
            self.winter[device_id] = offline_copy(self.data[device_id])
        else:
            self.winter.pop(device_id, None)
        if self.client.connected:
            self.async_devices_changed()
        else:
            self.async_gateway_lost()
        await self._winter_store.async_save(dict(self.winter))

    def _with_winter(self, reachable: bool) -> dict[str, dict[str, Any]]:
        """The gateway's devices, with stand-ins for mowers in winter mode."""
        devices = dict(self.client.devices)
        for device_id, saved in self.winter.items():
            current = devices.get(device_id)
            if current is None or not is_gen1_mower(current["data"]):
                devices[device_id] = saved
            elif not reachable:
                devices[device_id] = offline_copy(current)
        return devices

    def _all_stored(self, devices: dict[str, dict[str, Any]]) -> bool:
        """Every mower is in winter mode and offline, so no contact is expected."""
        mowers = {
            dev_id: dev["data"] for dev_id, dev in devices.items() if is_gen1_mower(dev["data"])
        }
        return bool(mowers) and all(
            dev_id in self.winter and get_value(data, "connection_status/0/online") is False
            for dev_id, data in mowers.items()
        )

    @property
    def no_contact_expected(self) -> bool:
        return self._all_stored(self._with_winter(reachable=False))

    @callback
    def async_devices_changed(self) -> None:
        """New state from the gateway."""
        self._end_winter_for_started_mowers()
        self.async_set_updated_data(self._with_winter(reachable=True))

    @callback
    def async_gateway_lost(self) -> None:
        """The gateway can't be reached. That's fine if every mower is in winter mode."""
        devices = self._with_winter(reachable=False)
        if self._all_stored(devices):
            self.async_set_updated_data(devices)
            return
        if devices:
            self.data = devices
        # async_set_update_error only notifies on the first failure.
        already_failed = not self.last_update_success
        self.async_set_update_error(CannotConnect("Connection to gateway lost"))
        if already_failed:
            self.async_update_listeners()

    @callback
    def _end_winter_for_started_mowers(self) -> None:
        """A mower that drives out is not in storage, so a forgotten winter mode ends.

        Otherwise it would hide a mower that goes missing in summer.
        """
        for device_id in list(self.winter):
            device = self.client.devices.get(device_id)
            if device is None or not is_gen1_mower(device["data"]):
                continue
            data = device["data"]
            if get_value(data, "connection_status/0/online") is False:
                continue
            out = mower_activity(data) in ("mowing", "leaving")
            was_out = self._last_out.get(device_id)
            self._last_out[device_id] = out
            # Only a new departure: turning winter mode on during the last run
            # of the season must not turn it straight off again.
            if out and was_out is False:
                _LOGGER.info("The mower started, so winter mode was turned off")
                del self.winter[device_id]
                del self._last_out[device_id]
                self.hass.async_create_task(self._winter_store.async_save(dict(self.winter)))

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Read the full state again."""
        try:
            await self.client.discover()
        except GardenaLocalError as err:
            # With the connection up, the gateway's last word on each mower still counts.
            devices = self._with_winter(reachable=self.client.connected)
            if self._all_stored(devices):
                return devices
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return self._with_winter(reachable=True)


type GardenaConfigEntry = ConfigEntry[GardenaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GardenaConfigEntry) -> bool:
    client = GardenaLocalClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = GardenaCoordinator(hass, entry, client)
    await coordinator.async_load_winter()
    try:
        await client.connect()
        await client.discover()
    except InvalidAuth as err:
        await client.shutdown()
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="wrong_password"
        ) from err
    except GardenaLocalError as err:
        if not coordinator.winter:
            await client.shutdown()
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="setup_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        _LOGGER.info("Winter mode: starting without the gateway (%s)", err)
        coordinator.started_offline = True
        # Marks the connection as closed, so _keep_connected starts retrying.
        await client.close()
        coordinator.async_gateway_lost()
    else:
        coordinator.async_devices_changed()
    if not any(is_gen1_mower(device["data"]) for device in coordinator.data.values()):
        # Right after a power cut the gateway answers before it knows the mower.
        await client.shutdown()
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="no_mower_yet")
    entry.async_on_unload(client.add_listener(coordinator.async_devices_changed))
    entry.runtime_data = coordinator
    _remove_old_entities(hass, entry)
    entry.async_create_background_task(
        hass, _keep_connected(coordinator), f"{DOMAIN}_connection"
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Options are read when used. Changing them only redraws entities (zone
    # names), so the connection is kept.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


def _remove_old_entities(hass: HomeAssistant, entry: GardenaConfigEntry) -> None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.endswith(tuple(f"_{key}" for key in REMOVED_ENTITY_KEYS)):
            registry.async_remove(entity.entity_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await _winter_store(hass, entry).async_remove()


async def _async_options_updated(hass: HomeAssistant, entry: GardenaConfigEntry) -> None:
    entry.runtime_data.async_update_listeners()


async def _keep_connected(coordinator: GardenaCoordinator) -> None:
    """Reconnect with backoff whenever the WebSocket drops."""
    client = coordinator.client
    while not client.stopped:
        await client.wait_closed()
        if client.stopped:
            return
        _LOGGER.log(
            logging.DEBUG if coordinator.no_contact_expected else logging.WARNING,
            "Lost connection to the GARDENA gateway, reconnecting",
        )
        coordinator.async_gateway_lost()
        delay = RECONNECT_DELAY
        while not client.stopped:
            await asyncio.sleep(delay)
            try:
                await client.connect()
                await client.discover()
            except InvalidAuth:
                _LOGGER.error("The gateway rejected the password")
                await client.shutdown()
                coordinator.config_entry.async_start_reauth(coordinator.hass)
                return
            except GardenaLocalError as err:
                _LOGGER.debug("Reconnect failed: %s", err)
                await client.close()
                delay = min(delay * 2, MAX_RECONNECT_DELAY)
            else:
                _LOGGER.info("Reconnected to the GARDENA gateway")
                if coordinator.started_offline:
                    # Set up from the saved state: start over with the real one.
                    coordinator.hass.config_entries.async_schedule_reload(
                        coordinator.config_entry.entry_id
                    )
                    return
                break


async def async_unload_entry(hass: HomeAssistant, entry: GardenaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.shutdown()
    return unloaded
