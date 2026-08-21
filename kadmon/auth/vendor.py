"""Vendor registry. `kadmon login <name>` dispatches through this.

To add a vendor:

1. Subclass `Vendor` in `kadmon/auth/<name>.py`.
2. Set `tested = False` until the live endpoints are verified. Login then
   prints one experimental-path line.
3. Call `register(YourVendor())` from `kadmon/auth/__init__.py`.

Do not copy `xai.py` and swap URLs unless the vendor is the same kind of
device-code flow. Claude is a local CLI, not this class of flow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from kadmon.auth.store import AuthError, Grant, clear, load, save

REFRESH_WINDOW = 60


@dataclass(frozen=True)
class LoginPrompt:
    """What the CLI shows while sign-in waits on the user.

    Device-code vendors set `url` and `user_code`. CLI-detect vendors set
    `message` only. An empty prompt means there is nothing to show.
    """

    url: str = ""
    user_code: str = ""
    message: str = ""


class Vendor(ABC):
    """One subscription vendor.

    `name` is the tokens.toml table and the `kadmon login` argument.
    `display_name` is what the CLI prints. `success_hint` is an extra line
    after a successful login; empty is fine.
    """

    name: str
    display_name: str
    tested: bool = False
    success_hint: str = ""
    # Printed when a live grant drives a run. Empty means no extra line.
    run_notice: str = ""
    # Env var a live grant ignores. Empty means none.
    key_env: str = ""
    # Extra words after "signed in as …" in `kadmon init`. Empty is fine.
    available_detail: str = ""

    def load_grant(self) -> Grant | None:
        return load(self.name)

    def save_grant(self, grant: Grant) -> None:
        save(self.name, grant)

    def clear_grant(self) -> None:
        clear(self.name)

    @abstractmethod
    def login(self, show: Callable[[LoginPrompt], None]) -> Grant:
        """Run sign-in. Call `show` once if the user must act."""

    def refresh_grant(self, grant: Grant) -> Grant:
        """Trade a refresh token for a new access token. Override for OAuth."""
        raise AuthError(
            f"{self.display_name} cannot refresh this session. "
            f"Run 'kadmon login {self.name}' to sign in again."
        )

    def live_grant(self) -> Grant | None:
        """Return a grant good to use right now, or None when not signed in."""
        grant = self.load_grant()
        if grant is None:
            return None
        if grant.expires_within(REFRESH_WINDOW):
            return self.refresh_grant(grant)
        return grant

    def pool_spent_message(self, status_code: int) -> str | None:
        """Stop-message when `status_code` means the pool is spent, else None.

        SuperGrok uses 402. Other vendors leave this as None until they
        declare their own signal. Do not guess.
        """
        return None

    def session_ended_message(self) -> str:
        return (
            f"Your {self.display_name} session ended. "
            f"Run 'kadmon login {self.name}' to sign in again."
        )


_VENDORS: dict[str, Vendor] = {}


def register(vendor: Vendor) -> None:
    """Make `vendor` available to `kadmon login` / `logout`."""
    _VENDORS[vendor.name] = vendor


def unregister(name: str) -> None:
    """Drop a vendor. Tests use this to restore the registry."""
    _VENDORS.pop(name, None)


def find_vendor(name: str) -> Vendor | None:
    """Return the registered vendor, or None when `name` is not one."""
    return _VENDORS.get(name)


def get_vendor(name: str) -> Vendor:
    """Return the registered vendor, or raise `AuthError`."""
    vendor = find_vendor(name)
    if vendor is None:
        names = ", ".join(vendor_names()) or "(none registered)"
        raise AuthError(f"Unknown vendor {name!r}. Choose one of: {names}.")
    return vendor


def vendor_names() -> list[str]:
    return sorted(_VENDORS)


def live(name: str) -> Grant | None:
    """Return a live grant for `name`, refreshing if needed."""
    return get_vendor(name).live_grant()
