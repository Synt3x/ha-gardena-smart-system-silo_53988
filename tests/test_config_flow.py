"""Setup wizard, reconfigure, reauth and options."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.gardena_sileno_local import api, config_flow
from custom_components.gardena_sileno_local.config_flow import clean_host, clean_password
from custom_components.gardena_sileno_local.const import DOMAIN

from .const import MOWER_ID

INPUT = {CONF_HOST: "192.0.2.10", CONF_PASSWORD: "1a2b3c4d", CONF_PORT: 8443}


@pytest.fixture(autouse=True)
def web(monkeypatch, gateway, enable_custom_integrations):
    """The gateway's web page: whether it answers, and what turning on the API does."""
    page = SimpleNamespace(answers=False, error=None, calls=0, starts=True)

    async def answers(_session, _host):
        return page.answers

    async def enable(_session, _host, _password):
        page.calls += 1
        if page.error:
            raise page.error
        gateway.up = page.starts

    monkeypatch.setattr(config_flow, "gateway_web_answers", answers)
    monkeypatch.setattr(config_flow, "enable_local_api", enable)
    return page


async def submit(hass, flow, user_input):
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], user_input)
    await hass.async_block_till_done()
    return result


async def start(hass, user_input):
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert flow["type"] is FlowResultType.FORM
    return await submit(hass, flow, user_input)


async def test_setup(hass, web):
    result = await start(hass, INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == INPUT
    assert result["result"].unique_id == MOWER_ID
    assert web.calls == 0


async def test_pasted_address_and_full_id(hass):
    result = await start(
        hass,
        {
            CONF_HOST: " https://192.0.2.10/#/login ",
            CONF_PASSWORD: "1A2B3C4D-0000-0000-0000-000000000000",
            CONF_PORT: 8443,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == INPUT


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [("192.168.1.5", "192.168.1.5"), ("http://gw.local/", "gw.local"), (" gw/x ", "gw")],
)
def test_clean_host(raw, cleaned):
    assert clean_host(raw) == cleaned


def test_clean_password():
    assert clean_password(" 1A2B3C4D ") == "1a2b3c4d"
    assert clean_password("something-else") == "something-else"


async def test_wrong_password_then_right(hass):
    result = await start(hass, {**INPUT, CONF_PASSWORD: "ffffffff"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await submit(hass, result, INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_no_mower(hass, gateway):
    gateway.mowers = {}
    assert (await start(hass, INPUT))["errors"] == {"base": "no_mower"}


async def test_nothing_at_the_address(hass, gateway):
    gateway.up = False
    assert (await start(hass, INPUT))["errors"] == {"base": "cannot_connect"}


async def test_turns_on_the_api_only_after_confirmation(hass, gateway, web):
    gateway.up, web.answers = False, True
    result = await start(hass, INPUT)
    assert result["step_id"] == "enable_api"
    assert result["description_placeholders"] == {"host": "192.0.2.10"}
    assert web.calls == 0
    result = await submit(hass, result, {})
    assert web.calls == 1
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == INPUT


async def test_enable_fails_then_works(hass, gateway, web):
    gateway.up, web.answers, web.error = False, True, api.CannotConnect("500")
    result = await submit(hass, await start(hass, INPUT), {})
    assert (result["step_id"], result["errors"]) == ("enable_api", {"base": "enable_failed"})
    web.error = None
    assert (await submit(hass, result, {}))["type"] is FlowResultType.CREATE_ENTRY


async def test_enable_with_wrong_password_goes_back(hass, gateway, web):
    gateway.up, web.answers, web.error = False, True, api.InvalidAuth("401")
    result = await submit(hass, await start(hass, INPUT), {})
    assert (result["step_id"], result["errors"]) == ("user", {"base": "invalid_auth"})
    gateway.up = True
    assert (await submit(hass, result, INPUT))["type"] is FlowResultType.CREATE_ENTRY


async def test_enabled_but_does_not_start(hass, gateway, web):
    gateway.up, web.answers, web.starts = False, True, False
    result = await submit(hass, await start(hass, INPUT), {})
    assert (result["step_id"], result["errors"]) == ("enable_api", {"base": "api_not_started"})


async def test_same_mower_updates_the_address(hass, entry):
    result = await start(hass, {**INPUT, CONF_HOST: "192.0.2.99"})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "already_configured")
    assert entry.data[CONF_HOST] == "192.0.2.99"


async def test_reconfigure(hass, entry, gateway, web):
    flow = await entry.start_reconfigure_flow(hass)
    assert flow["step_id"] == "reconfigure"
    # API lost after a gateway factory reset: it can be turned on from here too.
    gateway.up, web.answers = False, True
    result = await submit(hass, flow, {**INPUT, CONF_HOST: "192.0.2.50"})
    assert result["step_id"] == "enable_api"
    result = await submit(hass, result, {})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reconfigure_successful")
    assert entry.data[CONF_HOST] == "192.0.2.50"


async def test_reconfigure_to_another_mower(hass, entry, gateway):
    gateway.mowers = {"another": gateway.mowers[MOWER_ID]}
    result = await submit(hass, await entry.start_reconfigure_flow(hass), INPUT)
    assert result["errors"] == {"base": "different_mower"}


async def test_reauth(hass, entry, gateway):
    gateway.password = "aabbccdd"
    flow = await entry.start_reauth_flow(hass)
    result = await submit(hass, flow, {CONF_PASSWORD: "00000000"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await submit(hass, result, {CONF_PASSWORD: "aabbccdd"})
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reauth_successful")
    assert entry.data[CONF_PASSWORD] == "aabbccdd"


async def test_options(hass, entry):
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "dock_mode": "further_notice",
            "start_minutes": 90,
            "zone_1_name": "Front",
            "zone_1_distance": 45,
            "zone_2_name": "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "dock_mode": "further_notice",
        "start_minutes": 90,
        "zone_1_name": "Front",
        "zone_1_distance": 45,
    }
    assert isinstance(entry.options["zone_1_distance"], int)
