"""S3c kill switch for the credential-exfiltration signals (S1 `exfil`, S2 `js_post`).

The configured strengths live in services/config.py (set from the S3 false-positive gate). This adds a runtime
override in Redis that the enrichment worker reads for EVERY domain it confirms, so a signal can be switched off
during an evaluation without a redeploy or a restart:

    POST /admin/signals {"exfil": "off", "js_post": "off"}      (admin key)    DELETE /admin/signals to clear
    redis-cli HSET confirm:signal_strengths exfil off js_post off

The override can only LOWER a strength (strong -> moderate -> off), never raise it: promoting a signal past the gate
takes a config change and a commit, not a runtime switch.
"""
from __future__ import annotations

from services.config import SETTINGS

KEY = "confirm:signal_strengths"
ORDER = ("off", "moderate", "strong")
SIGNALS = ("exfil", "js_post")


def configured() -> dict[str, str]:
    return {"exfil": SETTINGS.exfil_signal_strength, "js_post": SETTINGS.js_post_signal_strength}


def effective(conf: dict[str, str], override: dict[str, str]) -> dict[str, str]:
    out = {}
    for k in SIGNALS:
        base = conf.get(k, "off") if conf.get(k, "off") in ORDER else "off"
        o = override.get(k)
        out[k] = o if o in ORDER and ORDER.index(o) < ORDER.index(base) else base
    return out


def _text(x) -> str:
    return x.decode() if isinstance(x, bytes) else x


async def current(redis) -> dict[str, str]:
    raw = await redis.hgetall(KEY) or {}
    return effective(configured(), {_text(k): _text(v) for k, v in raw.items()})


async def set_override(redis, values: dict[str, str]) -> None:
    clean = {k: v for k, v in values.items() if k in SIGNALS and v in ORDER}
    if clean:
        await redis.hset(KEY, mapping=clean)


async def clear(redis) -> None:
    await redis.delete(KEY)
