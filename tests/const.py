"""A made-up mower state, shaped like the gateway's answer. No real IDs or positions."""

import base64

MOWER_ID = "0123456789abcdef"


def vo(raw: bytes) -> dict:
    return {"ts": 1794064692, "vo": base64.b64encode(raw).decode()}


def vi(value: int) -> dict:
    return {"ts": 1794064692, "vi": value}


STATE = {
    "lemonbeat": {
        "0": {
            "status": vi(8),
            "battery_level": vi(77),
            "last_error_code": vi(9),
            "cutting_time": vi(12),
            "collisions": vi(5),
            "rf_link_quality": vi(70),
            "position_timer": vi(0),
            "source_for_next_start": vi(2),
            "timestamp_next_start": vo(bytes.fromhex("6a841d80")),
            "lona_control": vo(b"\x01"),
            # 3 x 6 bytes: guide, metres (LE), share, enabled, reserved
            "starting_points": vo(bytes.fromhex("010300320100" "012d00320100" "010000000000")),
        }
    },
    "device": {
        "0": {
            "device_type": {"vs": "Robotics Lawnmower"},
            "model_number": {"vs": "53988"},
            "serial_number": {"vs": "12345678"},
            "error_code": {"ai": [9]},
        }
    },
    "connection_status": {"0": {"online": {"ts": 1794064692, "vb": True}}},
}
