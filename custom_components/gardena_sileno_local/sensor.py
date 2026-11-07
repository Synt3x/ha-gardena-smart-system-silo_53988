"""Sensors for GARDENA SILENO gen 1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import GardenaConfigEntry
from .decode import (
    ERROR_CODES,
    GEN1_STATUS,
    LEMONBEAT,
    NEXT_START_SOURCE,
    decode_lawn_coverage,
    decode_paused_until,
    decode_position,
    decode_schedule,
    get_value,
    has_lona,
    hexdump,
    is_gen1_mower,
    last_contact_ts,
    local_naive_from_epoch,
)
from .entity import GardenaEntity

Data = dict[str, Any]


def _lb(data: Data, resource: str) -> Any:
    return get_value(data, f"{LEMONBEAT}/{resource}")


def _local(naive: datetime | None) -> datetime | None:
    """The mower reports local wall-clock time; attach Home Assistant's time zone."""
    return naive.replace(tzinfo=dt_util.get_default_time_zone()) if naive else None


def _status(data: Data) -> str | None:
    status = GEN1_STATUS.get(_lb(data, "status"))
    return status[0] if status else None


def _last_error(data: Data) -> str | None:
    code = _lb(data, "last_error_code")
    if code is None:
        return None
    return ERROR_CODES.get(code)


def _paused_until(data: Data) -> datetime | None:
    paused = decode_paused_until(_lb(data, "action_paused_until_1"))
    return _local(paused.when) if paused else None


def _paused_attrs(data: Data) -> dict[str, Any]:
    paused = decode_paused_until(_lb(data, "action_paused_until_1"))
    return {"indefinitely": bool(paused and paused.indefinitely)}


def _schedule(data: Data) -> str | None:
    entries = decode_schedule(_lb(data, "schedule_config"))
    if entries is None:
        return None
    if not entries:
        return "none"
    return "; ".join(entry.summary() for entry in entries)[:255]


def _schedule_attrs(data: Data) -> dict[str, Any]:
    entries = decode_schedule(_lb(data, "schedule_config")) or []
    return {"entries": [asdict(entry) for entry in entries]}


def _coverage(data: Data) -> int | None:
    areas = decode_lawn_coverage(_lb(data, "starting_points"))
    return None if areas is None else sum(1 for area in areas if area.enabled)


def _coverage_attrs(data: Data) -> dict[str, Any]:
    areas = decode_lawn_coverage(_lb(data, "starting_points")) or []
    return {
        "areas": [asdict(area) for area in areas],
        "note": "Layout inferred from live data and the SILENO manual (Lawn coverage).",
    }


def _position_value(data: Data, field: str) -> float | None:
    """LONA position. Only LONA mowers report it, about every 3 s while mowing."""
    position = decode_position(_lb(data, "position"))
    return getattr(position, field) if position else None


RAW_FIELDS = (
    "settings_report",
    "settings_control",
    "lona",
    "lona_status",
    "lona_control",
    "lona_mcu_fw_version",
    "lona_mcu_boot_fw_version",
    "starting_points",
    "schedule_config",
    "action_paused_until_1",
    "timestamp_next_start",
    "mower_timer_with_distance",
    "data_download",
)


@dataclass(frozen=True, kw_only=True)
class GardenaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Data], Any]
    attrs_fn: Callable[[Data], dict[str, Any] | None] = lambda data: None
    requires_online: bool = False
    lona_only: bool = False
    # Keep showing the last value when the mower stops reporting (position).
    keep_last: bool = False


