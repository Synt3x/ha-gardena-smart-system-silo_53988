"""Switches for GARDENA SILENO gen 1."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity

from . import GardenaConfigEntry
from .decode import has_lona, is_gen1_mower, mower_activity
from .entity import GardenaEntity

_LOGGER = logging.getLogger(__name__)

# position_timer takes at most 3600 s. Re-arm before it runs out.
POSITION_TIMER_SECONDS = 3600
REARM_AFTER = 50 * 60
MIN_REARM_GAP = 60
CHECK_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ContinuousPosition(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if is_gen1_mower(device["data"]) and has_lona(device["data"])
    )


class ContinuousPosition(GardenaEntity, SwitchEntity, RestoreEntity):
    """Keep the mower's GPS position reporting on whenever it's away from the station.

    On its own the mower reports position only while leaving the station, and
    sets position_timer to 0 when mowing begins (observed 2026-11-10). Arming
    position_timer makes it report every ~3 s.
    At the station the timer is left to run out: the position doesn't change
    there, and GNSS scatter would otherwise write ~1 200 rows an hour.
    """

    _attr_translation_key = "continuous_position"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "continuous_position")
        self._attr_is_on = True
        self._armed_at: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state != STATE_OFF
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_tick, CHECK_INTERVAL)
        )
        self._maybe_arm()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self._armed_at = None
        self.async_write_ha_state()
        self._maybe_arm()

    async def async_turn_off(self, **kwargs: Any) -> None:
        # The running timer (at most an hour) is left to expire.
        self._attr_is_on = False
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._maybe_arm()
        super()._handle_coordinator_update()

    async def _async_tick(self, _now: Any) -> None:
        self._maybe_arm()

    def _away_from_station(self) -> bool:
        # Only while moving: when stopped (paused, error) the last position stays.
        return mower_activity(self.device_data) in ("mowing", "leaving", "returning")

    @callback
    def _maybe_arm(self) -> None:
        if not self.is_on or not self.mower_online:
            return
        if not self._away_from_station():
            # Re-arm right away on the next departure.
            self._armed_at = None
            return
        now = time.monotonic()
        if self._armed_at is not None:
            since = now - self._armed_at
            # The mower sets the timer to 0 itself when it starts mowing
            # (observed 2026-11-10), so re-arm then too, at most once a minute.
            stopped = self.lb("position_timer") == 0 and since >= MIN_REARM_GAP
            if since < REARM_AFTER and not stopped:
                return
        self._armed_at = now
        self.hass.async_create_task(self._async_arm(), eager_start=False)

    async def _async_arm(self) -> None:
        try:
            await self.write_lemonbeat("position_timer", {"vi": POSITION_TIMER_SECONDS})
        except HomeAssistantError as err:
            # Retried on the next update or check.
            self._armed_at = None
            _LOGGER.warning("Could not turn on position reporting: %s", err)
