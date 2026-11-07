"""GARDENA SILENO (gen 1) via the smart Gateway's local WebSocket API."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DEFAULT_PORT, CannotConnect, GardenaLocalClient, GardenaLocalError, InvalidAuth
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LAWN_MOWER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
]

MAX_RECONNECT_DELAY = 300
# The gateway pushes every change. The periodic full read is only a safety net.
SAFETY_REFRESH = timedelta(minutes=15)


class GardenaCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holds device state, updated by pushed events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: GardenaLocalClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SAFETY_REFRESH
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Read the full state again."""
        try:
            return await self.client.discover()
        except GardenaLocalError as err:
            raise UpdateFailed(str(err)) from err


type GardenaConfigEntry = ConfigEntry[GardenaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GardenaConfigEntry) -> bool:
    client = GardenaLocalClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    try:
        await client.connect()
        await client.discover()
    except InvalidAuth as err:
        await client.shutdown()
        raise ConfigEntryAuthFailed("Wrong gateway password") from err
    except GardenaLocalError as err:
        await client.shutdown()
        raise ConfigEntryNotReady(
            f"Cannot reach the gateway's local API ({err}). Is WebSocket support enabled?"
        ) from err

    coordinator = GardenaCoordinator(hass, entry, client)
    coordinator.async_set_updated_data(client.devices)
    entry.async_on_unload(
        client.add_listener(lambda: coordinator.async_set_updated_data(client.devices))
    )
    entry.runtime_data = coordinator
    entry.async_create_background_task(
        hass, _keep_connected(coordinator), f"{DOMAIN}_connection"
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Options are read when a command is sent, so changing them needs no reload.
    return True


async def _keep_connected(coordinator: GardenaCoordinator) -> None:
    """Reconnect with backoff whenever the WebSocket drops."""
    client = coordinator.client
    while not client.stopped:
        await client.wait_closed()
        if client.stopped:
            return
        _LOGGER.warning("Lost connection to the GARDENA gateway, reconnecting")
        coordinator.async_set_update_error(CannotConnect("Connection to gateway lost"))
        delay = 5
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
                break


async def async_unload_entry(hass: HomeAssistant, entry: GardenaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.shutdown()
    return unloaded
