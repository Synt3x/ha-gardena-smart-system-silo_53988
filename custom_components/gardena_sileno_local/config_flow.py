"""Config flow for GARDENA SILENO local."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import DEFAULT_PORT, GardenaLocalClient, GardenaLocalError, InvalidAuth
from .const import (
    CONF_DOCK_MODE,
    CONF_START_MINUTES,
    DEFAULT_DOCK_MODE,
    DEFAULT_START_MINUTES,
    DOCK_FURTHER_NOTICE,
    DOCK_NEXT_SCHEDULE,
    DOMAIN,
    MAX_ZONES,
    zone_name_key,
)
from .decode import is_gen1_mower

PORT_FIELD = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): PORT_FIELD,
    }
)
PASSWORD_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


async def _find_mowers(hass: HomeAssistant, host: str, password: str, port: int) -> list[str]:
    """Connect once and return the IDs of supported mowers."""
    client = GardenaLocalClient(async_get_clientsession(hass), host, password, port)
    try:
        await client.connect()
        devices = await client.discover()
    finally:
        await client.shutdown()
    return sorted(dev_id for dev_id, dev in devices.items() if is_gen1_mower(dev["data"]))


async def _check(hass: HomeAssistant, host: str, password: str, port: int) -> tuple[list[str], str | None]:
    try:
        mowers = await _find_mowers(hass, host, password, port)
    except InvalidAuth:
        return [], "invalid_auth"
    except GardenaLocalError:
        return [], "cannot_connect"
    return mowers, (None if mowers else "no_mower")


class GardenaSilenoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            password = user_input[CONF_PASSWORD].strip()
            port = user_input[CONF_PORT]
            mowers, error = await _check(self.hass, host, password, port)
            if error:
                errors["base"] = error
            else:
                # Identify the entry by the mower, so a new gateway IP is not a new entry.
                await self.async_set_unique_id(mowers[0])
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PASSWORD: password, CONF_PORT: port}
                )
                return self.async_create_entry(
                    title="GARDENA SILENO",
                    data={CONF_HOST: host, CONF_PASSWORD: password, CONF_PORT: port},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change IP address, password or port without removing the integration."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            password = user_input[CONF_PASSWORD].strip()
            mowers, error = await _check(self.hass, host, password, user_input[CONF_PORT])
            if error:
                errors["base"] = error
            elif entry.unique_id not in mowers:
                errors["base"] = "different_mower"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={CONF_HOST: host, CONF_PASSWORD: password, CONF_PORT: user_input[CONF_PORT]},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or entry.data),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD].strip()
            _, error = await _check(
                self.hass, entry.data[CONF_HOST], password, entry.data.get(CONF_PORT, DEFAULT_PORT)
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=PASSWORD_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GardenaSilenoOptionsFlow()


class GardenaSilenoOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # Empty zone name = use the default "Zone N".
            data = {key: value for key, value in user_input.items() if value not in ("", None)}
            return self.async_create_entry(data=data)
        zone_fields = {
            vol.Optional(zone_name_key(zone)): str for zone in range(1, MAX_ZONES + 1)
        }
        schema = vol.Schema(
            {
                **zone_fields,
                vol.Required(CONF_DOCK_MODE, default=DEFAULT_DOCK_MODE): SelectSelector(
                    SelectSelectorConfig(
                        options=[DOCK_NEXT_SCHEDULE, DOCK_FURTHER_NOTICE],
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_DOCK_MODE,
                    )
                ),
                vol.Required(CONF_START_MINUTES, default=DEFAULT_START_MINUTES): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1440)
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
