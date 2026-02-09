import gzip
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

import requests

from auth import get_auth_headers
from config import (
    BASE_URL,
    DOWNLOAD_URL,
    MAX_DATE_RANGE,
    SKU_MAX_RANGE,
    POLL_INTERVAL,
    MAX_POLL_ATTEMPTS,
    VALID_REPORT_TYPES,
)

logger = logging.getLogger(__name__)


def _validate_dates(report_type, start_date, end_date):
    """Validate date range constraints for the given report type."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if start > end:
        raise ValueError(f"start_date ({start_date}) must be before end_date ({end_date})")

    if end >= today:
        raise ValueError(f"end_date ({end_date}) cannot include the current day or future dates")

    two_years_ago = today - timedelta(days=730)
    if start < two_years_ago:
        raise ValueError(f"start_date ({start_date}) cannot be more than 2 years in the past")

    delta_days = (end - start).days
    max_range = SKU_MAX_RANGE if report_type == "sku" else MAX_DATE_RANGE

    if delta_days > max_range:
        raise ValueError(
            f"Date range ({delta_days} days) exceeds the {max_range}-day limit "
            f"for '{report_type}' reports"
        )


def create_snapshot(advertiser_id, report_type, start_date, end_date):
    """Create a snapshot report job.

    Returns the snapshotId from the API response.
    """
    if report_type not in VALID_REPORT_TYPES:
        raise ValueError(
            f"Invalid report type '{report_type}'. "
            f"Must be one of: {', '.join(VALID_REPORT_TYPES)}"
        )

    _validate_dates(report_type, start_date, end_date)

    url = f"{BASE_URL}/snapshot/report"
    payload = {
        "advertiserId": advertiser_id,
        "reportType": report_type,
        "startDate": start_date,
        "endDate": end_date,
    }

    logger.info("Creating snapshot: type=%s, range=%s to %s", report_type, start_date, end_date)
    headers = get_auth_headers()
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    snapshot_id = data.get("snapshotId")
    if not snapshot_id:
        raise RuntimeError(f"No snapshotId in response: {data}")

    logger.info("Snapshot created: snapshotId=%s", snapshot_id)
    return snapshot_id


def poll_snapshot(advertiser_id, snapshot_id):
    """Poll snapshot status until it reaches a terminal state.

    Returns the full response dict when jobStatus is 'done'.
    Raises on 'failed', 'expired', or timeout.
    """
    url = f"{BASE_URL}/snapshot"
    params = {
        "advertiserId": advertiser_id,
        "snapshotId": snapshot_id,
    }

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        headers = get_auth_headers()
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        status = data.get("jobStatus", "unknown")
        logger.info("Poll attempt %d/%d — status: %s", attempt, MAX_POLL_ATTEMPTS, status)

        if status == "done":
            details_url = data.get("details")
            if not details_url:
                raise RuntimeError(f"Status is 'done' but no 'details' URL in response: {data}")
            return data

        if status == "failed":
            raise RuntimeError(f"Snapshot job failed: {data}")

        if status == "expired":
            raise RuntimeError(f"Snapshot job expired: {data}")

        if status not in ("pending", "processing"):
            logger.warning("Unexpected status: %s", status)

        if attempt < MAX_POLL_ATTEMPTS:
            logger.info("Waiting %ds before next poll...", POLL_INTERVAL)
            time.sleep(POLL_INTERVAL)

    raise TimeoutError(
        f"Snapshot did not complete after {MAX_POLL_ATTEMPTS} attempts "
        f"(~{MAX_POLL_ATTEMPTS * POLL_INTERVAL // 60} minutes)"
    )


def download_report(file_url, advertiser_id, output_path):
    """Download a gzip report file, decompress it, and save as CSV.

    Args:
        file_url: The 'details' URL from the poll response.
        advertiser_id: The advertiser ID for the download request.
        output_path: Local file path to save the decompressed CSV.

    Returns:
        The output file path.
    """
    parsed = urlparse(file_url)
    # Extract the file ID from the path (last segment)
    path_parts = parsed.path.rstrip("/").split("/")
    file_id = path_parts[-1] if path_parts else ""

    if not file_id:
        raise ValueError(f"Could not extract file ID from URL: {file_url}")

    download_url = f"{DOWNLOAD_URL}/{file_id}"
    params = {"advertiserId": advertiser_id}

    logger.info("Downloading report from: %s", download_url)
    headers = get_auth_headers()
    # Remove Content-Type for download request
    headers.pop("Content-Type", None)

    resp = requests.get(download_url, params=params, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    # Write the raw gzip response to a temp file, then decompress
    gz_path = output_path + ".gz"
    with open(gz_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    logger.info("Decompressing gzip file...")
    with gzip.open(gz_path, "rb") as gz_file:
        with open(output_path, "wb") as csv_file:
            while True:
                chunk = gz_file.read(8192)
                if not chunk:
                    break
                csv_file.write(chunk)

    # Clean up the .gz file
    import os
    os.remove(gz_path)

    logger.info("Report saved to: %s", output_path)
    return output_path
