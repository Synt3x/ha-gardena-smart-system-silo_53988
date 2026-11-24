"""Shared fixtures: a simulated gateway and a config entry."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_sileno_local import api
from custom_components.gardena_sileno_local.const import DOMAIN

from .const import MOWER_ID, STATE


class FakeWebSocket:
    closed = False

    async def close(self) -> None:
        self.closed = True


class FakeGateway:
    """Stands in for the network part of GardenaLocalClient."""

    def __init__(self) -> None:
        self.up = True
        self.read_fails = False
        self.password = "1a2b3c4d"
        self.mowers: dict[str, Any] = {MOWER_ID: copy.deepcopy(STATE)}
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.client: api.GardenaLocalClient | None = None

    def push(self, path: str, payload: dict[str, Any]) -> None:
        message = {
            "op": "update",
            "entity": {"device": MOWER_ID, "path": path},
            "payload": payload,
        }
        self.client._handle(json.dumps([message]))

    def set_online(self, online: bool) -> None:
        field = {"ts": 2, "vb": online}
        self.mowers[MOWER_ID]["connection_status"]["0"]["online"] = field
        self.push("connection_status/0", {"online": dict(field)})

    def set_status(self, code: int) -> None:
        field = {"ts": 2, "vi": code}
        self.mowers[MOWER_ID]["lemonbeat"]["0"]["status"] = field
        self.push("lemonbeat/0", {"status": dict(field)})

    def go_down(self) -> None:
        self.up = False
        self.client._ws.closed = True
        self.client._closed.set()


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> FakeGateway:
    fake = FakeGateway()

    async def connect(self: api.GardenaLocalClient) -> None:
        if self.stopped:
            raise api.CannotConnect("Client is shut down")
        self._closed.clear()
        if not fake.up:
            raise api.CannotConnect("no route to host")
        if self._headers["Authorization"] != api.basic_auth(fake.password):
            raise api.InvalidAuth("Wrong password")
        self._ws = FakeWebSocket()
        fake.client = self

    async def request(self, op, service, path, device=None, payload=None):
        if not fake.up or not self.connected:
            raise api.CannotConnect("Not connected")
        if op == "write":
            fake.writes.append((path, payload))
            return {"success": True}
        if fake.read_fails:
            raise api.CommandFailed("No reply to read devices")
        if service != "lemonbeatd":
            return {"payload": {}}
        return {"payload": copy.deepcopy(fake.mowers)}

    monkeypatch.setattr(api.GardenaLocalClient, "connect", connect)
    monkeypatch.setattr(api.GardenaLocalClient, "_request", request)
    monkeypatch.setattr("custom_components.gardena_sileno_local.RECONNECT_DELAY", 0.01)
    monkeypatch.setattr("custom_components.gardena_sileno_local.config_flow.API_START_WAIT", 0)
    return fake


@pytest.fixture
def entry(hass, enable_custom_integrations) -> MockConfigEntry:
    mock = MockConfigEntry(
        domain=DOMAIN,
        title="GARDENA SILENO",
        unique_id=MOWER_ID,
        data={CONF_HOST: "192.0.2.10", CONF_PASSWORD: "1a2b3c4d", CONF_PORT: 8443},
    )
    mock.add_to_hass(hass)
    return mock
