"""Decoders for GARDENA gen-1 (Lemonbeat) mower values.

Pure functions without Home Assistant imports, so they can be tested alone.

Sources:
- gardena-smart-local-api (GARDENA GmbH): mowers.py, utils/schedules.py and
  schema/53988_sileno_city_life.yaml.
- Error code texts follow Husqvarna's Automower numbering (aioautomower).
  GARDENA does not publish this list, so it is marked "probable".
- Lawn coverage layout is inferred from live data and the SILENO city manual.
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

LEMONBEAT = "lemonbeat/0"

# lemonbeat/0/status -> (state key, activity)
# activity: mowing | leaving | returning | docked | paused | error | None
GEN1_STATUS: dict[int, tuple[str, str | None]] = {
    0: ("paused", "paused"),
    1: ("mowing_schedule", "mowing"),
    2: ("searching_station", "returning"),
    3: ("charging", "docked"),
    4: ("leaving_station", "leaving"),
    5: ("waiting_software_update", "paused"),
    6: ("waiting_power_up", "paused"),
    7: ("parked_week_timer", "docked"),
    8: ("parked_by_user", "docked"),
    9: ("off_main_switch", "paused"),
    10: ("waiting_stop_pressed", "paused"),
    11: ("status_unknown", None),
    12: ("error", "error"),
    13: ("error_power_up", "error"),
    14: ("waiting", "paused"),
    15: ("mowing_manual", "mowing"),
    16: ("parked_auto_timer", "docked"),
    17: ("parked_day_limit", "docked"),
    18: ("parked_frost", "docked"),
}

# source_for_next_start, order from the schema description.
NEXT_START_SOURCE = {
    0: "none",
    1: "daily_limit",
    2: "week_timer",
    3: "countdown",
    4: "charging",
    5: "auto_timer",
    6: "frost",
}

# Probable meaning (Husqvarna Automower numbering, not published by GARDENA).
ERROR_CODES: dict[int, str] = {
    0: "no_error",
    1: "outside_working_area",
    2: "no_loop_signal",
    3: "wrong_loop_signal",
    4: "loop_sensor_front",
    5: "loop_sensor_rear",
    6: "loop_sensor_left",
    7: "loop_sensor_right",
    8: "wrong_pin_code",
    9: "trapped",
    10: "upside_down",
    11: "low_battery",
    12: "empty_battery",
    13: "no_drive",
    14: "mower_lifted",
    15: "lifted",
    16: "stuck_in_charging_station",
    17: "charging_station_blocked",
    18: "collision_sensor_rear",
    19: "collision_sensor_front",
    20: "wheel_motor_blocked_right",
    21: "wheel_motor_blocked_left",
    22: "wheel_drive_right",
    23: "wheel_drive_left",
    24: "cutting_system_blocked",
    25: "cutting_system_blocked",
    26: "invalid_device_combination",
    27: "settings_restored",
    28: "memory_circuit_problem",
    29: "slope_too_steep",
    30: "charging_system_problem",
    31: "stop_button_problem",
    32: "tilt_sensor_problem",
    33: "mower_tilted",
    34: "cutting_stopped_slope",
    35: "wheel_motor_overloaded_right",
    36: "wheel_motor_overloaded_left",
    37: "charging_current_too_high",
    38: "electronic_problem",
    39: "cutting_motor_problem",
    48: "no_response_from_charger",
    50: "guide_1_not_found",
    51: "guide_2_not_found",
    52: "guide_3_not_found",
    53: "gps_navigation_problem",
    54: "weak_gps_signal",
    55: "difficult_finding_home",
    56: "guide_calibration_done",
    57: "guide_calibration_failed",
    58: "temporary_battery_problem",
    59: "temporary_battery_problem",
}

_VALUE_KEYS = ("vi", "vf", "vb", "vs", "vo", "ai", "as")
_LATLON_SCALE = 1e-7
_HEADING_SCALE = 0.1
# Far-future pause the official library writes for "park until further notice".
PARK_INDEFINITELY = (2042).to_bytes(2, "little") + bytes([12, 31, 22, 0])
INDEFINITE_YEAR = 2040


def field_value(field: Any) -> Any:
    """Return the typed value of a resource dict like {"ts": .., "vi": 5}."""
    if not isinstance(field, dict):
        return None
    for key in _VALUE_KEYS:
        if key in field:
            value = field[key]
            if key == "vo":
                if not value:
                    return b""
                try:
                    return base64.b64decode(value)
                except (ValueError, TypeError):
                    return None
            return value
    return None


def get_field(data: dict[str, Any], path: str) -> dict[str, Any] | None:
    node: Any = data
    for key in path.split("/"):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, dict) else None


def get_value(data: dict[str, Any], path: str) -> Any:
    return field_value(get_field(data, path))


def local_naive_from_epoch(raw: bytes | None) -> datetime | None:
    """4-byte big-endian seconds since 1970 in the mower's local time. 0 = none."""
    if not raw or len(raw) != 4:
        return None
    seconds = int.from_bytes(raw, "big")
    if seconds == 0:
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class PausedUntil:
    when: datetime | None  # naive local time
    indefinitely: bool


