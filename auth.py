import base64
import logging
import time
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import (
    WALMART_CLIENT_ID,
    WALMART_CLIENT_SECRET,
    WALMART_PRIVATE_KEY_PATH,
    WALMART_KEY_VERSION,
    TOKEN_URL,
)

logger = logging.getLogger(__name__)

# Cached token state
_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


def _validate_credentials():
    """Ensure required credentials are configured."""
    if not WALMART_CLIENT_ID:
        raise ValueError("WALMART_CLIENT_ID is not set in .env")
    if not WALMART_CLIENT_SECRET:
        raise ValueError("WALMART_CLIENT_SECRET is not set in .env")
    if not WALMART_PRIVATE_KEY_PATH:
        raise ValueError("WALMART_PRIVATE_KEY_PATH is not set in .env")


def _get_access_token():
    """Fetch an OAuth access token, using cache if still valid.

    POST https://api-gateway.walmart.com/v3/token
    with Basic auth (base64 of clientId:clientSecret).
    """
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    _validate_credentials()

    credentials = base64.b64encode(
        f"{WALMART_CLIENT_ID}:{WALMART_CLIENT_SECRET}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    logger.info("Requesting new OAuth access token...")
    resp = requests.post(
        TOKEN_URL,
        headers=headers,
        data="grant_type=client_credentials",
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)

    # Cache with 60s buffer before actual expiry
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = now + expires_in - 60

    logger.info("OAuth token obtained, expires in %ds", expires_in)
    return access_token


def _load_private_key():
    """Load the RSA private key from the PEM file."""
    with open(WALMART_PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _generate_signature(method, url, timestamp):
    """Generate RSA SHA256 signature for the request.

    The string to sign is:
        ConsumerID\nTimestamp\nHTTP_METHOD\nREQUEST_PATH\n
    """
    request_path = urlparse(url).path

    string_to_sign = (
        f"{WALMART_CLIENT_ID}\n"
        f"{timestamp}\n"
        f"{method.upper()}\n"
        f"{request_path}\n"
    )

    private_key = _load_private_key()
    signature_bytes = private_key.sign(
        string_to_sign.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    return base64.b64encode(signature_bytes).decode()


def get_auth_headers(method, url):
    """Build the required Walmart API authentication headers.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full request URL (path is extracted for signing)
    """
    _validate_credentials()

    access_token = _get_access_token()
    timestamp = str(int(time.time() * 1000))
    signature = _generate_signature(method, url, timestamp)

    return {
        "Authorization": f"Bearer {access_token}",
        "WM_CONSUMER.ID": WALMART_CLIENT_ID,
        "WM_SEC.AUTH_SIGNATURE": signature,
        "WM_CONSUMER.intimestamp": timestamp,
        "WM_SEC.KEY_VERSION": WALMART_KEY_VERSION,
        "Content-Type": "application/json",
    }
