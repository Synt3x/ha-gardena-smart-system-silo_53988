# Entities and services

The integration ships its own icon in `custom_components/gardena_sileno_local/brand/`.
Home Assistant 2026.3 and later shows it. Older versions show a placeholder.

Shown by default:

| Entity | Notes |
|---|---|
| Lawn mower | Start = mow for the configured time from the selected start zone. Dock = your chosen park mode. |
| Start zone | **Automatic** (default, same as the app's *According to starting points*) or zone 1–4, shown as e.g. `Framsida (45 m)`. A zone without a distance shows *not set*. Remembered across restarts. |
| Mowing ends | During a timed start (app or Home Assistant): when the run ends, shown as e.g. "in 42 minutes". *Unknown* otherwise. |
| Start distance / Requested run time | LONA only. The last start command, from the app or Home Assistant: metres along the guide wire (0 = automatic) and minutes. *Unknown* after a park. |
| Battery | %. Unavailable while the gateway can't reach the mower. |
| Status | e.g. *Parked by user*, *Leaving charging station*, *Mowing (manual)*, *Searching for charging station*. Raw code in attribute `code`. |
| Problem | On only while there's an active error, or while the mower is *Disabled, manual start needed* (the app's wording; it won't move until you start it). Attribute `error_codes` holds the mower's current error codes (`[0]` = none). |
| Schedule paused | On while the mower is parked until further notice or until a date. |
| Next start | *Unknown* when no automatic start is planned. Attribute `source`. |
| Schedule | e.g. `Mon Tue Wed Thu Fri Sat 07:46, 8 h 9 min`. Entries in attributes. |
| Lawn coverage areas | Number of enabled areas. Distance, share and guide per area in attributes. |
| Cutting time | Lifetime hours of the blade motor. |
| Collisions | Lifetime counter. Wraps at 65 535. |
| Park until next schedule / Park until further notice | Buttons |
| Position | LONA only. A marker on the map, updated about every 3 seconds while the mower is out (see *Continuous position reporting*). |
| Continuous position reporting | LONA only, on by default. The mower itself reports its position only while leaving the station and stops when it starts mowing. This switch keeps reporting on whenever the mower is away from the station. At the station it's left off: the position doesn't change there. |
| Winter mode | Off by default. Turn it on when you put the mower away. See [Winter mode](../README.md#winter-mode). |
| Latitude / Longitude | LONA only. The same position as numbers (6 decimals). Keeps the last known value while parked. |

Diagnostic (under the device's *Diagnostic* section):
**Last contact** (when the mower last reported anything), last recorded error
and its time (error name is **probable**, see below), radio link quality,
mower online, refresh state, and versions: software, mainboard, display (MMI),
LONA firmware and LONA bootloader.

Disabled by default (enable them on the device page if you want them):
paused until (date of a timed pause; *Schedule paused* covers the common
case), running time, charging cycles, guide wire length, raw settings (hex for
decoding), status message, internal connection state, UTC offset, position
timer, position update interval (LONA). Most of these are raw values whose
meaning GARDENA doesn't document.

An error code that isn't in the table shows as *Unknown error code*; the
number is in the `code` attribute of *Last recorded error*.

**Services** (for automations):
- `gardena_sileno_local.start_mowing_for`: `duration` in minutes, and either
  `zone` (0 = automatic, 1–4) or `distance` in metres along the guide wire
  (LONA).

```yaml
action: gardena_sileno_local.start_mowing_for
target:
  entity_id: lawn_mower.gardena_sileno
data:
  duration: 60
  zone: 2
```
- `gardena_sileno_local.park_until_next_schedule`
- `gardena_sileno_local.park_until_further_notice`

**Diagnostics:** Settings → Devices & services → the integration → ⋮ →
Download diagnostics gives the full raw state, with serial number and position
removed. Binary fields are shown as base64 (`vo`) and as readable `hex`.
Attach it if you open an issue.
