# For developers

## Structure

| Path | What |
|---|---|
| `custom_components/gardena_sileno_local/api.py` | Gateway client (WebSocket) and turning on the local API. No Home Assistant imports. |
| `…/decode.py` | Pure functions that decode the mower's values. No Home Assistant imports. |
| `…/__init__.py` | Setup, coordinator, reconnecting, winter mode |
| `…/config_flow.py` | Setup wizard, reconfigure, reauth, options |
| `…/entity.py` | Base entity: availability and mower commands |
| `…/sensor.py`, `switch.py`, … | One file per platform |
| `tests/` | Automated tests, with a simulated gateway |
| `tools/capture.py` | Read-only logger for a real gateway |

## Tests

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Home Assistant's test tools need Linux or macOS (on Windows: WSL). GitHub Actions
runs the tests on the oldest supported and a current Home Assistant, plus
`hassfest` and the HACS validation, on every push and once a week.

No test talks to a real gateway. Anything that moves the mower must also be tried
on hardware, with someone watching it, before [verified.md](verified.md) says ✅.

## Plans

Features, hardware tests and known problems are
[GitHub issues](https://github.com/Synt3x/ha-gardena-smart-system-silo_53988/issues).

## Releasing

1. Set the version in `manifest.json` and update `CHANGELOG.md`.
2. Update [decisions.md](decisions.md) and [verified.md](verified.md).
3. Wait for GitHub Actions to pass.
4. Create a GitHub release with the tag `v<version>`. Mark it as a pre-release
   while this is a beta.

Texts live in `strings.json`, with the same content in `translations/en.json`.
Every key must also be in `translations/sv.json`; a test checks it.
