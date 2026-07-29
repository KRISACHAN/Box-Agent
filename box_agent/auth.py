"""Shared request-auth helpers for hosted Box-Agent integrations."""

from __future__ import annotations

import os
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

AUTH_TOKEN_ENV_VARS = (
    "BOX_AGENT_AUTH_TOKEN",
    "OFFICEV3_AUTH_TOKEN",
    "RACCOON_ACCESS_TOKEN",
    "RACCOON_TOKEN",
)

AUTH_TOKEN_FILE_KEYS = ("token", "access_token", "auth_token")
AUTH_HEADER_HOST_SUFFIXES = ("xiaohuanxiong.com", "10.158.136.99")


def _coerce_token(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    return ""


def read_auth_token_file(auth_file: str | Path | None) -> str:
    """Read a bearer token from auth.json.

    The file is intentionally separate from config.yaml because login tokens
    rotate independently from model/provider settings. Supported shapes:
    ``{"access_token": "..."}``, ``{"token": "..."}``, or
    ``{"auth_token": "..."}``.
    """
    if not auth_file:
        return ""

    path = Path(auth_file).expanduser()
    if not path.exists():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    if not isinstance(data, dict):
        return ""

    for key in AUTH_TOKEN_FILE_KEYS:
        token = _coerce_token(data.get(key))
        if token:
            return token
    return ""


def resolve_auth_token(
    explicit: str | None = None,
    auth_file: str | Path | None = None,
) -> str:
    """Return an explicit, auth-file, or environment login token."""
    if explicit is not None and explicit.strip():
        return explicit.strip()

    file_token = read_auth_token_file(auth_file)
    if file_token:
        return file_token

    for name in AUTH_TOKEN_ENV_VARS:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    return ""


def bearer_auth_headers(
    token: str | None,
    existing: Mapping[str, str | bytes] | None = None,
    url: str | None = None,
) -> dict[str, str | bytes]:
    """Return headers with ``Authorization: Bearer <token>`` when safe.

    Existing Authorization headers are preserved so user-configured provider
    or MCP credentials are not overwritten by the officev3 login token.
    """
    headers = dict(existing or {})
    if not token:
        return headers

    if url and not should_attach_auth_header(url):
        return headers

    for key in headers:
        if key.lower() == "authorization":
            return headers

    headers["Authorization"] = f"Bearer {token}"
    return headers


def should_attach_auth_header(url: str) -> bool:
    """True for hosted officev3 gateway URLs that expect the login token."""
    try:
        hostname = urlparse(url).hostname or ""
    except ValueError:
        return False

    hostname = hostname.lower().rstrip(".")
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in AUTH_HEADER_HOST_SUFFIXES
    )


def request_auth_headers(
    auth_file: str | Path | None = None,
    explicit_token: str | None = None,
    existing: Mapping[str, str | bytes] | None = None,
    url: str | None = None,
) -> dict[str, str | bytes]:
    """Return request headers after reading the current auth token."""
    return bearer_auth_headers(resolve_auth_token(explicit_token, auth_file), existing, url=url)
