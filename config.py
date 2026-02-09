import os
from dotenv import load_dotenv

load_dotenv()

# Walmart API credentials
WALMART_CLIENT_ID = os.getenv("WALMART_CLIENT_ID", "")
WALMART_CLIENT_SECRET = os.getenv("WALMART_CLIENT_SECRET", "")
WALMART_PRIVATE_KEY_PATH = os.getenv("WALMART_PRIVATE_KEY_PATH", "private_key.pem")
WALMART_KEY_VERSION = os.getenv("WALMART_KEY_VERSION", "1")
WALMART_ADVERTISER_ID = os.getenv("WALMART_ADVERTISER_ID", "")

# API endpoints
TOKEN_URL = "https://api-gateway.walmart.com/v3/token"
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
