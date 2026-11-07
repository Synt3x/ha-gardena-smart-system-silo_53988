# GARDENA SILENO local (gen 1) for Home Assistant

A Home Assistant custom integration (HACS) that reads and controls a
**1st-generation GARDENA smart SILENO** robotic mower **locally**, through the
GARDENA smart Gateway's own WebSocket API. No cloud account, no API keys and no
internet connection needed once it's set up.

Built for and tested with one mower: **smart SILENO city/life with LONA,
model number 53988**, on gateway firmware **10.12.2**.

> [!WARNING]
> **This project is vibe-coded.** It was written together with an AI coding
> assistant (Claude, by Anthropic) in a single session, by reverse-engineering
> the gateway, reading GARDENA's open-source library and testing against one
> real gateway and mower. A human checked the results, but the code has **not**
> been reviewed line by line and has **no automated test suite**.
> The gateway protocol, reading data, push updates, **Start** and **Park until
> further notice** were tested against a real gateway and mower. The Home
> Assistant side itself is in its first beta. Use it at your own risk, watch the
> mower the first time you send a command, and read the
> [What is verified](#what-is-verified-and-what-isnt) section.
>
> Not affiliated with GARDENA or Husqvarna.

---

## Quick start

You need Home Assistant with [HACS](https://hacs.xyz/docs/use/) installed, and
the gateway's IP address.

1. **Password:** the first 8 characters of the ID on the gateway's label.
   ([details](#step-1-find-the-gateway-password))
2. **Turn on the local API on the gateway** (one time). The commands are in
   [Step 2](#step-2-turn-on-the-local-api-on-the-smart-gateway).
3. **Add this repository to HACS and download it:**

   [![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Synt3x&repository=ha-gardena-smart-system-silo_53988&category=integration)

   Then click **Download** → **Download**, and **restart Home Assistant**.
   ([without the button](#step-3-install-the-integration))
4. **Add the integration:**

   [![Open your Home Assistant instance and start setting up this integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=gardena_sileno_local)

   Enter the gateway IP address and the password. Leave the port at 8443.
   ([details](#step-4-add-it-in-home-assistant))
5. **Optional:** the integration → **Configure** → name your zones and choose
   what Dock does.

---

## Contents

1. [Quick start](#quick-start)
2. [What you get](#what-you-get)
3. [Step 1: Find the gateway password](#step-1-find-the-gateway-password)
4. [Step 2: Turn on the local API on the smart Gateway](#step-2-turn-on-the-local-api-on-the-smart-gateway)
5. [Step 3: Install the integration](#step-3-install-the-integration)
6. [Step 4: Add it in Home Assistant](#step-4-add-it-in-home-assistant)
7. [Troubleshooting](#troubleshooting)
8. [Entities and services](#entities-and-services)
9. [Zones](#zones)
10. [What is verified and what isn't](#what-is-verified-and-what-isnt)
11. [How this was figured out](#how-this-was-figured-out)
12. [Help decode the remaining fields](#help-decode-the-remaining-fields)
13. [FAQ: Why does my LONA mower still bump into things?](#faq-why-does-my-lona-mower-still-bump-into-things)
14. [Turning the local API off again](#turning-the-local-api-off-again)
15. [Sources and credits](#sources-and-credits)

---

## What you get

- A **lawn mower** card: status, **Start** and **Dock**. You choose what Dock
  means (see [Step 4](#step-4-add-it-in-home-assistant)).
- **Start zone** selector: pick the charging station or one of the mower's
  zones (with your own names), then press Start. See [Zones](#zones).
- **At a glance**: battery, status, *Problem* (on only while there's an active
  error) and *Schedule paused*.
- **Planning**: next start, paused until, schedule, lawn coverage areas.
- **History**: cutting time and collisions. Running time and charging cycles
  are there too but disabled by default.
- **Buttons**: park until next schedule, park until further notice.
- **Live position on the map** while the mower is out (LONA only, every ~3 s).
- **Push updates**: the gateway sends changes within a second. A full re-read
  every 15 minutes is the safety net.
- Status and error texts in **English and Swedish**.

Only 1st-generation SILENO mowers (the gateway's `lemonbeatd` service) are
supported. 2nd-generation mowers, water controls, sensors and so on are ignored.

---

## Step 1: Find the gateway password

Turn the smart Gateway over. The label has a line like:

```
ID: 1a2b3c4d-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The password is the **first 8 characters** of that ID, here `1a2b3c4d`.

- It's lowercase hex, so only `0-9` and `a-f`. If a character is hard to read,
  `f` vs `1` for example, try both.
- The same password is used for the gateway's web page and for the local API.
- The white sticker with an 8-digit number is the **Apple HomeKit code**, not
  the password.

---

## Step 2: Turn on the local API on the smart Gateway

The local API (WebSocket on port **8443**) is **off by default**. You turn it on
once, and it stays on after reboots.

### First find the gateway's IP address

Look in your router's list of connected devices. Give the gateway a **fixed IP**
(DHCP reservation) so it doesn't change later. Below, replace `<gateway-ip>` and
`<password>` with your values.

### Option A: in the gateway's web page

1. Open `https://<gateway-ip>` in a browser and accept the certificate warning.
   The gateway uses a self-signed certificate.
2. Log in with the password from step 1.
3. If you see an **Advanced** section: open it, accept the warning and turn on
   **WebSocket support**.

On firmware 10.12.2 the Advanced section **did not show up** for us. The page
showed only Timezone, Wi-Fi and Apple HomeKit, and `#/advanced` was blank. If
that happens to you, use option B. It calls the same API the page uses.

### Option B: from a terminal (works when the web page doesn't show it)

**Windows PowerShell** (5.1, the built-in one):

```powershell
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
[System.Net.ServicePointManager]::SecurityProtocol = 'Tls12'
$s = (Invoke-RestMethod 'https://<gateway-ip>/login' -Method Post -ContentType 'application/json' -Body '{"password":"<password>"}').session
Invoke-RestMethod 'https://<gateway-ip>/websocket_api' -Method Put -Headers @{'X-Session'=$s} -ContentType 'application/json' -Body '{"enable":true}'
```

No output means it worked. `-SkipCertificateCheck` only exists in PowerShell 7,
which is why the first line is there.

**Linux / macOS / Git Bash:**

```bash
S=$(curl -sk -X POST https://<gateway-ip>/login -H 'Content-Type: application/json' \
      -d '{"password":"<password>"}' | sed -E 's/.*"session":"([^"]+)".*/\1/')
curl -sk -X PUT https://<gateway-ip>/websocket_api -H "X-Session: $S" \
     -H 'Content-Type: application/json' -d '{"enable":true}'
```

### Check that it's on

```powershell
Test-NetConnection <gateway-ip> -Port 8443     # TcpTestSucceeded : True
```
```bash
nc -zv <gateway-ip> 8443
```

If Home Assistant is on another VLAN or subnet, allow it to reach **TCP 8443**
on the gateway.

---

## Step 3: Install the integration

### With HACS (recommended)

If you don't have HACS yet, install it first by following
[HACS: Download](https://hacs.xyz/docs/use/download/download/) and
[HACS: Initial configuration](https://hacs.xyz/docs/use/configuration/basic/).

**One click:** the *Open in HACS* button in [Quick start](#quick-start) does
steps 1–3 below for you.

**By hand:**

1. In Home Assistant, open **HACS** in the sidebar.
2. Click **⋮** (top right) → **Custom repositories**.
3. Fill in:
   - **Repository:** `https://github.com/Synt3x/ha-gardena-smart-system-silo_53988`
   - **Type:** `Integration`

   Click **Add**, then close the dialog.
4. Search HACS for **GARDENA SILENO local (gen 1)** and open it.
5. Click **Download** (bottom right) → **Download**.
6. **Restart Home Assistant:** Settings → System → ⏻ (top right) →
   **Restart Home Assistant**. The integration doesn't show up until you restart.

**Updates:** HACS shows an update under *Settings → Updates* when a new
version is pushed. Click it → **Install**, then restart Home Assistant.

**Uninstall:** first remove the integration under *Settings → Devices &
services*, then HACS → the repository → ⋮ → **Remove**, and restart.

### Manually (without HACS)

1. Download this repository (green **Code** button → **Download ZIP**).
2. Copy the folder `custom_components/gardena_sileno_local` into your Home
   Assistant `config/custom_components/` folder, for example with the *File
   editor* or *Samba share* add-on. Create `custom_components` if it doesn't
   exist.
3. Restart Home Assistant.

---

## Step 4: Add it in Home Assistant

**One click:** the *Add integration* button in [Quick start](#quick-start).

**By hand:** **Settings → Devices & services → + Add integration** (bottom
right) → search for **GARDENA SILENO local (gen 1)**.

| Field | What to enter |
|---|---|
| Gateway IP address or hostname | `<gateway-ip>`, e.g. `192.168.1.50` |
| Password | First 8 characters of the gateway ID (step 1) |
| Port | `8443` (leave as is) |

Error messages:
- **Wrong password**: check the label again, especially `f` vs `1`.
- **Cannot reach the local API**: the IP is wrong, or WebSocket support is off (step 2).
- **No 1st-generation SILENO found**: connected fine, but no supported mower.

**Options** (the integration → **Configure**):

| Option | Choices |
|---|---|
| Zone 1–4 name and start distance | Your app zones, e.g. `Framsida` at `45` m. A zone without a distance uses the mower's own start area with that number (1–3). See [Zones](#zones). |
| What the Dock button does | **Go home, mow again at the next scheduled time** (default), or **Go home and stay parked until started again** |
| Mowing time for the Start button | Minutes, default 180 |

Both park variants are also separate buttons, so you can always pick the other one.

**New IP address or password?** Integration → ⋮ → **Reconfigure**. If the
password stops working, Home Assistant asks for it again by itself. You don't
need to remove and re-add the integration.

After setup you get one device, **GARDENA SILENO**. Open it from *Settings →
Devices & services → GARDENA SILENO local (gen 1)* to see all entities and add
them to a dashboard.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| The integration isn't in the *Add integration* list | Restart Home Assistant after downloading, then reload the browser page (Ctrl+F5). |
| "Cannot reach the local API" | Check the IP address. Check that port 8443 is open ([Step 2](#check-that-its-on)). The setting can be lost after a gateway factory reset. |
| "Wrong password" | Read the gateway label again. Only `0-9` and `a-f` are valid, so `f` vs `1` is the usual mistake. |
| Entities show *Unavailable* | The gateway can't reach the mower, e.g. it's switched off or in winter storage. The *Mower online* diagnostic sensor shows this. A short *Unavailable* (under a second) while Home Assistant starts or reloads the integration is normal. So is about 30 seconds after you enable a hidden entity, because Home Assistant reloads the integration then. |
| A value "hasn't updated" for a long time | Home Assistant shows when a value last **changed**. If radio link quality stays at 70 %, its time doesn't move. Check **Last contact** (diagnostic section) to see when the mower last reported anything. Radio link quality is measured by the gateway itself, about once an hour. |
| *Next start* shows *Unknown* | No automatic start is planned: the mower is mowing right now, or parked until further notice. |
| *Position* is missing | On version 0.2.0 and earlier, Home Assistant created it disabled. Open the device → *Entities* → *Position* → enable it. |
| Values look stale | Press the *Refresh state* button on the device (diagnostic section). |
| Anything else | Turn on debug logging (below), reproduce the problem, and open an [issue](https://github.com/Synt3x/ha-gardena-smart-system-silo_53988/issues) with the log and the integration's diagnostics (⋮ → *Download diagnostics*). |

Debug logging, in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.gardena_sileno_local: debug
```

Or temporarily: the integration → ⋮ → **Enable debug logging**.

---

## Entities and services

Shown by default:

| Entity | Notes |
|---|---|
| Lawn mower | Start = mow for the configured time from the selected start zone. Dock = your chosen park mode. |
| Start zone | **Automatic** (default) or one of your zones, shown as e.g. `Framsida (45 m)`. Remembered across restarts. |
| Battery | %. Unavailable while the gateway can't reach the mower. |
| Status | e.g. *Parked by user*, *Leaving charging station*, *Mowing (manual)*, *Searching for charging station*. Raw code in attribute `code`. |
| Problem | On only while there's an active error. |
| Schedule paused | On while the mower is parked until further notice or until a date. |
| Next start | *Unknown* when no automatic start is planned. Attribute `source`. |
| Schedule | e.g. `Mon Tue Wed Thu Fri Sat 07:46, 8 h 9 min`. Entries in attributes. |
| Lawn coverage areas | Number of enabled areas. Distance, share and guide per area in attributes. |
| Cutting time | Lifetime hours of the blade motor. |
| Collisions | Lifetime counter. Wraps at 65 535. |
| Park until next schedule / Park until further notice | Buttons |
| Position | LONA only. A marker on the map, updated about every 3 seconds while the mower is out. |
| Latitude / Longitude | LONA only. The same position as numbers (6 decimals). Keeps the last known value while parked. |

Diagnostic (under the device's *Diagnostic* section):
**Last contact** (when the mower last reported anything), last recorded error
and its time (error name is **probable**, see below), radio link quality,
mower online, refresh state.

Disabled by default (enable them on the device page if you want them):
paused until (date of a timed pause; *Schedule paused* covers the common
case), running time, charging cycles, guide wire length, raw settings (hex for
decoding), report position for 1 hour (LONA, while parked).

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
removed. Attach it if you open an issue.

---

## Zones

On a 1st-generation SILENO a "zone" is a **start point along the guide wire**.
The manual calls them *Lawn coverage, area 1–3*. The mower stores up to three,
each with a distance from the charging station and a share of the starts.

When you start a zone in the GARDENA app, the app sends the mower **only that
zone's distance**. Starting "Framsida" (zone 4 in the app) sent
`mower_timer_with_distance = 00 2d 00 00 0e 10`, which is 45 m and 3600 s. That
matched the mower's zone 2 (45 m). So:

- The app's zones (max 4, LONA zones drawn on the map) and their names live in
  the GARDENA cloud. They are **not** in the local API. The mower itself only
  stores 3 start areas, which the *Lawn coverage areas* sensor lists.
- So you enter your app zones once under **Configure**: name + start distance.
  A zone without a distance falls back to the mower's start area with the same
  number (1–3), with the distance read live from the mower.

**Finding each zone's distance:** run [`tools/capture.py`](tools/capture.py),
start the zone in the app, and read the first two bytes of
`mower_timer_with_distance` (`00 2d` = 45 m). The steps are in
[plan.md](plan.md#1-fill-in-the-four-app-zones-owner-10-minutes). Learning
zones automatically is planned.
- **Automatic** sends distance 0, which GARDENA's library calls the *default
  starting point*: the mower picks where to start by itself. In a test it
  drove out on its own for about 80 seconds before it began mowing. Exactly
  how it chooses (for example by the zones' shares) isn't confirmed.

## What is verified and what isn't

| Item | Status |
|---|---|
| Enabling the local API through `/login` + `/websocket_api` | ✅ Done on real hardware |
| Connect, wrong-password detection, discovery, full state | ✅ Tested against a real gateway |
| Status, battery, counters, link quality, firmware | ✅ Read from real hardware. Meanings from GARDENA's official schema |
| `cutting_time` / `running_time` in hours | ✅ GARDENA schema |
| Paused-until, last-error time, next start | ✅ Format from schema. Last-error time matched the gateway's own timestamp |
| Schedule | 🟡 Decoded with the library's gen-1 schedule format. Check against the app |
| Lawn coverage areas (`starting_points`) | 🟡 Inferred: 3 × 6 bytes matches the manual's "Lawn coverage, area 1-3" |
| Error code names | 🟡 Probable: Husqvarna Automower numbering. GARDENA doesn't publish the list |
| Status codes | ✅ 2, 4, 8 and 15 seen on the real mower and match. 🟡 The others follow the official library's list |
| Push updates | ✅ Real events observed and merged: status, timers, pause and position |
| **Start** (mow for N minutes) | ✅ Tested: the mower left the station, status went *Leaving* → *Mowing (manual)* |
| **Park until further notice** | ✅ Tested: the gateway confirmed, status went to *Searching for charging station* |
| Live position (LONA) | ✅ Decoded from real events, about every 3 seconds while mowing |
| Start zone | ✅ The app's zone start was captured. The integration builds byte-identical commands from the mower's zone list |
| Park until next schedule (default Dock mode) | 🟡 Payload from the official library. **Not tried on hardware yet** |
| Position reporting while parked | 🟡 Payload from the official library, not tried |
| Home Assistant runtime | 🟡 First beta. The code compiles and the gateway client was tested on its own, but it hasn't run inside Home Assistant yet |
| `settings_report`, `settings_control`, `lona`, `lona_status`, `data_download` | ❌ Not decoded (see below) |

---

## How this was figured out

This is a short log of the investigation, including the problems we hit and
how we worked around them.

**1. Network.** The gateway answered only on ports 80 and 443. Port 80
redirects to HTTPS. The certificate is self-signed.

**2. The gateway's web page.** It's a small Vue app ("GARDENA smart system -
Gateway Config"). Searching its JavaScript bundle for URL strings showed the
admin API:

| Endpoint | Purpose |
|---|---|
| `GET /version` | Firmware version (no login) |
| `POST /login {"password"}` | Returns `{"session"}`. Send it as header `X-Session` |
| `GET/PUT /websocket_api {"enable"}` | Local WebSocket API on/off |
| `GET/PUT /ssh_access_enable`, `POST /ssh_access_credentials` | SSH |
| `/wifi`, `/timezone`, `/homekit`, `/logout` | Other settings |

**3. Public sources.** GARDENA publishes an official Python library for this
API, [gardena-smart-local-api](https://github.com/cloudless-garden/gardena-smart-local-api).
It has a schema file for exactly this model (`53988_sileno_city_life.yaml`).
The community integration
[ha-gardena-smart-system](https://github.com/kayloehmann/ha-gardena-smart-system)
documented the password rule and port 8443.

**4. Problems we hit and solved ourselves:**

| Problem | What we found | Fix |
|---|---|---|
| The Advanced / WebSocket toggle was not visible in the web page | The JS bundle still contains `PUT /websocket_api` | Call the API directly (step 2, option B) |
| Label character unclear (`f` or `1`) | Only one is valid hex in context | Tried both; `/login` returned 200 for one and 401 for the other |
| `-SkipCertificateCheck` failed in Windows PowerShell 5.1 | It's PowerShell 7 only | Certificate callback instead |
| Connected to port 8443 but got nothing | The gateway sends no snapshot on connect | Send a discovery request |
| `Failed to route request, entity.service field missing?` | Every request needs a service | `lemonbeatd` (gen 1) or `lwm2mserver` (gen 2) |
| `'get' is not a valid ProtocolOperation` | Ops are `read`, `write`, `execute` | Use `read` |
| `lemonbeatd: could not parse request` | Requests must be a JSON **array** | Wrap in `[...]` |
| Reading `devices/<id>` failed | Per-device paths are `object/instance/resource` plus `entity.device` | Discovery (`read` `devices`) already returns the full state |
| Many fields are base64 blobs | Binary formats | Decoded with the official library, the model schema, the SILENO manual and live comparisons |
| The library can't be pip-installed in every environment | Wanted no extra dependency | Protocol re-implemented on `aiohttp`, which ships with Home Assistant |

**5. Capturing live data.** To decode what wasn't documented, we wrote a
read-only logger ([`tools/capture.py`](tools/capture.py)). It records every
message the gateway pushes, so a field can be compared before and after a
change.

**6. One supervised command test.** With the owner watching the mower, we sent
*start for 5 minutes* and then *park until further notice* through the
integration's own client code, and logged every event in between. That
confirmed the command payloads, the reply format and the push event format.

### Protocol summary

```
wss://<gateway-ip>:8443     Basic auth, user "_", password = first 8 chars of gateway ID

→ [{"op":"read","entity":{"service":"lemonbeatd","path":"devices"},"request_id":"<uuid>"}]
← [{"request_id":"<uuid>","success":true,"entity":{...},
    "payload":{"<device-id>":{"lemonbeat":{"0":{"battery_level":{"ts":1794064692,"vi":100}, ...}}}}}]
← [{"op":"update","entity":{"device":"<device-id>","path":"lemonbeat/0"},
    "metadata":{"source":"lemonbeatd","sequence":2100},
    "payload":{"status":{"ts":1794071281,"vi":15}}}]                                        (push)

→ [{"op":"write","entity":{"service":"lemonbeatd","device":"<device-id>",
    "path":"lemonbeat/0/mower_timer_with_distance"},"payload":{"vo":"AAAAAAEs"},"request_id":"<uuid>"}]
← [{"request_id":"<uuid>","success":true,"entity":{...},"metadata":{...}}]
```

Mower commands (gen 1, LONA):

| Action | Resource | Payload |
|---|---|---|
| Mow N seconds | `lemonbeat/0/mower_timer_with_distance` | 2 bytes distance (m) + 4 bytes seconds, big-endian |
| Park until next schedule | same | seconds = 0 |
| Park until further notice | `lemonbeat/0/action_paused_until_1` | year (2 bytes LE), month, day, hour, minute far in the future |
| Position reporting | `lemonbeat/0/position_timer` | `vi` seconds, 0–3600 |

Non-LONA gen-1 mowers use `lemonbeat/0/mower_timer` with `vi` seconds.

Value types: `vi` int, `vf` float, `vb` bool, `vs` string, `vo` base64 bytes,
`ai` int array, `as` string array. Each also has `ts` (Unix time).

---

## Help decode the remaining fields

These are still unknown. If you have a gen-1 SILENO, you can help.

| Field | Size | What we know |
|---|---|---|
| `settings_report` | 18 bytes | First 9 bytes `ff`. Last 9, e.g. `01 2c 23 00 01 07 00 01 00`, match `settings_control` |
| `settings_control` | 18 bytes | Last values written by the app |
| `lona` | 10 bytes | No documentation |
| `lona_status` | 12 bytes | Schema: error code, zone tag, map tag, session ID |
| `data_download` | 30 bytes | Probably firmware/map transfer bookkeeping |

Candidates for the settings bytes, from the SILENO manual's settings menu:
starting point (60–300 cm), drive past wire (20–40 cm), ECO mode,
avoid house collisions, SensorControl on/off and Low/Mid/High, security level.
`0x23` = 35 fits "drive past wire" and `0x012c` = 300 fits "starting point",
but **neither is confirmed**.

**How to help:**
1. `pip install websockets`
2. `python tools/capture.py --host <gateway-ip> --password <password>`
3. In the GARDENA app, change **one** setting. Note the time and what you changed.
4. Wait a minute, change it back, note the time again.
5. Open an issue with your notes and the matching `settings_report` lines from
   the output. Remove anything personal.

---

## FAQ: Why does my LONA mower still bump into things?

Because **LONA isn't obstacle detection**. On smart SILENO city/life, LONA is
GPS-based sensor fusion for **tracking where the mower is** and for **zones**.
GARDENA's own wording: the mower still relies on the **boundary wire** to know
where to cut. These models have no radar or camera. Like every wired SILENO,
the mower **drives until its body touches something**, the collision sensor
triggers, and it turns.

So the `collisions` counter going up all the time is normal. As an example, the
mower this was built on had about 52 500 collisions in about 2 400 cutting
hours, roughly 20 per hour. Useful things to watch in Home Assistant:

- **Sudden jumps** in collisions per hour can mean a new obstacle, or that the
  mower is stuck going back and forth somewhere.
- Error **"Trapped"** (code 9) together with many collisions points to a spot
  the mower can't get out of. The live position on the map shows where it
  happens.
- You can't reduce bumping in software. Island off trees, beds and furniture
  with boundary wire, and keep the lawn clear.

---

## Turning the local API off again

Same as step 2, with `{"enable":false}`:

```powershell
Invoke-RestMethod 'https://<gateway-ip>/websocket_api' -Method Put -Headers @{'X-Session'=$s} -ContentType 'application/json' -Body '{"enable":false}'
```

**Security note:** while it's on, anyone on your network who knows the first
8 characters of the gateway ID can read and control your GARDENA devices.
Don't expose port 8443 to the internet.

---

## What's next

See [plan.md](plan.md): learning zones automatically, a map of the mower's
track, exploring the gateway over SSH for the LONA map, decoding the settings
buffer, and the remaining hardware checks.

---

## Sources and credits

- GARDENA official local API library and model schemas (LGPL-3.0):
  https://github.com/cloudless-garden/gardena-smart-local-api
- Community integration (password rule, port, local/cloud approach):
  https://github.com/kayloehmann/ha-gardena-smart-system
- Husqvarna Automower error numbering, via aioautomower:
  https://github.com/Thomas55555/aioautomower
- SILENO city / smart SILENO city operator's manual (settings menu, lawn coverage)
- GARDENA product pages describing LONA on smart SILENO city/life
- GARDENA smart Gateway open-source components:
  https://github.com/husqvarnagroup/smart-garden-gateway-public

This integration contains no code from these projects. The protocol was
re-implemented from their documentation, schema files and observed behaviour.

## License

[MIT](LICENSE)
