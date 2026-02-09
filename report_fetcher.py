#!/usr/bin/env python3
"""Walmart Advertising Report Snapshot Fetcher.

Automates the full workflow: create job → poll status → download gzip → decompress → save CSV.

Usage:
    python report_fetcher.py --report-type campaign --start-date 2026-01-01 --end-date 2026-01-15
    python report_fetcher.py --report-type sku --start-date 2026-01-01 --end-date 2026-01-10 --advertiser-id 600001
"""

import argparse
import csv
import logging
import os
import sys
from datetime import datetime

from config import WALMART_ADVERTISER_ID, VALID_REPORT_TYPES
from snapshot_client import create_snapshot, poll_snapshot, download_report

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def setup_logging():
    """Configure logging with timestamps."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch Walmart Advertising Report Snapshots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python report_fetcher.py --report-type campaign --start-date 2026-01-01 --end-date 2026-01-15\n"
            "  python report_fetcher.py --report-type sku --start-date 2026-01-01 --end-date 2026-01-10 --advertiser-id 600001\n"
        ),
    )
    parser.add_argument(
        "--report-type",
        required=True,
        choices=VALID_REPORT_TYPES,
        help="Type of report to fetch",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--advertiser-id",
        default=None,
        help="Advertiser ID (defaults to WALMART_ADVERTISER_ID from .env)",
    )
    return parser.parse_args()


def validate_date_format(date_str):
    """Validate that a string is a proper YYYY-MM-DD date."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.")


def build_output_filename(report_type, start_date, end_date, advertiser_id):
    """Build a descriptive output filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{report_type}_{start_date}_{end_date}_{advertiser_id}_{timestamp}.csv"


def print_summary(output_path):
    """Print a summary of the downloaded CSV file."""
    try:
        with open(output_path, "r", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            row_count = sum(1 for _ in reader)

        col_count = len(headers) if headers else 0
        print("\n" + "=" * 50)
        print("DOWNLOAD COMPLETE")
        print("=" * 50)
        print(f"  File:    {output_path}")
        print(f"  Rows:    {row_count:,}")
        print(f"  Columns: {col_count}")
        if headers:
            print(f"  Headers: {', '.join(headers[:5])}", end="")
            if col_count > 5:
                print(f" ... (+{col_count - 5} more)")
            else:
                print()
        print("=" * 50)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not read CSV summary: %s", e)
        print(f"\nReport saved to: {output_path}")


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    args = parse_args()

    # Resolve advertiser ID
    advertiser_id = args.advertiser_id or WALMART_ADVERTISER_ID
    if not advertiser_id:
        logger.error("No advertiser ID provided. Use --advertiser-id or set WALMART_ADVERTISER_ID in .env")
        sys.exit(1)

    # Validate date formats
    try:
        validate_date_format(args.start_date)
        validate_date_format(args.end_date)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Ensure reports directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Build output path
    filename = build_output_filename(args.report_type, args.start_date, args.end_date, advertiser_id)
    output_path = os.path.join(REPORTS_DIR, filename)

    try:
        # Step 1: Create snapshot
        logger.info("=== Step 1/3: Creating snapshot job ===")
        snapshot_id = create_snapshot(
            advertiser_id=advertiser_id,
            report_type=args.report_type,
            start_date=args.start_date,
            end_date=args.end_date,
        )

        # Step 2: Poll for completion
        logger.info("=== Step 2/3: Polling for job completion ===")
        result = poll_snapshot(advertiser_id=advertiser_id, snapshot_id=snapshot_id)
        file_url = result["details"]

        # Step 3: Download and decompress
        logger.info("=== Step 3/3: Downloading and decompressing report ===")
        download_report(
            file_url=file_url,
            advertiser_id=advertiser_id,
            output_path=output_path,
        )

        # Summary
        print_summary(output_path)

    except ValueError as e:
        logger.error("Validation error: %s", e)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        logger.error("API error: %s", e)
        if e.response is not None:
            logger.error("Response body: %s", e.response.text)
        sys.exit(1)
    except TimeoutError as e:
        logger.error("Timeout: %s", e)
        sys.exit(1)
    except RuntimeError as e:
        logger.error("Runtime error: %s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
