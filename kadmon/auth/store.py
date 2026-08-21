"""Vendor-keyed token store.

Each vendor owns one table in `~/.config/kadmon/tokens.toml`. Extra keys on a
table round-trip, so a Grok write cannot strip a Codex `id_token`.
"""

from __future__ import annotations

import os
import time
import tomllib
from dataclasses import dataclass, field

from kadmon.config import GLOBAL_CONFIG_DIR, _toml_str

TOKENS_PATH = GLOBAL_CONFIG_DIR / "tokens.toml"

_KNOWN = ("access_token", "refresh_token", "expires_at", "account")
_Scalar = str | int | float | bool


class AuthError(Exception):
    """Sign-in failed. The message tells the user what to do next."""


@dataclass
class Grant:
    """One live subscription session."""

    access_token: str
    refresh_token: str = ""
    expires_at: int = 0
    account: str = ""
    extra: dict[str, _Scalar] = field(default_factory=dict)

    def expires_within(self, seconds: int, now: float | None = None) -> bool:
        """True when the access token is about to expire, or already has."""
        if not self.expires_at:
            return False
        return self.expires_at - (now if now is not None else time.time()) <= seconds


def load(vendor: str) -> Grant | None:
    """Read `vendor`'s grant. Returns None when there is none."""
    entry = _read_store().get(vendor)
    if not isinstance(entry, dict) or not entry.get("access_token"):
        return None
    extra = {
        key: value
        for key, value in entry.items()
        if key not in _KNOWN and _is_scalar(value)
    }
    return Grant(
        access_token=str(entry.get("access_token", "")),
        refresh_token=str(entry.get("refresh_token", "")),
        expires_at=int(entry.get("expires_at", 0) or 0),
        account=str(entry.get("account", "")),
        extra=extra,
    )


def save(vendor: str, grant: Grant) -> None:
    """Store `vendor`'s grant, readable only by this user.

    Writes a temp file in the same directory and renames it over the target, so
    two Kadmon runs cannot leave a half-written store behind.
    """
    data = _read_store()
    entry: dict[str, _Scalar] = {
        "access_token": grant.access_token,
        "refresh_token": grant.refresh_token,
        "expires_at": grant.expires_at,
        "account": grant.account,
    }
    for key, value in grant.extra.items():
        if key not in entry:
            entry[key] = value
    data[vendor] = entry
    _write_store(data)


def clear(vendor: str) -> None:
    """Drop `vendor`'s grant. Leaves any other vendor's entry alone."""
    data = _read_store()
    if data.pop(vendor, None) is None:
        return
    _write_store(data)


def _read_store() -> dict:
    if not TOKENS_PATH.exists():
        return {}
    try:
        return tomllib.loads(TOKENS_PATH.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AuthError(
            f"Cannot read {TOKENS_PATH}: {exc}. Delete it and run 'kadmon login'."
        ) from exc


def _write_store(data: dict) -> None:
    lines = ["# Kadmon subscription tokens — keep private", ""]
    for vendor, entry in data.items():
        if not isinstance(entry, dict):
            continue
        lines.append(f"[{vendor}]")
        for key, value in entry.items():
            if _is_scalar(value):
                lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")

    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = TOKENS_PATH.with_name(f"{TOKENS_PATH.name}.{os.getpid()}.tmp")
    temp.write_text("\n".join(lines))
    temp.chmod(0o600)
    os.replace(temp, TOKENS_PATH)
    # `os.replace` keeps the temp file's mode, but re-apply it so a store that
    # existed with looser permissions cannot survive a write.
    TOKENS_PATH.chmod(0o600)


def _is_scalar(value: object) -> bool:
    return isinstance(value, (str, int, float, bool))


def _toml_value(value: _Scalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _toml_str(value)