SENSORS: tuple[GardenaSensorDescription, ...] = (
    GardenaSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        requires_online=True,
        value_fn=lambda d: _lb(d, "battery_level"),
    ),
    GardenaSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=sorted({s for s, _ in GEN1_STATUS.values()}),
        requires_online=True,
        value_fn=_status,
        attrs_fn=lambda d: {"code": _lb(d, "status")},
    ),
    GardenaSensorDescription(
        key="last_error",
        translation_key="last_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(ERROR_CODES.values())),
        value_fn=_last_error,
        attrs_fn=lambda d: {
            "code": _lb(d, "last_error_code"),
            "note": "Probable meaning, based on Husqvarna's Automower error numbering.",
        },
    ),
    GardenaSensorDescription(
        key="last_error_time",
        translation_key="last_error_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _local(local_naive_from_epoch(_lb(d, "timestamp_last_error_code"))),
    ),
    GardenaSensorDescription(
        key="next_start",
        translation_key="next_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _local(local_naive_from_epoch(_lb(d, "timestamp_next_start"))),
        attrs_fn=lambda d: {
            "source": NEXT_START_SOURCE.get(_lb(d, "source_for_next_start"), "unknown")
        },
    ),
    GardenaSensorDescription(
        key="paused_until",
        translation_key="paused_until",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_paused_until,
        attrs_fn=_paused_attrs,
    ),
    GardenaSensorDescription(
        key="schedule",
        translation_key="schedule",
        value_fn=_schedule,
        attrs_fn=_schedule_attrs,
    ),
    GardenaSensorDescription(
        key="lawn_coverage",
        translation_key="lawn_coverage",
        value_fn=_coverage,
        attrs_fn=_coverage_attrs,
    ),
    GardenaSensorDescription(
        key="cutting_time",
        translation_key="cutting_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _lb(d, "cutting_time"),
    ),
    GardenaSensorDescription(
        key="running_time",
        translation_key="running_time",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _lb(d, "running_time"),
    ),
    GardenaSensorDescription(
        key="charging_cycles",
        translation_key="charging_cycles",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _lb(d, "charging_cycles"),
    ),
    GardenaSensorDescription(
        key="collisions",
        translation_key="collisions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: _lb(d, "collisions"),
    ),
    GardenaSensorDescription(
        key="latitude",
        translation_key="latitude",
        native_unit_of_measurement="°",
        suggested_display_precision=6,
        lona_only=True,
        keep_last=True,
        value_fn=lambda d: _position_value(d, "latitude"),
    ),
    GardenaSensorDescription(
        key="longitude",
        translation_key="longitude",
        native_unit_of_measurement="°",
        suggested_display_precision=6,
        lona_only=True,
        keep_last=True,
        value_fn=lambda d: _position_value(d, "longitude"),
    ),
    GardenaSensorDescription(
        key="last_contact",
        translation_key="last_contact",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            dt_util.utc_from_timestamp(ts) if (ts := last_contact_ts(d)) else None
        ),
    ),
    GardenaSensorDescription(
        key="rf_link_quality",
        translation_key="rf_link_quality",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _lb(d, "rf_link_quality"),
    ),
    GardenaSensorDescription(
        key="guide_wire_length",
        translation_key="guide_wire_length",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _lb(d, "guide_wire_length") or None,
    ),
    GardenaSensorDescription(
        key="settings_raw",
        translation_key="settings_raw",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: hexdump(_lb(d, "settings_report")),
        attrs_fn=lambda d: {name: hexdump(_lb(d, name)) for name in RAW_FIELDS},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GardenaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        GardenaSensor(coordinator, device_id, description)
        for device_id, device in coordinator.data.items()
        if is_gen1_mower(device["data"])
        for description in SENSORS
        if has_lona(device["data"]) or not description.lona_only
    )


class GardenaSensor(GardenaEntity, SensorEntity):
    entity_description: GardenaSensorDescription
    # Bulky or static attributes are not written to the recorder history.
    _unrecorded_attributes = frozenset({"entries", "areas", "note", *RAW_FIELDS})

    def __init__(self, coordinator, device_id: str, description: GardenaSensorDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self._requires_mower_online = description.requires_online
        self._last_value: Any = None

    @property
    def native_value(self) -> Any:
        value = self.entity_description.value_fn(self.device_data)
        if self.entity_description.keep_last:
            if value is None:
                return self._last_value
            self._last_value = value
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.device_data)
