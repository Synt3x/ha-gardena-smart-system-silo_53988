<img src="custom_components/gardena_sileno_local/brand/icon.png" alt="" width="96" align="right">

# GARDENA SILENO local (gen 1) for Home Assistant

See and control a **1st-generation GARDENA smart SILENO** robotic mower from
Home Assistant. Everything stays in your home: no cloud account, no API keys,
and updates within a second.

- **Start, dock and status** on Home Assistant's own mower card
- **Start in a zone**, with your own zone names
- **Live position on the map** (LONA mowers)
- **Battery, next start, problems, mowing hours** and more
- **Winter mode**, so a stored mower doesn't show up as a fault
- In **English and Swedish**

> [!WARNING]
> **This is a beta, for a machine with blades.** Stay near the mower the first
> time you use each command.
>
> - It was built with an AI assistant (Claude), by reverse-engineering the gateway.
>   No one has reviewed the code line by line.
> - It has been tested on **one** mower.
> - The **Dock** button's default command has **not been tried on a real mower yet**.
>   *Park until further notice* has. You can [switch](#settings).
>
> See [what is verified](docs/verified.md). Not affiliated with GARDENA or Husqvarna.

## Will it work for me?

| You need | Details |
|---|---|
| A 1st-generation smart SILENO | Tested: **smart SILENO city/life with LONA, model 53988**. Other gen-1 models (such as 29694 and 6146) are accepted but **untested**. 2nd-generation mowers are not supported. |
| A GARDENA smart Gateway | Tested: firmware **10.12.2** |
| Home Assistant 2025.1 or newer | With [HACS](https://hacs.xyz/docs/use/) installed |

Tried it on another model? Please [tell us](https://github.com/Synt3x/ha-gardena-smart-system-silo_53988/issues/new/choose), whether it worked or not.

## Install

### 1. Have two things ready

- **The gateway's IP address.** Look in your router's list of connected devices.
  Give the gateway a fixed address there (DHCP reservation).
- **The password.** Turn the gateway over. On the label, the password is the
  **first 8 characters of the ID**: `ID: 1a2b3c4d-xxxx-…` → `1a2b3c4d`. It only has
  `0`–`9` and `a`–`f`. The 8-digit number on the white sticker is something else
  (HomeKit).

### 2. Download

[![Open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Synt3x&repository=ha-gardena-smart-system-silo_53988&category=integration)

Click **Download**, then **restart Home Assistant**.

<details>
<summary>Without the button, or without HACS</summary>

**HACS:** ⋮ → **Custom repositories** → add
`https://github.com/Synt3x/ha-gardena-smart-system-silo_53988` as type
**Integration** → search for **GARDENA SILENO local (gen 1)** → **Download** →
restart Home Assistant.

**By hand:** download this repository as a ZIP, copy
`custom_components/gardena_sileno_local` into `config/custom_components/`, and
restart Home Assistant.

</details>

### 3. Add the mower

[![Add the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=gardena_sileno_local)

Or: **Settings → Devices & services → Add integration** → **GARDENA SILENO local (gen 1)**.

Enter the IP address and the password. Leave the port at 8443.

The gateway's local API is off from the factory. If so, the wizard offers to
**turn it on for you**. If that doesn't work, you can
[do it by hand](docs/manual-setup.md).

## Daily use

Add the mower card, the **Start zone** selector and the sensors you like to a
dashboard. [All entities and services](docs/entities.md) are listed separately.

- **Start** mows for the time you set (3 hours by default), from the selected
  start zone.
- **Dock** goes home and mows again at the next scheduled time. You can change that.
- **Problem** turns on only while the mower needs help.
- **Mowing ends** shows when a timed run is over.

### Settings

**Settings → Devices & services → GARDENA SILENO local → Configure**

| Setting | Choices |
|---|---|
| What the Dock button does | **Go home, mow again at the next scheduled time** (default), or **go home and stay parked until started again** |
| Mowing time for the Start button | Minutes, 180 by default |
| Zone 1–4 | Name and start distance, see [Zones](#zones) |

New IP address or password? Choose **⋮ → Reconfigure**. You don't need to remove
the integration.

## Zones

A zone is a **start point along the guide wire**. The GARDENA app keeps its zone
names in the cloud, so you enter them once under **Configure**:

1. Start the zone in the GARDENA app.
2. Read the **Start distance** sensor in Home Assistant, e.g. 45 m.
3. Enter the zone's name and that distance.

A zone without a distance uses the mower's own start area with the same number
(1–3). **Automatic** lets the mower choose, like *According to starting points*
in the app.

## Winter mode

Turn on the **Winter mode** switch when you put the mower away. While the mower
is offline:

| Entity | Shows |
|---|---|
| Mower | *Docked* |
| Status | *Winter storage* |
| Problem | Off |
| Battery, next start, mowing ends | *Unknown*, because the last values would be wrong |
| Counters, schedule, position | The last known value |
| Mower online | *Disconnected*, as it really is |

- **Unplugging the gateway too?** Turn winter mode on **first**. Home Assistant
  can then restart without it all winter.
- **While the mower is online, winter mode changes nothing.** You still see real
  problems.
- **In spring**, switch on the gateway and the mower. Winter mode turns itself
  off when the mower drives out, so it can't hide a missing mower all summer.

## Help

| Problem | What to do |
|---|---|
| The integration isn't in the list | Restart Home Assistant after downloading, then reload the page (Ctrl+F5). |
| *Nothing answers at that address* | Check the IP address and that the gateway has power. Is Home Assistant on another network or VLAN? Allow it to reach port 443 and **8443** on the gateway. |
| *Wrong password* | Only `0`–`9` and `a`–`f` are possible. `1` and `f` look alike on the label. |
| *The local API doesn't answer yet* | Wait a minute and try again. If it keeps failing, check that port 8443 isn't blocked between Home Assistant and the gateway. |
| Entities are *Unavailable* | The gateway can't reach the mower. Check that the mower is on. Put away? Use [Winter mode](#winter-mode). A second of *Unavailable* during a restart is normal. |
| The integration keeps retrying | The gateway is off, has lost the local API (factory reset), or doesn't list the mower yet. After a power cut, wait a few minutes. Otherwise choose **⋮ → Reconfigure**. |
| *Next start* is *Unknown* | The mower is mowing, or parked until further notice. |
| A value hasn't changed for long | It may simply be the same. **Last contact** shows when the mower last reported. |
| Collisions keep going up | Normal. [Why?](#why-does-a-lona-mower-still-bump-into-things) |
| Something else | [Open an issue](https://github.com/Synt3x/ha-gardena-smart-system-silo_53988/issues/new/choose) and attach **⋮ → Download diagnostics**. Password, address, serial number and position are removed from it. |

To get a detailed log: **⋮ → Enable debug logging**, reproduce the problem, then
turn it off again.

### Why does a LONA mower still bump into things?

LONA is GPS for tracking and zones, not obstacle detection. These mowers drive
until they touch something, then turn. The mower this was built on has about 20
collisions per mowing hour. A **sudden** increase can mean a new obstacle, or that
it's stuck somewhere.

### How do I update or remove it?

HACS shows updates under **Settings → Updates**. Install and restart. To remove
it, delete the integration under **Devices & services**, then remove it in HACS
and restart. The gateway's local API stays on until you
[turn it off](docs/manual-setup.md#turn-it-off-again).

## Security and privacy

- **All traffic stays on your network.** Nothing is sent to the internet by this
  integration.
- While the local API is on, **anyone on your network who knows the password can
  control your GARDENA devices**. Never open port 8443 (or 443) of the gateway to
  the internet.
- **The gateway's certificate is self-signed and isn't checked.** Someone already
  inside your network could pose as the gateway and read the password. Use a
  network you trust.
- The mower's position is your home. It's stored in your Home Assistant history,
  like any device tracker.
- GARDENA places the local API under *Advanced* on the gateway, with a warning that
  such settings may affect the warranty.

## More

- [Entities and services](docs/entities.md)
- [What is verified and what isn't](docs/verified.md)
- [Turn the local API on or off by hand](docs/manual-setup.md)
- [Technical notes and the protocol](docs/technical.md), and how to help decode the rest
- [For developers](docs/development.md) · [Changelog](CHANGELOG.md) · [Plans and known issues](https://github.com/Synt3x/ha-gardena-smart-system-silo_53988/issues) · [Decisions](docs/decisions.md)

## Sources and credits

- GARDENA's official local API library and model schemas (LGPL-3.0):
  [gardena-smart-local-api](https://github.com/cloudless-garden/gardena-smart-local-api)
- Password rule, port and local/cloud approach:
  [ha-gardena-smart-system](https://github.com/kayloehmann/ha-gardena-smart-system)
- Husqvarna Automower error numbering:
  [aioautomower](https://github.com/Thomas55555/aioautomower)
- [GARDENA smart Gateway open-source components](https://github.com/husqvarnagroup/smart-garden-gateway-public),
  the SILENO city operator's manual and GARDENA's product pages

This integration contains no code from these projects. The protocol was
re-implemented from their documentation, schema files and observed behaviour.

[MIT license](LICENSE)
