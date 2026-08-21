"""Shared OAuth HTTP. Vendors that are not form-POST OAuth do not import this."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from kadmon.auth.store import AuthError

# RFC 6749: the authorization server rejected this grant. HTTP blips are not
# this — `http_503` and `http_429` must not sign the user out.
DEAD_GRANT_CODES = frozenset({"invalid_grant", "invalid_token", "revoked"})

_FORM_HEADERS = {
    "content-type": "application/x-www-form-urlencoded",
    "accept": "application/json",
}


class OAuthError(Exception):
    """An OAuth error response. `code` is the `error` field."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(description or code)
        self.code = code


@dataclass
class DeviceCode:
    """What an RFC 8628 device-code endpoint hands back so the user can approve."""

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


def is_dead_grant(code: str) -> bool:
    """True when the token endpoint has rejected this refresh token."""
    return code in DEAD_GRANT_CODES


def post_form(url: str, fields: dict[str, str], timeout: float = 30.0) -> dict:
    """POST a form and return the JSON body. Raises `OAuthError` on an error body."""
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, headers=_FORM_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        payload = _decode(exc.read())
        raise OAuthError(
            str(payload.get("error", f"http_{exc.code}")),
            str(payload.get("error_description", "")),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AuthError(f"Cannot reach {url}: {exc}.") from exc
    except json.JSONDecodeError as exc:
        raise AuthError(f"{url} returned a body that is not JSON.") from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise OAuthError(str(payload["error"]), str(payload.get("error_description", "")))
    return payload


def _decode(raw: bytes) -> dict:
    try:
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
