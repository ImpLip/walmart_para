# Usage Guide

How to set up and use the Walmart Ads Report Snapshot Fetcher.

## Prerequisites

- Python 3.8+
- A Walmart Advertising API account with valid credentials

## Setup

### 1. Create and activate the virtual environment

```bash
cd /home/shajiazzpy/walmart_para
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
WALMART_ACCESS_TOKEN=your_bearer_token_here
WALMART_CONSUMER_ID=your_consumer_id_here
WALMART_AUTH_SIGNATURE=your_auth_signature_here
WALMART_KEY_VERSION=1
WALMART_ADVERTISER_ID=your_default_advertiser_id
```

| Variable                  | Required | Description                                |
|---------------------------|----------|--------------------------------------------|
| `WALMART_ACCESS_TOKEN`    | Yes      | Bearer token for API authorization         |
| `WALMART_CONSUMER_ID`     | Yes      | Your Walmart consumer ID                   |
| `WALMART_AUTH_SIGNATURE`  | Yes      | Authentication signature                   |
| `WALMART_KEY_VERSION`     | No       | Signature key version (defaults to `1`)    |
| `WALMART_ADVERTISER_ID`   | No       | Default advertiser ID (overridable via CLI)|

## Running Reports

### Basic syntax

```bash
python report_fetcher.py --report-type <TYPE> --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD>
```

### Show help

```bash
python report_fetcher.py --help
```

### Available report types

| Type        | Description          | Max Date Range |
|-------------|----------------------|----------------|
| `campaign`  | Campaign-level data  | 60 days        |
| `lineItem`  | Line item metrics    | 60 days        |
| `tactic`    | Tactic performance   | 60 days        |
| `sku`       | SKU-level data       | 15 days        |
| `creative`  | Creative performance | 60 days        |
| `bid`       | Bid analytics        | 60 days        |
| `newBuyer`  | New buyer metrics    | 60 days        |

## Examples

### Fetch a campaign report

```bash
python report_fetcher.py \
  --report-type campaign \
  --start-date 2026-01-01 \
  --end-date 2026-01-15
```

### Fetch a SKU report (note: 15-day max range)

```bash
python report_fetcher.py \
  --report-type sku \
  --start-date 2026-01-01 \
  --end-date 2026-01-10
```

### Fetch with a specific advertiser ID

```bash
python report_fetcher.py \
  --report-type lineItem \
  --start-date 2026-01-01 \
  --end-date 2026-01-31 \
  --advertiser-id 600001
```

### Fetch a new buyer report

```bash
python report_fetcher.py \
  --report-type newBuyer \
  --start-date 2026-01-01 \
  --end-date 2026-02-01
```

## Output

### File location

All reports are saved to the `reports/` directory with descriptive filenames:

```
reports/{report_type}_{start_date}_{end_date}_{advertiser_id}_{timestamp}.csv
```

Example:
```
reports/campaign_2026-01-01_2026-01-15_500001_20260209_143022.csv
```

### Console output

The tool logs each step with timestamps and prints a summary on completion:

```
2026-02-09 14:30:00 [INFO] === Step 1/3: Creating snapshot job ===
2026-02-09 14:30:01 [INFO] Creating snapshot: type=campaign, range=2026-01-01 to 2026-01-15
2026-02-09 14:30:02 [INFO] Snapshot created: snapshotId=abc123
2026-02-09 14:30:02 [INFO] === Step 2/3: Polling for job completion ===
2026-02-09 14:30:02 [INFO] Poll attempt 1/60 — status: pending
2026-02-09 14:30:02 [INFO] Waiting 30s before next poll...
2026-02-09 14:30:32 [INFO] Poll attempt 2/60 — status: done
2026-02-09 14:30:32 [INFO] === Step 3/3: Downloading and decompressing report ===
2026-02-09 14:30:33 [INFO] Downloading report from: https://advertising.walmart.com/display/file/xyz789
2026-02-09 14:30:35 [INFO] Decompressing gzip file...
2026-02-09 14:30:35 [INFO] Report saved to: reports/campaign_2026-01-01_2026-01-15_500001_20260209_143022.csv

==================================================
DOWNLOAD COMPLETE
==================================================
  File:    reports/campaign_2026-01-01_2026-01-15_500001_20260209_143022.csv
  Rows:    1,234
  Columns: 12
  Headers: col1, col2, col3, col4, col5 ... (+7 more)
==================================================
```

## Date Constraints

The Walmart API enforces these date rules:

| Rule                        | Constraint                                |
|-----------------------------|-------------------------------------------|
| Date format                 | `YYYY-MM-DD`                              |
| Start before end            | `start_date` must be before `end_date`    |
| No current/future dates     | `end_date` must be before today           |
| Lookback limit              | `start_date` within the last 2 years      |
| Max range (most types)      | 60 days                                   |
| Max range (`sku` only)      | 15 days                                   |

## Error Handling

### Common errors and solutions

| Error Message                                    | Cause                                    | Solution                                          |
|-------------------------------------------------|------------------------------------------|--------------------------------------------------|
| `WALMART_ACCESS_TOKEN is not set in .env`       | Missing credential                       | Fill in all required values in `.env`             |
| `No advertiser ID provided`                     | No ID via CLI or `.env`                  | Use `--advertiser-id` or set `WALMART_ADVERTISER_ID` in `.env` |
| `Invalid date format`                           | Date not in `YYYY-MM-DD` format          | Use correct format, e.g., `2026-01-15`           |
| `Date range exceeds the N-day limit`            | Range too wide for report type           | Narrow the date range                            |
| `end_date cannot include the current day`       | End date is today or in the future       | Use yesterday or earlier as end date             |
| `start_date cannot be more than 2 years`        | Start date too far back                  | Use a date within the last 2 years               |
| `Snapshot job failed`                           | Server-side job failure                  | Retry; check report type and date range          |
| `Snapshot job expired`                          | Job result expired (24h window)          | Create a new snapshot and download promptly       |
| `Snapshot did not complete after 60 attempts`   | Job took longer than ~30 minutes         | Retry later; the API may be under heavy load      |
| `API error: 401`                                | Invalid or expired credentials           | Refresh your access token                        |
| `API error: 429`                                | Rate limited                             | Wait and retry                                   |

### Interrupt

Press `Ctrl+C` at any time to cancel the operation. The tool exits cleanly with code 130.

## Project Structure

```
walmart_para/
├── .env.example          # Template for required env vars
├── .env                  # Your credentials (git-ignored)
├── requirements.txt      # Python dependencies
├── config.py             # Configuration & constants
├── auth.py               # Authentication header builder
├── snapshot_client.py    # Core API client (create, poll, download)
├── report_fetcher.py     # CLI entry point
├── reports/              # Output directory for downloaded CSVs
├── venv/                 # Python virtual environment
├── IMPLEMENTATION.md     # Technical implementation details
└── USAGE.md              # This file
```
