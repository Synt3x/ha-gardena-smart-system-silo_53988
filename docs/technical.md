# Technical notes

How the gateway's local API works, how that was found out, and what is still unknown. You don't need this to use the integration; see the [README](../README.md).

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
| The Advanced / WebSocket toggle was not visible in the web page | The JS bundle still contains `PUT /websocket_api` | Call the API directly ([by hand](manual-setup.md)) |
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
read-only logger ([`tools/capture.py`](../tools/capture.py)). It records every
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

## Help decode the remaining fields

These are still unknown. If you have a gen-1 SILENO, you can help.

| Field | Size | What we know |
|---|---|---|
| `settings_report` | 18 bytes | First 9 bytes `ff`. Last 9, e.g. `01 2c 23 00 01 07 00 01 00`, match `settings_control` |
| `settings_control` | 18 bytes | Last values written by the app |
| `lona` | 10 bytes | No documentation |
| `lona_control` | 1 byte (`01`) | Schema: LONA control flags |
| `lona_status` | 12 bytes | Schema: error code, zone tag, map tag, session ID. The last byte was `1f` during a run and `07` otherwise |
| `data_download` | 30 bytes | Map/zone transfer bookkeeping. The gateway also shows it decoded as `data_download/0`: slot 260, a checksum, content tag and status |
| `lemonbeat_status_message` | 4 values | Code 12, level 2 (= error in the schema), type 6, data `01`, unchanged for days while the mower worked normally |

Candidates for the settings bytes, from the SILENO manual's settings menu:
starting point (60–300 cm), drive past wire (20–40 cm), ECO mode,
avoid house collisions, SensorControl on/off and Low/Mid/High, security level.
`0x23` = 35 fits "drive past wire" and `0x012c` = 300 fits "starting point".
The sample mower in GARDENA's library has `00 3c 1e` at the same place, which
is 60 and 30 and fits the same two settings. That's two mowers pointing the
same way, but it's still **not confirmed**.

**How to help:**
1. `pip install websockets`
2. `python tools/capture.py --host <gateway-ip> --password <password>`
3. In the GARDENA app, change **one** setting. Note the time and what you changed.
4. Wait a minute, change it back, note the time again.
5. Open an issue with your notes and the matching `settings_report` lines from
   the output. Remove anything personal.
