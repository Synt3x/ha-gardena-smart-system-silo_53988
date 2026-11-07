# Plan

What's next for the integration, roughly in priority order. Each item says
what we know, what to do and how to verify it.

## 1. Fill in the four app zones (owner, 10 minutes)

**Known:** starting a zone in the GARDENA app sends the mower only that zone's
distance along the guide wire. "Framsida" (app zone 4) = 45 m. The app allows
at most 4 zones, each with its own start point.

**Do:**
1. Run `python tools/capture.py --host <gateway-ip> --password <password>`.
2. In the app, start zone 1, wait ~10 s, park. Repeat for zones 2 and 3.
3. Read the `mower_timer_with_distance` lines: the first 2 bytes are the
   distance in metres (e.g. `00 2d` = 45 m).
4. Enter name + distance for each zone under the integration's **Configure**.

**Done when:** the Start zone list shows all four zones with the right
distances, and starting each from Home Assistant drives to the same place as
the app.

## 2. Learn zones automatically from the app

**Why:** zones can change in the app. Typed distances go stale.

**Idea:** when a `mower_timer_with_distance` event arrives with a non-zero
distance that the integration didn't send itself, the app (or the mower's own
logic) started a zone. Store the distance (Home Assistant `Store`), and show it
in the Start zone list until the user names it.

**Open questions:**
- How to match a learned distance to an app zone number when two zones are
  close or a zone moves. One distance per zone is a given, since start points
  can't repeat.
- How to tell app-initiated starts from scheduled starts with lawn-coverage
  start points. Those may also produce non-zero distances.
- When to forget distances that haven't been seen for a long time.

## 3. Map: show the mower's track in Home Assistant

**Known:** LONA reports the position about every 3 s while mowing. Latitude and
longitude are sensors, and *Position* is a device tracker.

**Do:** add a README example of the built-in map card with history
(`type: map`, `entities: [device_tracker.<mower>_position]`, `hours_to_show:
24`). That draws the track. No code needed.

**Later, maybe:** a coverage heat map (where it mowed most). Needs new code,
for example an image entity rendered from stored positions. Watch database
growth: one position every 3 s is about 1 200 rows per mowing hour.

## 4. Explore the gateway over SSH (LONA map and zones from the cloud)

**Why:** the LONA map and zones are drawn in the app and stored in the GARDENA
cloud. The local API only shows that something was downloaded to the mower
(`data_download`: slot 260, checksum, status). The cloud's data passes through
the gateway's `cloudadapter` service on its way to the mower.

**Do (read-only, with the owner's go-ahead):**
1. Owner enables SSH: `POST /ssh_access_credentials {"key": "<public key>"}`
   and `PUT /ssh_access_enable {"enable": true}`, the same API as the web page.
   The gateway warns that Advanced settings may affect the warranty.
2. Look, don't change: `systemctl status cloudadapter lemonbeatd`, logs
   (`journalctl -u cloudadapter`), config and cache directories. Look for zone
   or map payloads, and for what `data_download` slot 260 contains.
3. Turn SSH off again afterwards.

**Done when:** we know whether the zone list and map can be read locally, and
in what format. Or that they can't.

## 5. Decode the settings buffer

`settings_report` / `settings_control` (18 bytes), `lona` (10 bytes) and
`lona_status` (12 bytes) are still unknown. Method: run `tools/capture.py`,
change **one** setting in the app, compare the hex. Candidates from the manual:
starting point (60–300 cm), drive past wire (20–40 cm), ECO mode, avoid house
collisions, SensorControl, security level. Seen so far: `lona_status`'s last
byte goes `07` → `1f` when the mower starts.

## 6. Verify on hardware

- **Park until next schedule** (the default Dock mode). Send it while the mower
  is out, check that it goes home, and that *Next start* shows the next
  scheduled time.
- **Position reporting while parked** (`position_timer`).
- Starting a configured zone from Home Assistant (item 1).

## 7. Smaller improvements from the product review

- Two mowers on one gateway get the same device name ("GARDENA SILENO").
- Start while the main switch is off or in an error: show a friendly message
  instead of the gateway's raw error.
- Translated exception messages.
- A GitHub release per version, so HACS shows "0.3.0" instead of a commit hash.