def decode_paused_until(raw: bytes | None) -> PausedUntil | None:
    """year (2 bytes LE), month, day, hour, minute. All zero = no pause."""
    if not raw or len(raw) < 6 or not any(raw):
        return None
    year = int.from_bytes(raw[0:2], "little")
    if year >= INDEFINITE_YEAR:
        return PausedUntil(None, True)
    try:
        return PausedUntil(datetime(year, raw[2], raw[3], raw[4], raw[5]), False)
    except ValueError:
        return None


_WEEKDAYS = [(0x02, "Mon"), (0x04, "Tue"), (0x08, "Wed"), (0x10, "Thu"),
             (0x20, "Fri"), (0x40, "Sat"), (0x01, "Sun")]


@dataclass(frozen=True)
class ScheduleEntry:
    schedule_id: int
    weekdays: list[str]
    start: str
    duration_minutes: int
    action: int

    def summary(self) -> str:
        days = " ".join(self.weekdays) if self.weekdays else "no days"
        hours, minutes = divmod(self.duration_minutes, 60)
        return f"{days} {self.start}, {hours} h {minutes} min"


def decode_schedule(raw: bytes | None) -> list[ScheduleEntry] | None:
    """7-byte entries: id, weekday mask, hour, minute, duration (2 bytes LE), action."""
    if raw is None or len(raw) % 7:
        return None
    entries = []
    for i in range(0, len(raw), 7):
        e = raw[i : i + 7]
        entries.append(
            ScheduleEntry(
                schedule_id=e[0],
                weekdays=[name for bit, name in _WEEKDAYS if e[1] & bit],
                start=f"{e[2]:02d}:{e[3]:02d}",
                duration_minutes=int.from_bytes(e[4:6], "little"),
                action=e[6],
            )
        )
    return entries


@dataclass(frozen=True)
class CoverageArea:
    """One "Lawn coverage" area (manual: Settings > Lawn coverage > Area 1-3).

    Inferred layout per 6 bytes: guide, distance m (2 bytes LE), share %,
    enabled, reserved.
    """

    area: int
    guide: int
    distance_m: int
    share_percent: int
    enabled: bool
    raw_hex: str


def decode_lawn_coverage(raw: bytes | None) -> list[CoverageArea] | None:
    if raw is None or not raw or len(raw) % 6:
        return None
    areas = []
    for n, i in enumerate(range(0, len(raw), 6), start=1):
        e = raw[i : i + 6]
        areas.append(
            CoverageArea(
                area=n,
                guide=e[0],
                distance_m=int.from_bytes(e[1:3], "little"),
                share_percent=e[3],
                enabled=bool(e[4]),
                raw_hex=e.hex(" "),
            )
        )
    return areas


def zone_distance(data: dict[str, Any], zone: int) -> int | None:
    """Metres along the guide wire for a start zone. Zone 0 = charging station.

    Verified: starting "Framsida" in the GARDENA app sent exactly this area's
    distance (45 m) in mower_timer_with_distance.
    """
    if zone == 0:
        return 0
    areas = decode_lawn_coverage(get_value(data, f"{LEMONBEAT}/starting_points")) or []
    for area in areas:
        if area.area == zone:
            return area.distance_m
    return None


@dataclass(frozen=True)
class Position:
    latitude: float
    longitude: float
    heading: float | None
    lona_ready: bool
    gnss_latitude: float
    gnss_longitude: float
    gnss_accuracy: int
    compass_heading: float
    compass_calibrated: bool


def decode_position(raw: bytes | None) -> Position | None:
    """26-byte position payload, layout from the official library."""
    if not raw or len(raw) != 26:
        return None
    (glat, glon, gacc, lat, lon, heading, ready, compass, calibrated) = struct.unpack(
        ">2iI2ih?h?", raw
    )
    return Position(
        latitude=lat * _LATLON_SCALE,
        longitude=lon * _LATLON_SCALE,
        heading=heading * _HEADING_SCALE if ready or calibrated else None,
        lona_ready=ready,
        gnss_latitude=glat * _LATLON_SCALE,
        gnss_longitude=glon * _LATLON_SCALE,
        gnss_accuracy=gacc,
        compass_heading=compass * _HEADING_SCALE,
        compass_calibrated=calibrated,
    )


def encode_start_mowing(seconds: int, meters_from_station: int = 0) -> bytes:
    """mower_timer_with_distance: distance m (2 bytes BE) + seconds (4 bytes BE).

    seconds = 0 means "park until next schedule" per the official library.
    """
    return meters_from_station.to_bytes(2, "big") + seconds.to_bytes(4, "big")


def opaque_payload(raw: bytes) -> dict[str, str]:
    return {"vo": base64.b64encode(raw).decode("ascii")}


def hexdump(raw: Any) -> str | None:
    return raw.hex(" ") if isinstance(raw, (bytes, bytearray)) else None


def is_gen1_mower(data: dict[str, Any]) -> bool:
    return get_field(data, f"{LEMONBEAT}/status") is not None and (
        get_value(data, "device/0/device_type") == "Robotics Lawnmower"
    )


def has_lona(data: dict[str, Any]) -> bool:
    return get_field(data, f"{LEMONBEAT}/lona_control") is not None
