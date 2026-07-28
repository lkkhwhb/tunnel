"""
API Key authentication utilities.

Handles API key verification for tunnel registration.
Raises ``AuthError`` with separate client-facing and log-friendly messages
to preserve the original error reporting behaviour.
"""

import hmac

from gateway.config.settings import TUNNEL_API_KEY


class AuthError(Exception):
    """Raised when authentication fails.

    Attributes:
        client_message: Safe message to send back to the tunnel client.
        log_detail:     More detailed message for server-side logging.
    """

    def __init__(self, client_message: str, log_detail: str | None = None):
        self.client_message = client_message
        self.log_detail = log_detail or client_message
        super().__init__(client_message)


def verify_api_key(api_key: str | None) -> None:
    """
    Verify an API key against the configured TUNNEL_API_KEY.

    Args:
        api_key: The raw API key string from the client request.

    Raises:
        AuthError: If the API key is missing or invalid.
    """
    if not api_key or not hmac.compare_digest(api_key, TUNNEL_API_KEY):
        raise AuthError("Invalid API key")
