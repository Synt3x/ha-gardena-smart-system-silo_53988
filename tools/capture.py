"""Read-only capture of everything the GARDENA gateway sends.

Used to decode unknown binary fields: run it, change ONE setting in the
GARDENA app, note the time, and compare the hex before and after.

    pip install websockets
    python tools/capture.py --host 192.168.1.50 --password abcd1234 --out capture.jsonl

Sends only the discovery "read" request. Never writes to the mower.
"""

import argparse
import asyncio
import base64
import json
import ssl
import time
import uuid


def show(value):
    if isinstance(value, dict):
        if value.get("vo"):
            return base64.b64decode(value["vo"]).hex(" ")
        for key in ("vi", "vf", "vb", "vs", "ai", "as"):
            if key in value:
                return value[key]
    return value


async def main(args):
    import websockets

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    auth = base64.b64encode(f"_:{args.password}".encode()).decode()
    end = time.time() + args.seconds
    async with websockets.connect(
        f"wss://{args.host}:8443",
        ssl=ctx,
        close_timeout=0,
        ping_interval=30,
        additional_headers={"Authorization": f"Basic {auth}"},
    ) as ws:
        await ws.send(json.dumps([
            {"op": "read", "entity": {"service": s, "path": "devices"}, "request_id": str(uuid.uuid4())}
            for s in ("lemonbeatd", "lwm2mserver")
        ]))
        with open(args.out, "a", encoding="utf-8") as log:
            while time.time() < end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                log.write(json.dumps({"t": time.time(), "msg": json.loads(raw)}) + "\n")
                log.flush()
                stamp = time.strftime("%H:%M:%S")
                for msg in json.loads(raw):
                    if msg.get("op"):
                        print(f"{stamp} {msg['op']} {msg.get('entity', {}).get('path')}", flush=True)
                        for key, value in (msg.get("payload") or {}).items():
                            if not key.startswith("_"):
                                print(f"    {key} = {show(value)}", flush=True)
                    elif msg.get("request_id"):
                        print(f"{stamp} full state received ({len(msg.get('payload') or {})} devices)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True)
    parser.add_argument("--password", required=True, help="First 8 characters of the gateway ID")
    parser.add_argument("--out", default="capture.jsonl")
    parser.add_argument("--seconds", type=int, default=3600)
    asyncio.run(main(parser.parse_args()))
