# Decisions

Newest first.

## 2026-11-07 – 0.3.0: app zones entered by hand, Automatic, GPS sensors, fixes
- **Area:** GUI / data
- **Decision:**
  - The start zone list is Automatic plus up to 4 zones (name + distance) entered under Configure. A zone without a distance falls back to the mower's start area 1–3.
  - "Charging station" became "Automatic" (distance 0 = the mower's default starting point).
  - Latitude and longitude are separate sensors (LONA only) and keep their last value while parked.
  - New *Last contact* diagnostic sensor.
  - The position tracker is enabled by default. *Paused until* is hidden by default.
- **Why:**
  - The app's LONA zones aren't in the local API; the mower stores only 3 start areas. The owner said the app allows max 4 zones with unique start points, so knowing the start distances is enough.
  - "Not updated in 40 min" turned out to be an unchanged value. The gateway measures radio link quality itself, about hourly. *Last contact* makes freshness visible.
- **Bugs fixed:**
  - *Paused until* showed 1970-01-01. The mower writes 1970-01-01 to mean "no pause", seen in the log after resuming in the app.
  - The position tracker was disabled by Home Assistant's default for integration trackers.
- **Deferred to plan.md (owner's choice):** learning zones automatically, a map track card, SSH exploration of the gateway.
- **Note:** GPS sensors and the tracker write about every 3 s while mowing. Accepted for now. A coverage map would need care with database growth.
- **Level:** TEST

## 2026-11-07 – Start zones: selector + Start, names set in Home Assistant
- **Area:** GUI / mower control
- **Decision:** A *Start zone* selector (charging station, zone 1–3) decides where the mower's Start begins. Zone names are options in the integration. The service `start_mowing_for` takes `zone` or `distance`.
- **Why:** Capturing a zone start from the GARDENA app showed that it sends only the zone's distance along the guide wire, which matched the mower's start area. The app's zone numbers and names are not on the mower, so they can't be read locally.
- **Objection:** Claude suggested one button per zone (one tap). The owner chose selector + Start (fewer entities).
- **Testing:** The command was not sent from Home Assistant. Its bytes match the app's captured command exactly. The owner asked not to test zones 1–2 because they had been changed.
- **Level:** TEST

## 2026-11-07 – Publish as public beta 0.1.0 before running inside Home Assistant
- **Area:** Release
- **Decision:** Push to GitHub now and install via HACS, as beta 0.1.0.
- **Why:** HACS is the install path, and there is no separate test instance of Home Assistant.
- **Objection:** Claude suggested waiting until it had worked in the owner's Home Assistant. The owner chose to publish now. The README lists exactly what is verified and what isn't.
- **Level:** TEST (beta), public repo

## 2026-11-07 – No test instance of Home Assistant
- **Area:** Testing
- **Decision:** Gateway protocol and commands are tested directly against the real gateway from a PC. The integration itself is tested in the owner's real Home Assistant.
- **Why:** The owner's choice.
- **Level:** TEST

## 2026-11-07 – Dock behaviour is an option, default "until next schedule"
- **Area:** GUI / mower control
- **Decision:** Option "What the Dock button does": *go home and mow again at the next scheduled time* (default) or *go home and stay parked until started again*. Both are also separate buttons and services.
- **Why:** The HA mower card's Dock button is the obvious "go home" action. If it paused the schedule indefinitely, the mower could stand still for weeks without anyone noticing. The owner wanted to be able to choose.
- **Level:** TEST

## 2026-11-07 – One supervised command test on real hardware
- **Area:** Safety / verification
- **Decision:** Start (5 min) and Park until further notice were sent once while the owner watched the mower. Both worked. The mower was left parked until further notice, as it was before the test.
- **Not yet tried:** Park until next schedule, position reporting while parked.
- **Level:** TEST

## 2026-11-07 – Push updates plus a 15-minute safety re-read
- **Area:** Backend
- **Decision:** State comes from the gateway's push events, which were verified. The coordinator also re-reads the full state every 15 minutes.
- **Why:** A silently missed event would otherwise show stale data indefinitely. A full read is one small request.
- **Level:** TEST

## 2026-11-07 – Integration identified by the mower, not the IP address
- **Area:** Data model / setup
- **Decision:** The config entry's unique ID is the mower's device ID. Reconfigure changes the IP, password or port. A rejected password starts re-authentication.
- **Why:** An IP change must not create a duplicate or force removing the integration.
- **Level:** TEST

## 2026-11-07 – Entities a non-technical user doesn't need are hidden
- **Area:** GUI
- **Decision:** Shown: mower, battery, status, problem, schedule paused, next start, paused until, schedule, lawn coverage, cutting time, collisions, park buttons, position. Diagnostic: last recorded error and its time, radio link, online, refresh. Disabled by default: running time, charging cycles, guide wire length, raw settings, position reporting button.
- **Why:** About 20 entities on a phone is too many. "Last error" stays visible after the problem is gone, so the *Problem* sensor carries the active state instead.
- **Level:** TEST

## 2026-11-07 – Never publish personal data
- **Area:** Privacy / security
- **Decision:** The repo and README contain no gateway password, gateway ID, device ID, serial number or GPS position. Diagnostics redact the password, host, serial number and position, and replace device IDs.
- **Why:** The password is derived from the gateway ID, and the position is the owner's home.
- **Level:** LIVE (public repo)
