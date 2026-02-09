import time
from config import (
    WALMART_ACCESS_TOKEN,
    WALMART_CONSUMER_ID,
    WALMART_AUTH_SIGNATURE,
    WALMART_KEY_VERSION,
)


def get_auth_headers():
    """Build the required Walmart API authentication headers."""
    if not WALMART_ACCESS_TOKEN:
        raise ValueError("WALMART_ACCESS_TOKEN is not set in .env")
    if not WALMART_CONSUMER_ID:
        raise ValueError("WALMART_CONSUMER_ID is not set in .env")
    if not WALMART_AUTH_SIGNATURE:
        raise ValueError("WALMART_AUTH_SIGNATURE is not set in .env")

    return {
        "Authorization": f"Bearer {WALMART_ACCESS_TOKEN}",
        "WM_CONSUMER.ID": WALMART_CONSUMER_ID,
        "WM_SEC.AUTH_SIGNATURE": WALMART_AUTH_SIGNATURE,
        "WM_CONSUMER.intimestamp": str(int(time.time() * 1000)),
        "WM_SEC.KEY_VERSION": WALMART_KEY_VERSION,
        "Content-Type": "application/json",
    }
