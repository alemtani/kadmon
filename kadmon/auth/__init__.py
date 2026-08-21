"""Subscription sign-in. One module per vendor, one table per vendor in the store.

Add a vendor: subclass `Vendor`, set `tested` until the live path is verified,
and call `register` below. `kadmon login <name>` then dispatches.
"""

from kadmon.auth.store import TOKENS_PATH, AuthError, Grant, clear, load, save
from kadmon.auth.vendor import (
    LoginPrompt,
    Vendor,
    get_vendor,
    live,
    register,
    unregister,
    vendor_names,
)
from kadmon.auth.xai import GrokVendor

register(GrokVendor())

__all__ = [
    "TOKENS_PATH",
    "AuthError",
    "Grant",
    "LoginPrompt",
    "Vendor",
    "clear",
    "get_vendor",
    "live",
    "load",
    "register",
    "save",
    "unregister",
    "vendor_names",
]
