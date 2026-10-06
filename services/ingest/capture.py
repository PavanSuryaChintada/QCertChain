"""Record raw certstream messages to JSONL. Demo insurance and replay source (DATA.md §1)."""
import argparse
import asyncio
import json
import time

import websockets

from services.config import SETTINGS


async def capture(url: str, minutes: float, out: str) -> int:
    n, deadline = 0, time.time() + minutes * 60
    with open(out, "a", encoding="utf-8") as f:
        while time.time() < deadline:
            try:
                async with websockets.connect(url, max_size=2**24, open_timeout=20) as ws:
                    while time.time() < deadline:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        msg = json.loads(raw)
                        if msg.get("message_type") == "certificate_update":
                            f.write(json.dumps(msg, separators=(",", ":")) + "\n")
                            n += 1
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
                print(f"capture: connection issue {type(e).__name__}: {e}; retrying in 5s", flush=True)
                await asyncio.sleep(5)
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--out", default="data/capture.jsonl")
    ap.add_argument("--url", default=SETTINGS.certstream_url)
    a = ap.parse_args()
    print("captured", asyncio.run(capture(a.url, a.minutes, a.out)))
