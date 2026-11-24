# What is verified and what isn't

| Item | Status |
|---|---|
| Enabling the local API through `/login` + `/websocket_api` | ✅ Done on real hardware |
| Connect, wrong-password detection, discovery, full state | ✅ Tested against a real gateway |
| Status, battery, counters, link quality, firmware | ✅ Read from real hardware. Meanings from GARDENA's official schema |
| `cutting_time` / `running_time` in hours | ✅ GARDENA schema |
| Paused-until, last-error time, next start | ✅ Format from schema. Last-error time matched the gateway's own timestamp |
| Schedule | 🟡 Decoded with the library's gen-1 schedule format. Check against the app |
| Lawn coverage areas (`starting_points`) | 🟡 Inferred: 3 × 6 bytes matches the manual's "Lawn coverage, area 1-3" |
| Error code names | 🟡 Probable: Husqvarna Automower numbering (codes 0–78). GARDENA doesn't publish the list. Only code 9 has been seen on the real mower |
| Status codes | ✅ 0, 2, 3, 4, 6, 7, 8, 10, 14 and 15 seen on the real mower and match. 🟡 The others follow the official library's list |
| Push updates | ✅ Real events observed and merged: status, timers, pause and position |
| **Start** (mow for N minutes) | ✅ Tested: the mower left the station, status went *Leaving* → *Mowing (manual)* |
| **Park until further notice** | ✅ Tested: the gateway confirmed, status went to *Searching for charging station* |
| Live position (LONA) | ✅ Decoded from real events, about every 3 seconds. On its own the mower reports only while leaving the station and stops when mowing begins |
| Continuous position reporting (switch) and *Mowing ends* | 🟡 Built from live observations. Not run inside Home Assistant yet |
| Start zone | ✅ The app's zone start was captured. The integration builds byte-identical commands from the mower's zone list |
| Park until next schedule (default Dock mode) | 🟡 **Not tried on hardware yet.** Payload from the official library |
| Home Assistant runtime | 🟡 Beta. Version 0.3.1 has run in the owner's Home Assistant since 2026-11-07 with no errors in the log. Newer versions have not run there. 0.5.0 passes its automated tests on Home Assistant 2026.10.4 and 2025.1.4, against a simulated gateway |
| Turning on the local API from the setup wizard | 🟡 Same calls that worked by hand on real hardware. The wizard itself is only tested against a simulated gateway |
| Other gen-1 models, two mowers on one gateway | ❌ Never tried on hardware |
| Winter mode | 🟡 Automated tests against a simulated gateway. Not known: what the gateway reports for a mower that has been off for months, or after the gateway itself restarts |
| LONA bootloader version | 🟡 Shown as the first three bytes (`00 02 01` = 0.2.1). The format is a guess |
| `settings_report`, `settings_control`, `lona`, `lona_control`, `lona_status`, `data_download` | ❌ Not decoded (see below) |

✅ seen on real hardware · 🟡 likely, but not confirmed there · ❌ unknown or never tried
