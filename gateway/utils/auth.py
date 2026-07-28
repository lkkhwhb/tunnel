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


# In-memory store for dummy/temporary API keys created by the admin
DUMMY_API_KEYS: set[str] = set()


def add_dummy_api_key(key: str) -> None:
    """Add a temporary dummy API key to in-memory storage."""
    if key and key.strip():
        DUMMY_API_KEYS.add(key.strip())


def remove_dummy_api_key(key: str) -> bool:
    """Remove a temporary dummy API key from in-memory storage."""
    if key in DUMMY_API_KEYS:
        DUMMY_API_KEYS.remove(key)
        return True
    return False


def list_dummy_api_keys() -> list[str]:
    """Return a sorted list of all active dummy API keys."""
    return sorted(list(DUMMY_API_KEYS))


def clear_dummy_api_keys() -> None:
    """Clear all dummy API keys from memory."""
    DUMMY_API_KEYS.clear()


def verify_api_key(api_key: str | None) -> None:
    """
    Verify an API key against the configured TUNNEL_API_KEY or any active dummy keys.

    Args:
        api_key: The raw API key string from the client request.

    Raises:
        AuthError: If the API key is missing or invalid.
    """
    if not api_key:
        raise AuthError("Invalid API key")
    if hmac.compare_digest(api_key, TUNNEL_API_KEY):
        return
    for dummy_key in DUMMY_API_KEYS:
        if hmac.compare_digest(api_key, dummy_key):
            return
    raise AuthError("Invalid API key")
