"""Sealed key copies (spec 2026-10-09 §3). The SHA-256 hash stays the lookup path; a sealed copy exists only so the
super admin panel and the public sign-in list (read-only keys) can show a key again. SecretBox under
KEY_SEAL_SECRET (32 random bytes, hex, in .env). Without the secret nothing is sealed: keys are then shown once."""
from __future__ import annotations

from nacl import secret

from services.config import SETTINGS


def _box() -> secret.SecretBox | None:
    k = SETTINGS.key_seal_secret
    return secret.SecretBox(bytes.fromhex(k)) if k else None


def seal(text: str) -> bytes | None:
    box = _box()
    return bytes(box.encrypt(text.encode("utf-8"))) if box else None


def unseal(blob: bytes) -> str:
    """Raises nacl.exceptions.CryptoError on a wrong secret or altered bytes: it fails closed."""
    box = _box()
    if box is None:
        raise RuntimeError("KEY_SEAL_SECRET is not set")
    return box.decrypt(bytes(blob)).decode("utf-8")
