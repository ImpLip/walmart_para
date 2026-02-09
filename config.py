import os
from dotenv import load_dotenv

load_dotenv()

# Walmart API credentials
WALMART_ACCESS_TOKEN = os.getenv("WALMART_ACCESS_TOKEN", "")
WALMART_CONSUMER_ID = os.getenv("WALMART_CONSUMER_ID", "")
WALMART_AUTH_SIGNATURE = os.getenv("WALMART_AUTH_SIGNATURE", "")
WALMART_KEY_VERSION = os.getenv("WALMART_KEY_VERSION", "1")
WALMART_ADVERTISER_ID = os.getenv("WALMART_ADVERTISER_ID", "")

# API endpoints
BASE_URL = "https://developer.api.us.walmart.com/api-proxy/service/display/api/v1/api/v1"
DOWNLOAD_URL = "https://advertising.walmart.com/display/file"

# Valid report types
VALID_REPORT_TYPES = [
    "campaign",
    "lineItem",
    "tactic",
    "sku",
    "creative",
    "bid",
    "newBuyer",
]

# Date range limits (days)
MAX_DATE_RANGE = 60
SKU_MAX_RANGE = 15

# Polling configuration
POLL_INTERVAL = 30        # seconds between status checks
MAX_POLL_ATTEMPTS = 60    # ~30 min timeout

# Snapshot expiry
SNAPSHOT_EXPIRY_HOURS = 24
