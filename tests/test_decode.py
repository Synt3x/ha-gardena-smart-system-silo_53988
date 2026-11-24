"""Decoders, with the byte strings documented in the code."""

from datetime import datetime

import pytest

from custom_components.gardena_sileno_local import decode

from .const import STATE, vi, vo


def paused(text):
    return decode.decode_paused_until(bytes.fromhex(text))


def test_paused_until():
    assert paused("b20701010000") is None  # 1970 = no pause
    assert paused("f8070c1f1600").indefinitely  # the app's "until further notice"
    assert paused("fa070c1f1600").indefinitely  # the library's
    assert paused("ea0705010800").when == datetime(2026, 5, 1, 8, 0)


def test_park_command_decodes_as_indefinite():
    assert decode.decode_paused_until(decode.PARK_INDEFINITELY).indefinitely


def test_start_command_round_trip():
    raw = decode.encode_start_mowing(3600, 45)
    assert raw.hex() == "002d00000e10"
    assert decode.decode_start_command(raw) == decode.StartCommand(45, 3600)


def test_schedule():
    (entry,) = decode.decode_schedule(bytes([1, 0x7E, 7, 46, 0xE9, 0x01, 0]))
    assert entry.summary() == "Mon Tue Wed Thu Fri Sat 07:46, 8 h 9 min"
    assert decode.decode_schedule(b"123") is None


@pytest.mark.parametrize(
    ("code", "key"), [(0, "no_error"), (9, "trapped"), (999, "unknown_code"), (None, None)]
)
def test_error_key(code, key):
    assert decode.error_key(code) == key


def test_zones():
    options = {"zone_1_name": "Front", "zone_1_distance": 20}
    zones = decode.start_zones(STATE, options)
    assert [(z.name, z.distance_m, z.from_mower) for z in zones] == [
        ("Front", 20, False),
        (None, 45, True),
        (None, 0, True),
        (None, None, False),
    ]
    assert decode.start_zone_distance(STATE, options, 0) == 0
    assert decode.start_zone_distance(STATE, options, 4) is None


def test_position_without_fix():
    assert decode.decode_position(bytes(26)) is None
    assert decode.decode_position(b"short") is None


def test_timed_run_end():
    command = vo(bytes.fromhex("002d00000e10"))
    data = {"lemonbeat": {"0": {"status": vi(15), "mower_timer_with_distance": command}}}
    assert decode.timed_run_end_ts(data) == 1794064692 + 3600
    data["lemonbeat"]["0"]["status"] = vi(3)
    assert decode.timed_run_end_ts(data) is None


def test_offline_copy_leaves_the_original():
    path = "connection_status/0/online"
    copied = decode.offline_copy({"service": "lemonbeatd", "data": STATE})
    assert decode.get_value(copied["data"], path) is False
    assert decode.get_value(STATE, path) is True
    empty = decode.offline_copy({"service": "lemonbeatd", "data": {}})
    assert decode.get_value(empty["data"], path) is False
