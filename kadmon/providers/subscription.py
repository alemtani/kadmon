"""Grant-backed OpenAI-compatible calls.

One refresh, one retry, then stop. Pool exhaustion is whatever the vendor
declares — do not assume 402 here.
"""

from __future__ import annotations

import openai

from kadmon.auth.store import AuthError, Grant
from kadmon.auth.vendor import Vendor


class PoolExhausted(Exception):
    """The subscription pool, credit, or spending cap is spent.

    This is not a dead session. It means wait, not sign in again. Never fall
    back to an API key on it.
    """


class GrantClient:
    """401 refreshes once; vendor pool-spent stops the run.

    `OpenAIProvider` inherits this. `_call_with_retry` wraps
    `_create_with_backoff` twice and then stops — it never calls itself.
    """

    vendor: Vendor | None = None
    grant: Grant | None = None

    def _call_with_retry(self, kwargs: dict):
        vendor = self.vendor
        if self.grant is None or vendor is None:
            return self._create_with_backoff(kwargs)
        try:
            return self._create_with_backoff(kwargs)
        except openai.AuthenticationError:
            self._refresh_grant()
            try:
                return self._create_with_backoff(kwargs)
            except openai.AuthenticationError as exc:
                raise AuthError(vendor.session_ended_message()) from exc
        except openai.APIStatusError as exc:
            message = vendor.pool_spent_message(exc.status_code)
            if message:
                raise PoolExhausted(message) from exc
            raise

    def _refresh_grant(self) -> None:
        vendor, grant = self.vendor, self.grant
        if vendor is None or grant is None:
            return
        self.grant = vendor.refresh_grant(grant)
        self.client.api_key = self.grant.access_token
