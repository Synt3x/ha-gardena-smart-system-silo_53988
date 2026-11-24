"""Config flow for GARDENA SILENO local."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    DEFAULT_PORT,
    GardenaLocalClient,
    GardenaLocalError,
    InvalidAuth,
    enable_local_api,
    gateway_web_answers,
)
from .const import (
    CONF_DOCK_MODE,
    CONF_START_MINUTES,
    DEFAULT_DOCK_MODE,
    DEFAULT_START_MINUTES,
    DOCK_FURTHER_NOTICE,
    DOCK_NEXT_SCHEDULE,
    DOMAIN,
)
from .decode import MAX_ZONES, is_gen1_mower, zone_distance_key, zone_name_key

_LOGGER = logging.getLogger(__name__)

PORT_FIELD = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
PASSWORD_FIELD = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): PASSWORD_FIELD,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): PORT_FIELD,
    }
)
PASSWORD_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_FIELD})

# The gateway needs a moment to start the local API after it's turned on.
API_START_ATTEMPTS = 6
API_START_WAIT = 3


def clean_host(value: str) -> str:
    """Accept a pasted address such as https://192.168.1.50/#/login."""
    host = value.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    return host.split("/", 1)[0].strip()


def clean_password(value: str) -> str:
    """Accept the whole gateway ID; the password is its first 8 characters."""
    password = value.strip()
    if re.match(r"^[0-9a-fA-F]{8}(-|$)", password):
        return password[:8].lower()
    return password


async def _find_mowers(hass: HomeAssistant, host: str, password: str, port: int) -> list[str]:
    """Connect once and return the IDs of supported mowers."""
    client = GardenaLocalClient(async_get_clientsession(hass), host, password, port)
    try:
        await client.connect()
        devices = await client.discover()
    finally:
        await client.shutdown()
    return sorted(dev_id for dev_id, dev in devices.items() if is_gen1_mower(dev["data"]))


async def _check(
    hass: HomeAssistant, host: str, password: str, port: int
) -> tuple[list[str], str | None]:
    try:
        mowers = await _find_mowers(hass, host, password, port)
    except InvalidAuth:
        return [], "invalid_auth"
    except (GardenaLocalError, ValueError):
        # ValueError: not a usable address.
        return [], "cannot_connect"
    return mowers, (None if mowers else "no_mower")


class GardenaSilenoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_connection_form("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change IP address, password or port without removing the integration."""
        return await self._async_connection_form(
            "reconfigure", user_input, self._get_reconfigure_entry().data
        )

    async def _async_connection_form(
        self, step_id: str, user_input: dict[str, Any] | None, current: Mapping[str, Any]
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_HOST: clean_host(user_input[CONF_HOST]),
                CONF_PASSWORD: clean_password(user_input[CONF_PASSWORD]),
                CONF_PORT: user_input[CONF_PORT],
            }
            mowers, error = await _check(self.hass, *data.values())
            if error is None and self._is_different_mower(mowers):
                error = "different_mower"
            if error is None:
                return await self._async_finish(data, mowers)
            if (
                error == "cannot_connect"
                and data[CONF_PORT] == DEFAULT_PORT
                and await gateway_web_answers(
                    async_get_clientsession(self.hass), data[CONF_HOST]
                )
            ):
                # The gateway is there, so its local API is probably just off.
                self._pending = data
                return await self.async_step_enable_api()
            errors["base"] = error
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input if user_input is not None else current
            ),
            errors=errors,
        )

    async def async_step_enable_api(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to turn on the gateway's local API."""
        data = self._pending
        errors: dict[str, str] = {}
        if user_input is not None:
            mowers: list[str] = []
            try:
                await enable_local_api(
                    async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PASSWORD]
                )
            except InvalidAuth:
                error: str | None = "invalid_auth"
            except GardenaLocalError as err:
                _LOGGER.warning("Could not turn on the gateway's local API: %s", err)
                error = "enable_failed"
            else:
                for _ in range(API_START_ATTEMPTS):
                    mowers, error = await _check(self.hass, *data.values())
                    # The mower can show up a moment after the API does.
                    if error not in ("cannot_connect", "no_mower"):
                        break
                    await asyncio.sleep(API_START_WAIT)
                if error == "cannot_connect":
                    error = "api_not_started"
            if error is None and self._is_different_mower(mowers):
                error = "different_mower"
            if error is None:
                return await self._async_finish(data, mowers)
            if error in ("invalid_auth", "different_mower"):
                # Back to the form, where the address and password can be changed.
                reconfigure = self.source == SOURCE_RECONFIGURE
                return self.async_show_form(
                    step_id="reconfigure" if reconfigure else "user",
                    data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, data),
                    errors={"base": error},
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="enable_api",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"host": data[CONF_HOST]},
        )

    def _is_different_mower(self, mowers: list[str]) -> bool:
        return (
            self.source == SOURCE_RECONFIGURE
            and self._get_reconfigure_entry().unique_id not in mowers
        )

    async def _async_finish(self, data: dict[str, Any], mowers: list[str]) -> ConfigFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=data)
        # Identify the entry by the mower, so a new gateway IP is not a new entry.
        await self.async_set_unique_id(mowers[0])
        self._abort_if_unique_id_configured(updates=data)
        return self.async_create_entry(title="GARDENA SILENO", data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = clean_password(user_input[CONF_PASSWORD])
            _, error = await _check(
                self.hass, entry.data[CONF_HOST], password, entry.data.get(CONF_PORT, DEFAULT_PORT)
            )
            # The password is right even if the mower isn't reported at the moment.
            if error not in (None, "no_mower"):
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


def _number(minimum: int, maximum: int, unit: str) -> vol.All:
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(
                min=minimum, max=maximum, unit_of_measurement=unit, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Coerce(int),
    )


class GardenaSilenoOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # Empty zone name = use the default "Zone N".
            data = {key: value for key, value in user_input.items() if value not in ("", None)}
            return self.async_create_entry(data=data)
        zone_fields: dict[Any, Any] = {}
        for zone in range(1, MAX_ZONES + 1):
            zone_fields[vol.Optional(zone_name_key(zone))] = str
            zone_fields[vol.Optional(zone_distance_key(zone))] = _number(0, 500, "m")
        schema = vol.Schema(
            {
                vol.Required(CONF_DOCK_MODE, default=DEFAULT_DOCK_MODE): SelectSelector(
                    SelectSelectorConfig(
                        options=[DOCK_NEXT_SCHEDULE, DOCK_FURTHER_NOTICE],
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_DOCK_MODE,
                    )
                ),
                vol.Required(CONF_START_MINUTES, default=DEFAULT_START_MINUTES): _number(
                    1, 1440, "min"
                ),
                **zone_fields,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
