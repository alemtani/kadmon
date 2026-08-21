"""Device-code sign-in for xAI Grok.

Kadmon signs in with the public Grok CLI client. Usage then draws from the
SuperGrok pool instead of a pay-per-token console key.

Tokens live in `~/.config/kadmon/tokens.toml`, mode 0600. They never go into
`config.toml` and never leave this machine.

The endpoints below come from xAI's OIDC discovery document at
`https://auth.x.ai/.well-known/openid-configuration`. See
`docs/subscription-auth.md` for the spike that pinned them.
"""

import base64
import json
import os
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from kadmon.config import GLOBAL_CONFIG_DIR, _toml_str

ISSUER = "https://auth.x.ai"
DEVICE_CODE_URL = f"{ISSUER}/oauth2/device/code"
TOKEN_URL = f"{ISSUER}/oauth2/token"

# The public Grok CLI client. Kadmon does not register a client of its own.
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"

# `offline_access` buys the refresh token. `team:read` and `org:read` exist but
# xAI rejects them for a personal account, so they are not asked for.
SCOPE = (
    "openid profile email offline_access api:access grok-cli:access "
    "conversations:read conversations:write workspaces:read workspaces:write"
)

DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

TOKENS_PATH = GLOBAL_CONFIG_DIR / "tokens.toml"

# Refresh this many seconds before the access token expires.
REFRESH_WINDOW = 60

_FORM_HEADERS = {
    "content-type": "application/x-www-form-urlencoded",
    "accept": "application/json",
}


class AuthError(Exception):
    """Sign-in failed. The message tells the user what to do next."""


@dataclass
class Grant:
    """One live subscription session."""

    access_token: str
    refresh_token: str = ""
    expires_at: int = 0
    account: str = ""

    def expires_within(self, seconds: int, now: float | None = None) -> bool:
        """True when the access token is about to expire, or already has."""
        if not self.expires_at:
            return False
        return self.expires_at - (now if now is not None else time.time()) <= seconds


@dataclass
class DeviceCode:
    """What the device-code endpoint hands back so the user can approve."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str = ""
    expires_in: int = 600
    interval: int = 5

    @property
    def url(self) -> str:
        """The URL to show. The complete form carries the code already."""
        return self.verification_uri_complete or self.verification_uri


# --- token store ---


def load_grant() -> Grant | None:
    """Read the stored Grok grant. Returns None when there is none."""
    if not TOKENS_PATH.exists():
        return None
    try:
        data = tomllib.loads(TOKENS_PATH.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AuthError(
            f"Cannot read {TOKENS_PATH}: {exc}. Delete it and run 'kadmon login grok'."
        ) from exc

    entry = data.get("grok")
    if not isinstance(entry, dict) or not entry.get("access_token"):
        return None
    return Grant(
        access_token=str(entry.get("access_token", "")),
        refresh_token=str(entry.get("refresh_token", "")),
        expires_at=int(entry.get("expires_at", 0) or 0),
        account=str(entry.get("account", "")),
    )


def save_grant(grant: Grant) -> None:
    """Store the Grok grant, readable only by this user.

    Writes a temp file in the same directory and renames it over the target, so
    two Kadmon runs cannot leave a half-written store behind.
    """
    data = _read_store()
    data["grok"] = {
        "access_token": grant.access_token,
        "refresh_token": grant.refresh_token,
        "expires_at": grant.expires_at,
        "account": grant.account,
    }
    _write_store(data)


def clear_grant() -> None:
    """Drop the Grok grant. Leaves any other vendor's entry alone."""
    data = _read_store()
    if data.pop("grok", None) is None:
        return
    _write_store(data)


