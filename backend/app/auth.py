"""Minimal auth: PBKDF2 password hashes + HMAC-signed bearer tokens (no extra deps)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Header, HTTPException

from .config import JWT_SECRET

TOKEN_TTL = 60 * 60 * 24 * 7


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(test.hex(), dk)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: str, role: str, patient_id: str | None) -> str:
    payload = _b64(json.dumps({"uid": user_id, "role": role, "pid": patient_id, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig = _b64(hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str) -> dict:
    try:
        payload, sig = token.split(".")
    except ValueError:
        raise HTTPException(401, "Your session is no longer valid. Please sign in again.")
    good = _b64(hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, good):
        raise HTTPException(401, "Your session is no longer valid. Please sign in again.")
    data = json.loads(_unb64(payload))
    if data["exp"] < time.time():
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return data


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    user = read_token(authorization.split(" ", 1)[1])
    from . import db  # the account may have been removed (e.g. demo data reset) since the token was issued
    if not db.q1("SELECT 1 FROM users WHERE id = %s", (user["uid"],)):
        raise HTTPException(401, "Your session is no longer valid. Please sign in again.")
    return user


def require_role(user: dict, *roles: str) -> None:
    if user["role"] not in roles:
        raise HTTPException(403, "Not allowed for this account type")
