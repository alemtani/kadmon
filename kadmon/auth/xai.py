"""Device-code sign-in for xAI Grok.

Kadmon signs in with the public Grok CLI client. Usage then draws from the
SuperGrok pool instead of a pay-per-token console key.

The endpoints below come from xAI's OIDC discovery document at
`https://auth.x.ai/.well-known/openid-configuration`. See
`docs/subscription-auth.md` for the spike that pinned them.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable

from kadmon.auth.oauth import DeviceCode, OAuthError, is_dead_grant, post_form
from kadmon.auth.store import AuthError, Grant, clear, load, save
from kadmon.auth.vendor import LoginPrompt, Vendor

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

VENDOR = "grok"

_OAuthError = OAuthError


def load_grant() -> Grant | None:
    """Read the stored Grok grant. Returns None when there is none."""
    return load(VENDOR)


def save_grant(grant: Grant) -> None:
    """Store the Grok grant, readable only by this user."""
    save(VENDOR, grant)


def clear_grant() -> None:
    """Drop the Grok grant. Leaves any other vendor's entry alone."""
    clear(VENDOR)


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


def poll_for_grant(
    device: DeviceCode,
    sleep: Callable[[float], None] | None = None,
    now: Callable[[], float] | None = None,
) -> Grant:
    """Wait for the user to approve the code, then return the grant.

    Blocks until xAI answers, the code expires, or the user denies it.
    """
    pause = time.sleep if sleep is None else sleep
    clock = time.time if now is None else now
    interval = max(device.interval, 1)
    deadline = clock() + device.expires_in

    while clock() < deadline:
        pause(interval)
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
            interval += _poll_wait(exc)
            continue
        return _grant_from_payload(payload)

    raise AuthError("The code expired. Run 'kadmon login grok' to get a new one.")


def _poll_wait(exc: OAuthError) -> int:
    """Seconds to add to the poll interval. Raises AuthError when polling must stop."""
    if exc.code == "authorization_pending":
        return 0
    if exc.code == "slow_down":
        return 5
    if exc.code == "access_denied":
        raise AuthError("You denied the request. Run 'kadmon login grok' to try again.") from exc
    if exc.code == "expired_token":
        raise AuthError("The code expired. Run 'kadmon login grok' to get a new one.") from exc
    raise AuthError(f"xAI refused the sign-in: {exc}.") from exc


def refresh_grant(grant: Grant) -> Grant:
    """Trade the refresh token for a new access token, and store it.

    Only a rejected refresh token is a dead grant. A 5xx or 429 leaves the
    stored session alone so a blip does not push the user onto a paid key.
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
        if not is_dead_grant(exc.code):
            raise AuthError(f"Cannot refresh the xAI Grok session: {exc}.") from exc
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
    """Return a grant good to use right now, or None when not signed in."""
    return GrokVendor().live_grant()


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


def _post_form(url: str, fields: dict[str, str], timeout: float = 30.0) -> dict:
    """Hook for tests. Production calls `post_form`."""
    return post_form(url, fields, timeout=timeout)


class GrokVendor(Vendor):
    """xAI Grok device-code sign-in. The only vendor with a verified live path."""

    name = VENDOR
    display_name = "xAI Grok"
    tested = True
    success_hint = "Runs now draw from your SuperGrok pool, not a console API key."
    run_notice = "Running on your SuperGrok subscription pool."
    key_env = "XAI_API_KEY"
    available_detail = "runs on your SuperGrok pool"

    def login(self, show: Callable[[LoginPrompt], None]) -> Grant:
        device = request_device_code()
        show(LoginPrompt(url=device.url, user_code=device.user_code))
        return poll_for_grant(device)

    def refresh_grant(self, grant: Grant) -> Grant:
        return refresh_grant(grant)

    def pool_spent_message(self, status_code: int) -> str | None:
        if status_code != 402:
            return None
        from kadmon.providers.grok import POOL_SPENT

        return POOL_SPENT
