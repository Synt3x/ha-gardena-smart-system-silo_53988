"""Client for the GARDENA smart Gateway local WebSocket API.

No Home Assistant imports, so it can be tested on its own.

Protocol (from gardena-smart-local-api and live testing):
- wss://<gateway>:8443, HTTP Basic auth, user "_", password = first 8
  characters of the gateway ID. Self-signed certificate.
- Requests are JSON arrays of {"op", "entity": {"service", "path", "device"},
  "payload", "request_id"}. Ops: read, write, execute.
- The gateway sends no snapshot on connect. A "read" of path "devices" per
  service returns every device with its full state.
- Afterwards it pushes events {"op": update|overwrite|delete, "entity":
  {"device", "path"}, "payload"} where payload is relative to the path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

SERVICES = ("lemonbeatd", "lwm2mserver")
DEFAULT_PORT = 8443
REQUEST_TIMEOUT = 20
CONNECT_TIMEOUT = 10


class GardenaLocalError(Exception):
    """Base error."""


class CannotConnect(GardenaLocalError):
    """Gateway unreachable or the WebSocket API is off."""


class InvalidAuth(GardenaLocalError):
    """Wrong password."""


class CommandFailed(GardenaLocalError):
    """The gateway rejected a request."""


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _delete_path(target: dict[str, Any], segments: list[str]) -> None:
    node: Any = target
    for key in segments[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return
    if isinstance(node, dict) and segments:
        node.pop(segments[-1], None)


class GardenaLocalClient:
    """One WebSocket connection to one gateway."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        password: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._session = session
        self._url = f"wss://{host}:{port}"
        self._headers = {"Authorization": aiohttp.BasicAuth("_", password).encode()}
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._listeners: list[Callable[[], None]] = []
        self._closed = asyncio.Event()
        self.stopped = False
        # device id -> {"service": str, "data": nested objects}
        self.devices: dict[str, dict[str, Any]] = {}

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    async def connect(self) -> None:
        if self.stopped:
            raise CannotConnect("Client is shut down")
        self._closed.clear()
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                self._ws = await self._session.ws_connect(
                    self._url,
                    headers=self._headers,
                    ssl=False,
                    heartbeat=30,
                    timeout=aiohttp.ClientWSTimeout(ws_close=5),
                )
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise InvalidAuth("Wrong password") from err
            raise CannotConnect(f"Handshake failed: {err.status}") from err
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as err:
            raise CannotConnect(str(err) or type(err).__name__) from err
        self._reader = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
        self._fail_pending(CannotConnect("Connection closed"))
        self._closed.set()

    async def shutdown(self) -> None:
        """Close for good; connect() refuses afterwards."""
        self.stopped = True
        await self.close()

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def discover(self) -> dict[str, dict[str, Any]]:
        """Read all devices with full state from every service."""
        results = await asyncio.gather(
            *(self._request("read", service, "devices") for service in SERVICES),
            return_exceptions=True,
        )
        found: dict[str, dict[str, Any]] = {}
        for service, result in zip(SERVICES, results):
            if isinstance(result, BaseException):
                _LOGGER.debug("Discovery on %s failed: %s", service, result)
                continue
            for device_id, objects in (result.get("payload") or {}).items():
                if device_id.startswith("_") or not isinstance(objects, dict):
                    continue
                found[device_id] = {"service": service, "data": objects}
        if not found and all(isinstance(r, BaseException) for r in results):
            raise CannotConnect(f"Discovery failed: {results[0]}")
        self.devices = found
        self._notify()
        return found

    async def write(
        self, device_id: str, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        device = self.devices.get(device_id)
        if device is None:
            raise CommandFailed("The gateway no longer reports this mower")
        return await self._request("write", device["service"], path, device_id, payload)

    async def _request(
        self,
        op: str,
        service: str,
        path: str,
        device: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.connected:
            raise CannotConnect("Not connected")
        request_id = str(uuid.uuid4())
        entity: dict[str, Any] = {"service": service, "path": path}
        if device:
            entity["device"] = device
        message: dict[str, Any] = {"op": op, "entity": entity, "request_id": request_id}
        if payload is not None:
            message["payload"] = payload
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._ws.send_str(json.dumps([message]))
            reply = await asyncio.wait_for(future, REQUEST_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise CommandFailed(f"No reply to {op} {path}") from err
        except (aiohttp.ClientError, ConnectionError) as err:
            raise CannotConnect(f"Connection lost while sending {op} {path}") from err
        finally:
            self._pending.pop(request_id, None)
        if reply.get("success") is False:
            text = (reply.get("payload") or {}).get("vs", "unknown error")
            raise CommandFailed(f"{op} {path}: {text}")
        return reply

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle(msg.data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("WebSocket read failed: %s", err)
        finally:
            self._fail_pending(CannotConnect("Connection lost"))
            self._closed.set()

    def _handle(self, raw: str) -> None:
        try:
            messages = json.loads(raw)
        except ValueError:
            _LOGGER.debug("Ignoring non-JSON message: %.200s", raw)
            return
        if not isinstance(messages, list):
            messages = [messages]
        changed = False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            request_id = msg.get("request_id")
            if request_id in self._pending:
                future = self._pending[request_id]
                if not future.done():
                    future.set_result(msg)
                continue
            if msg.get("op") in ("update", "overwrite", "delete"):
                changed |= self._apply_event(msg)
            elif msg.get("success") is False:
                # Some gateway errors carry no request_id. With exactly one
                # request in flight, it must be the answer to that request.
                if len(self._pending) == 1:
                    future = next(iter(self._pending.values()))
                    if not future.done():
                        future.set_result(msg)
                else:
                    _LOGGER.debug("Unmatched gateway error: %s", msg)
        if changed:
            self._notify()

    def _apply_event(self, msg: dict[str, Any]) -> bool:
        entity = msg.get("entity") or {}
        device = self.devices.get(entity.get("device"))
        if device is None:
            return False
        segments = [s for s in str(entity.get("path") or "").split("/") if s]
        if msg["op"] == "delete":
            _delete_path(device["data"], segments)
            return True
        payload = msg.get("payload")
        if not isinstance(payload, dict) or not payload:
            return False
        nested: dict[str, Any] = payload
        for key in reversed(segments):
            nested = {key: nested}
        if msg["op"] == "overwrite":
            _delete_path(device["data"], segments)
        _deep_merge(device["data"], nested)
        return True

    def _fail_pending(self, err: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(err)
        self._pending.clear()

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener failed")