def _read_store() -> dict:
    if not TOKENS_PATH.exists():
        return {}
    try:
        return tomllib.loads(TOKENS_PATH.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AuthError(
            f"Cannot read {TOKENS_PATH}: {exc}. Delete it and run 'kadmon login grok'."
        ) from exc


def _write_store(data: dict) -> None:
    lines = ["# Kadmon subscription tokens — keep private", ""]
    for vendor, entry in data.items():
        if not isinstance(entry, dict):
            continue
        lines.append(f"[{vendor}]")
        lines.append(f"access_token = {_toml_str(str(entry.get('access_token', '')))}")
        lines.append(f"refresh_token = {_toml_str(str(entry.get('refresh_token', '')))}")
        lines.append(f"expires_at = {int(entry.get('expires_at', 0) or 0)}")
        lines.append(f"account = {_toml_str(str(entry.get('account', '')))}")
        lines.append("")

    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = TOKENS_PATH.with_name(f"{TOKENS_PATH.name}.{os.getpid()}.tmp")
    temp.write_text("\n".join(lines))
    temp.chmod(0o600)
    os.replace(temp, TOKENS_PATH)
    # `os.replace` keeps the temp file's mode, but re-apply it so a store that
    # existed with looser permissions cannot survive a write.
    TOKENS_PATH.chmod(0o600)


# --- device-code flow ---


def request_device_code() -> DeviceCode:
    """Ask xAI for a device code and the URL the user must open."""
    payload = _post_form(DEVICE_CODE_URL, {"client_id": CLIENT_ID, "scope": SCOPE})
    try:
        return DeviceCode(
            device_code=payload["device_code"],
            user_code=payload["user_code"],
            verification_uri=payload["verification_uri"],
            verification_uri_complete=payload.get("verification_uri_complete", ""),
            expires_in=int(payload.get("expires_in", 600)),
            interval=int(payload.get("interval", 5)),
        )
    except KeyError as exc:
        raise AuthError(f"xAI returned no {exc.args[0]}. Try 'kadmon login grok' again.") from exc


def poll_for_grant(device: DeviceCode, sleep=time.sleep, now=time.time) -> Grant:
    """Wait for the user to approve the code, then return the grant.

    Blocks until xAI answers, the code expires, or the user denies it.
    """
    interval = max(device.interval, 1)
    deadline = now() + device.expires_in

    while now() < deadline:
        sleep(interval)
        try:
            payload = _post_form(
                TOKEN_URL,
                {
                    "client_id": CLIENT_ID,
                    "device_code": device.device_code,
                    "grant_type": DEVICE_CODE_GRANT,
                },
            )
        except _OAuthError as exc:
            if exc.code == "authorization_pending":
                continue
            if exc.code == "slow_down":
                interval += 5
                continue
            if exc.code == "access_denied":
                raise AuthError(
                    "You denied the request. Run 'kadmon login grok' to try again."
                ) from exc
            if exc.code == "expired_token":
                raise AuthError(
                    "The code expired. Run 'kadmon login grok' to get a new one."
                ) from exc
            raise AuthError(f"xAI refused the sign-in: {exc}.") from exc
        return _grant_from_payload(payload)

    raise AuthError("The code expired. Run 'kadmon login grok' to get a new one.")


def refresh_grant(grant: Grant) -> Grant:
    """Trade the refresh token for a new access token, and store it.

    A failure here means the grant is dead, not that the pool is spent. The
    stored grant is cleared so nothing later reads it as live.
    """
    if not grant.refresh_token:
        clear_grant()
        raise AuthError("Your xAI Grok session ended. Run 'kadmon login grok' to sign in again.")

    try:
        payload = _post_form(
            TOKEN_URL,
            {
                "client_id": CLIENT_ID,
                "refresh_token": grant.refresh_token,
                "grant_type": "refresh_token",
            },
        )
    except _OAuthError as exc:
        # xAI rejected the refresh token. The grant is dead, so drop it.
        # A network failure is not a dead grant and propagates untouched.
        clear_grant()
        raise AuthError(
            "Your xAI Grok session ended. Run 'kadmon login grok' to sign in again."
        ) from exc

    fresh = _grant_from_payload(payload)
    if not fresh.refresh_token:
        fresh.refresh_token = grant.refresh_token
    if not fresh.account:
        fresh.account = grant.account
    save_grant(fresh)
    return fresh


def live_grant() -> Grant | None:
    """Return a grant good to use right now, or None when not signed in.

    Refreshes an access token that expires within `REFRESH_WINDOW` seconds. A
    refresh failure raises `AuthError` after clearing the dead grant.
    """
    grant = load_grant()
    if grant is None:
        return None
    if grant.expires_within(REFRESH_WINDOW):
        return refresh_grant(grant)
    return grant


def _grant_from_payload(payload: dict) -> Grant:
    access_token = payload.get("access_token", "")
    if not access_token:
        raise AuthError("xAI returned no access token. Run 'kadmon login grok' again.")

    expires_in = int(payload.get("expires_in", 0) or 0)
    return Grant(
        access_token=access_token,
        refresh_token=payload.get("refresh_token", ""),
        expires_at=int(time.time()) + expires_in if expires_in else 0,
        account=_account_from_payload(payload),
    )


def _account_from_payload(payload: dict) -> str:
    """Name the signed-in account, for `login` to print back.

    The id token carries the email. It is read for display only and never
    trusted for a decision, so the signature is not checked. Empty is fine.
    """
    id_token = payload.get("id_token", "")
    if not isinstance(id_token, str) or id_token.count(".") != 2:
        return ""
    body = id_token.split(".")[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(claims, dict):
        return ""
    return str(claims.get("email") or claims.get("sub") or "")


# --- HTTP ---


class _OAuthError(Exception):
    """An OAuth error response. `code` is the `error` field."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(description or code)
        self.code = code


def _post_form(url: str, fields: dict[str, str], timeout: float = 30.0) -> dict:
    """POST a form and return the JSON body. Raises `_OAuthError` on an error body."""
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, headers=_FORM_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        payload = _decode(exc.read())
        raise _OAuthError(
            str(payload.get("error", f"http_{exc.code}")),
            str(payload.get("error_description", "")),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AuthError(f"Cannot reach {url}: {exc}.") from exc
    except json.JSONDecodeError as exc:
        raise AuthError(f"{url} returned a body that is not JSON.") from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise _OAuthError(str(payload["error"]), str(payload.get("error_description", "")))
    return payload


def _decode(raw: bytes) -> dict:
    try:
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
