"""Winter mode and availability."""

from __future__ import annotations

import asyncio
import copy

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import ServiceValidationError

from .const import MOWER_ID

MOWER = "lawn_mower.gardena_sileno"
STATUS = "sensor.gardena_sileno_status"
BATTERY = "sensor.gardena_sileno_battery"
COLLISIONS = "sensor.gardena_sileno_collisions"
PROBLEM = "binary_sensor.gardena_sileno_problem"
ONLINE = "binary_sensor.gardena_sileno_mower_online"
NEXT_START = "sensor.gardena_sileno_next_start"
WINTER = "switch.gardena_sileno_winter_mode"


def states(hass, *entity_ids):
    return [hass.states.get(entity_id).state for entity_id in entity_ids]


def assert_stored(hass):
    assert states(hass, MOWER, STATUS, BATTERY, PROBLEM, ONLINE, NEXT_START, WINTER) == [
        "docked",
        "winter_storage",
        "unknown",
        "off",
        "off",
        "unknown",
        "on",
    ]
    assert not [s.entity_id for s in hass.states.async_all() if s.state == STATE_UNAVAILABLE]


async def setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def restart(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def winter(hass, on, entity_id=WINTER):
    await hass.services.async_call(
        "switch", "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def settle(hass):
    await asyncio.sleep(0.15)
    await hass.async_block_till_done()


async def test_offline_without_winter_mode(hass, gateway, entry):
    await setup(hass, entry)
    assert states(hass, MOWER, BATTERY, PROBLEM, WINTER) == ["docked", "77", "on", "off"]
    gateway.set_online(False)
    await hass.async_block_till_done()
    assert states(hass, MOWER, STATUS, BATTERY) == [STATE_UNAVAILABLE] * 3
    assert states(hass, COLLISIONS) == ["5"]


async def test_offline_mower(hass, gateway, entry):
    await setup(hass, entry)
    gateway.set_online(False)
    await winter(hass, True)
    assert_stored(hass)
    assert states(hass, COLLISIONS) == ["5"]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "lawn_mower", "start_mowing", {"entity_id": MOWER}, blocking=True
        )
    assert not gateway.writes
    await restart(hass, entry)
    assert_stored(hass)
    await winter(hass, False)
    assert states(hass, MOWER) == [STATE_UNAVAILABLE]


async def test_gateway_unplugged(hass, gateway, entry, caplog):
    await setup(hass, entry)
    await winter(hass, True)
    caplog.clear()
    gateway.go_down()
    await settle(hass)
    assert_stored(hass)
    await entry.runtime_data.async_refresh()
    assert_stored(hass)
    assert not [
        r
        for r in caplog.records
        if r.levelname in ("WARNING", "ERROR") and "gardena_sileno_local" in r.name
    ]

    await winter(hass, False)
    assert states(hass, MOWER, COLLISIONS, WINTER) == [STATE_UNAVAILABLE, STATE_UNAVAILABLE, "off"]
    await winter(hass, True)
    assert_stored(hass)


async def test_restart_without_gateway_then_back(hass, gateway, entry):
    await setup(hass, entry)
    await winter(hass, True)
    gateway.go_down()
    await restart(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert_stored(hass)

    # Back, but it doesn't know the mower yet.
    known, gateway.mowers = gateway.mowers, {}
    gateway.up = True
    await settle(hass)
    assert entry.runtime_data.client.connected
    assert not entry.runtime_data.started_offline
    assert_stored(hass)

    gateway.mowers = known
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert states(hass, MOWER, BATTERY, WINTER) == ["docked", "77", "on"]


async def test_online_mower_shows_the_truth(hass, gateway, entry):
    await setup(hass, entry)
    await winter(hass, True)
    assert states(hass, STATUS, BATTERY, PROBLEM) == ["parked_by_user", "77", "on"]
    # A failed re-read while connected must not look like storage.
    gateway.read_fails = True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert states(hass, STATUS) == [STATE_UNAVAILABLE]
    gateway.read_fails = False
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert states(hass, STATUS) == ["parked_by_user"]


async def test_turns_off_when_the_mower_drives_out(hass, gateway, entry):
    await setup(hass, entry)
    await winter(hass, True)
    gateway.set_online(False)
    gateway.set_online(True)
    gateway.set_status(4)
    await hass.async_block_till_done()
    assert states(hass, WINTER, MOWER) == ["off", "mowing"]
    await restart(hass, entry)
    assert states(hass, WINTER) == ["off"]


async def test_turned_on_during_the_last_run(hass, gateway, entry):
    await setup(hass, entry)
    gateway.set_status(15)
    await winter(hass, True)
    gateway.set_status(2)
    gateway.set_status(3)
    await hass.async_block_till_done()
    assert states(hass, WINTER) == ["on"]
    gateway.set_status(4)
    await hass.async_block_till_done()
    assert states(hass, WINTER) == ["off"]


async def test_second_mower_still_warns(hass, gateway, entry):
    """One mower in storage doesn't hide that the other one lost contact."""
    second = copy.deepcopy(gateway.mowers[MOWER_ID])
    second["device"]["0"]["serial_number"]["vs"] = "99998888"
    gateway.mowers["fedcba9876543210"] = second
    await setup(hass, entry)
    await winter(hass, True, "switch.gardena_sileno_5678_winter_mode")
    assert states(hass, "switch.gardena_sileno_8888_winter_mode") == ["off"]
    gateway.go_down()
    await settle(hass)
    assert states(
        hass, "lawn_mower.gardena_sileno_5678", "lawn_mower.gardena_sileno_8888"
    ) == ["docked", STATE_UNAVAILABLE]


async def test_storage_removed_with_entry(hass, gateway, entry, hass_storage):
    await setup(hass, entry)
    await winter(hass, True)
    key = f"gardena_sileno_local.{entry.entry_id}.winter"
    assert key in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    assert key not in hass_storage
