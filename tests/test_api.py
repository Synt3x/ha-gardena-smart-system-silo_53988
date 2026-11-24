"""The client against a real TLS server on localhost."""

from __future__ import annotations

import datetime
import json
import ssl

import aiohttp
import pytest
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.gardena_sileno_local import api

from .const import MOWER_ID, STATE

PASSWORD = "1a2b3c4d"


@pytest.fixture
def tls(tmp_path) -> ssl.SSLContext:
    """A self-signed certificate, like the gateway's."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "gateway")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "gateway.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        + cert.public_bytes(serialization.Encoding.PEM)
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(path)
    return context


class Server:
    """The gateway: web page API and WebSocket on one port."""

    def __init__(self) -> None:
        self.enabled: list[dict] = []
        self.received: list[dict] = []
        self.socket: web.WebSocketResponse | None = None
        self.login_body: dict | list = {"session": "token-1"}
        self.port = 0

    async def version(self, _request):
        return web.Response(text="10.12.2")

    async def login(self, request):
        if (await request.json())["password"] != PASSWORD:
            return web.Response(status=401)
        return web.json_response(self.login_body)

    async def websocket_api(self, request):
        if request.headers.get("X-Session") != "token-1":
            return web.Response(status=401)
        self.enabled.append(await request.json())
        return web.Response()

    async def websocket(self, request):
        if request.headers.get("Authorization") != "Basic XzoxYTJiM2M0ZA==":  # _:1a2b3c4d
            return web.Response(status=401)
        self.socket = web.WebSocketResponse()
        await self.socket.prepare(request)
        async for message in self.socket:
            for item in json.loads(message.data):
                self.received.append(item)
                reply = {"request_id": item["request_id"], "success": True}
                if item["op"] == "read" and item["entity"]["service"] == "lemonbeatd":
                    reply["payload"] = {MOWER_ID: STATE}
                if item["entity"]["path"] == "refused":
                    reply |= {"success": False, "payload": {"vs": "not allowed"}}
                await self.socket.send_str(json.dumps([reply]))
        return self.socket


@pytest.fixture
async def server(tls, socket_enabled):
    gateway = Server()
    app = web.Application()
    app.add_routes(
        [
            web.get("/version", gateway.version),
            web.post("/login", gateway.login),
            web.put("/websocket_api", gateway.websocket_api),
            web.get("/", gateway.websocket),
        ]
    )
    runner = web.AppRunner(app, shutdown_timeout=0.1)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=tls)
    await site.start()
    gateway.port = runner.addresses[0][1]
    yield gateway
    await runner.cleanup()


@pytest.fixture
async def session(socket_enabled):
    connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as client_session:
        yield client_session


async def test_web_answers(server, session):
    assert await api.gateway_web_answers(session, f"127.0.0.1:{server.port}")
    assert not await api.gateway_web_answers(session, "127.0.0.1:1")


async def test_enable(server, session):
    await api.enable_local_api(session, f"127.0.0.1:{server.port}", PASSWORD)
    assert server.enabled == [{"enable": True}]


async def test_enable_wrong_password(server, session):
    with pytest.raises(api.InvalidAuth):
        await api.enable_local_api(session, f"127.0.0.1:{server.port}", "ffffffff")
    assert not server.enabled


@pytest.mark.parametrize("body", [{}, ["unexpected"]])
async def test_enable_unexpected_login_answer(server, session, body):
    server.login_body = body
    with pytest.raises(api.CannotConnect):
        await api.enable_local_api(session, f"127.0.0.1:{server.port}", PASSWORD)
    assert not server.enabled


async def test_client(server, session):
    client = api.GardenaLocalClient(session, "127.0.0.1", PASSWORD, server.port)
    await client.connect()
    devices = await client.discover()
    assert devices[MOWER_ID]["service"] == "lemonbeatd"

    with pytest.raises(api.CommandFailed, match="not allowed"):
        await client.write(MOWER_ID, "refused", {"vi": 1})
    await client.write(MOWER_ID, "lemonbeat/0/x", {"vi": 1})
    assert server.received[-1]["entity"]["device"] == MOWER_ID

    updates = []
    client.add_listener(lambda: updates.append(client.devices[MOWER_ID]["data"]))
    event = {
        "op": "update",
        "entity": {"device": MOWER_ID, "path": "lemonbeat/0"},
        "payload": {"status": {"vi": 15}},
    }
    await server.socket.send_str(json.dumps([event]))
    await client.write(MOWER_ID, "lemonbeat/0/x", {"vi": 1})
    assert updates[-1]["lemonbeat"]["0"]["status"] == {"vi": 15, "ts": 1794064692}
    assert updates[-1]["lemonbeat"]["0"]["battery_level"]["vi"] == 77

    await server.socket.close()
    await client.wait_closed()
    with pytest.raises(api.CannotConnect):
        await client.write(MOWER_ID, "lemonbeat/0/x", {"vi": 1})
    await client.shutdown()


async def test_client_wrong_password(server, session):
    client = api.GardenaLocalClient(session, "127.0.0.1", "ffffffff", server.port)
    with pytest.raises(api.InvalidAuth):
        await client.connect()
    await client.shutdown()
