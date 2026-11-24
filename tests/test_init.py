"""Setup, reconnect, entities and commands."""

from __future__ import annotations

import base64

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.gardena_sileno_local import api
from custom_components.gardena_sileno_local.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .test_winter import BATTERY, MOWER, settle, setup, states


async def call(hass, domain, service, **data):
    await hass.services.async_call(domain, service, {"entity_id": MOWER, **data}, blocking=True)


def sent(gateway):
    path, payload = gateway.writes[-1]
    return path.rsplit("/", 1)[1], base64.b64decode(payload["vo"]).hex()


async def test_gateway_down_retries(hass, gateway, entry):
    gateway.up = False
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_wrong_password_asks_again(hass, gateway, entry):
    gateway.password = "00000000"
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert [f["context"]["source"] for f in hass.config_entries.flow.async_progress()] == ["reauth"]


async def test_gateway_without_mower_retries(hass, gateway, entry):
    """After a power cut the gateway answers before it knows the mower."""
    gateway.mowers = {}
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_reconnects(hass, gateway, entry):
    await setup(hass, entry)
    gateway.go_down()
    await settle(hass)
    assert states(hass, MOWER, BATTERY) == [STATE_UNAVAILABLE] * 2
    gateway.up = True
    await settle(hass)
    assert states(hass, MOWER, BATTERY) == ["docked", "77"]


async def test_commands(hass, gateway, entry):
    await setup(hass, entry)
    await call(hass, "lawn_mower", "start_mowing")
    assert sent(gateway) == ("mower_timer_with_distance", "000000002a30")  # automatic, 180 min
    await call(hass, "gardena_sileno_local", "start_mowing_for", duration=60, zone=2)
    assert sent(gateway) == ("mower_timer_with_distance", "002d00000e10")  # 45 m, as the app
    await call(hass, "gardena_sileno_local", "start_mowing_for", duration=60, distance=3)
    assert sent(gateway) == ("mower_timer_with_distance", "000300000e10")
    await call(hass, "lawn_mower", "dock")
    assert sent(gateway) == ("mower_timer_with_distance", "000000000000")
    hass.config_entries.async_update_entry(entry, options={"dock_mode": "further_notice"})
    await call(hass, "lawn_mower", "dock")
    assert sent(gateway) == ("action_paused_until_1", "fa070c1f1600")


async def test_zone_without_distance(hass, gateway, entry):
    await setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await call(hass, "gardena_sileno_local", "start_mowing_for", duration=60, zone=4)
    assert not gateway.writes


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (api.CannotConnect("down"), "gateway_unreachable"),
        (api.CommandFailed("bad"), "command_rejected"),
    ],
)
async def test_command_errors_are_explained(hass, gateway, entry, monkeypatch, error, key):
    await setup(hass, entry)

    async def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(gateway.client, "write", fail)
    with pytest.raises(HomeAssistantError) as caught:
        await call(hass, "lawn_mower", "start_mowing")
    assert caught.value.translation_key == key


async def test_continuous_position_arms_when_leaving(hass, gateway, entry):
    await setup(hass, entry)
    assert not gateway.writes
    gateway.set_status(4)
    await hass.async_block_till_done()
    assert gateway.writes == [("lemonbeat/0/position_timer", {"vi": 3600})]


async def test_diagnostics_hide_personal_data(hass, gateway, entry):
    await setup(hass, entry)
    text = str(await async_get_config_entry_diagnostics(hass, entry))
    for secret in ("192.0.2.10", "1a2b3c4d", "12345678", "0123456789abcdef"):
        assert secret not in text
