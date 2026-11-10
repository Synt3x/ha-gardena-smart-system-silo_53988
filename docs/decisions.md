# Decisions

Newest first.

## 2026-11-10 – Audit against GARDENA's schema and live data
- **Area:** data / GUI / docs
- **Method:** Compared `decode.py` with GARDENA's schema for model 53988 and its library, and with live values read from the owner's Home Assistant (running 0.3.1): all entity states, 3 days of history, the diagnostics payload and the log.
- **Changed:**
  - Error table extended from code 59 to 78 (Automower numbering). A code outside the table shows *Unknown error code* instead of *Unknown*.
  - A position of exactly 0, 0 (no fix) is ignored, so the mower is never drawn at 0° N 0° E.
  - *Problem* got the attribute `error_codes` (the mower's current codes, `device/0/error_code`).
  - *Position timer* got a real unit (s). New hidden diagnostic *Position update interval* (LONA, 3000 ms on the owner's mower).
  - Icons for every entity and service (`icons.json`).
  - Diagnostics show binary fields as hex too, and whether the gateway is connected.
  - If reading one gateway service fails during a re-read, its devices are kept instead of dropped.
  - The `distance` field of `start_mowing_for` no longer has a default of 0. A prefilled distance collided with `zone`.
- **Removed (owner's decision, from the list of always-empty values):** the sensors *Start delay* and *Manual operation* (always 0), *Supported starting points* and *Supported wires* (constant 3 and 4), and the button *Report position for 1 hour* (the Continuous position reporting switch replaces it). Their registry entries are deleted at setup. The raw values are still in the diagnostics download.
- **Kept hidden:** guide wire length (0 = never measured), status message, UTC offset, internal connection state, raw settings, position timer.
- **Left alone on purpose:**
  - GNSS accuracy stays a raw attribute. 778–853 at the station; the unit (mm or cm) isn't known, so it isn't used as the tracker's accuracy.
  - No buttons for the mower's command resource (measure radio link, trigger data update, measure guide wire length). They write to the mower and need a supervised test first.
  - No control for the position update interval, for the same reason.
- **Verified by the live data:** the 1970 *Paused until* bug exists in 0.3.1 (shown for 7 min on 2026-11-07) and is fixed in this code. The last-error time is local time written as epoch; the decoding is right. No errors or warnings in the Home Assistant log.
- **Level:** TEST (compiles; not yet run in Home Assistant)

## 2026-11-10 – 0.4.0: continuous position, Mowing ends, zones 1–4, versions, diagnostics
- **Area:** GUI / data / mower control
- **Decision:**
  - *Continuous position reporting* switch (LONA, on by default): writes `position_timer = 3600` while the mower is away from the station, re-arms every 50 min and whenever the mower sets the timer to 0 (at most once a minute). Not armed at the station.
  - *Mowing ends* timestamp sensor: report ts of the start command + its seconds, only while leaving_station / mowing_manual.
  - Start zone always lists Automatic + zone 1–4. An unset zone shows "not set" and can't be started.
  - Status 14 = the app's "Disabled. Manual start needed": shown as an error (lawn mower *Error*, *Problem* on), not paused. Seen after park until further notice: the mower docked, then went to 14 in the station (GPS 0 m from the dock, no error code). The owner wants it to stand out, since the mower is neither parked normally nor running.
  - The position switch re-arms only while the mower moves (mowing, leaving, returning). A stopped mower's last position stays shown.
  - New sensors: start distance and requested run time (last start command), versions (software, mainboard, MMI, LONA fw/boot), and hidden raw diagnostics.
- **Why:**
  - Live data: the mower reported position only while leaving the station; at mowing_manual it wrote `position_timer = 0` and positions stopped. The owner wants the position always.
  - Not armed at the station: the position doesn't change there and GNSS scatter (~25 m seen between two dock fixes) would write ~1 200 rows an hour.
  - The owner wants the list to match the app (Automatic + 4 zones).
- **Captured:** Kortsida (app zone, start closest to the station) sent `00 03 00 00 0e 10` = 3 m, 1 h, and reached mowing_manual.
- **Level:** TEST (the switch and Mowing ends haven't run in Home Assistant yet)

## 2026-11-10 – Automatic = the app's "According to starting points" (verified)
- **Area:** mower control
- **Finding:** Starting with "According to starting points" in the app wrote `mower_timer_with_distance = 00 00 00 00 0e 10` (distance 0 m, 3600 s). That's the same command Automatic sends from Home Assistant, so no code change. The mower picks the start point itself from its Lawn coverage shares (25 m 30 %, 45 m 20 %, 11 m 30 %, the station the rest).
- **Also seen:** latitude/longitude didn't update during this run while the Position tracker and *Report position* button were disabled by the user.
- **Level:** VERIFIED

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
