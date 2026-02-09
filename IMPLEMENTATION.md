# Implementation Guide

Technical documentation for the Walmart Ads Report Snapshot Fetcher.

## Architecture

The project follows a layered design with clear separation of concerns:

```
report_fetcher.py   (CLI orchestrator)
       |
snapshot_client.py  (API client - create, poll, download)
       |
   auth.py          (authentication header builder)
       |
  config.py         (environment variables & constants)
```

## File Breakdown

### `config.py`

Loads credentials from a `.env` file using `python-dotenv` and exposes them as module-level constants.

| Constant               | Purpose                                     | Default |
|------------------------|---------------------------------------------|---------|
| `WALMART_ACCESS_TOKEN` | Bearer token for API authorization           | `""`    |
| `WALMART_CONSUMER_ID`  | Consumer identity header                     | `""`    |
| `WALMART_AUTH_SIGNATURE`| Cryptographic signature for request signing | `""`    |
| `WALMART_KEY_VERSION`  | Signature key version                        | `"1"`   |
| `WALMART_ADVERTISER_ID`| Default advertiser (overridable via CLI)     | `""`    |

**API Endpoints:**

| Constant       | URL                                                                                     |
|---------------|-----------------------------------------------------------------------------------------|
| `BASE_URL`    | `https://developer.api.us.walmart.com/api-proxy/service/display/api/v1/api/v1`          |
| `DOWNLOAD_URL`| `https://advertising.walmart.com/display/file`                                          |

**Operational Constants:**

| Constant              | Value | Description                              |
|-----------------------|-------|------------------------------------------|
| `MAX_DATE_RANGE`      | 60    | Max days for most report types           |
| `SKU_MAX_RANGE`       | 15    | Max days specifically for `sku` reports  |
| `POLL_INTERVAL`       | 30    | Seconds between polling attempts         |
| `MAX_POLL_ATTEMPTS`   | 60    | Max polls before timeout (~30 minutes)   |
| `SNAPSHOT_EXPIRY_HOURS`| 24   | Hours before a snapshot download expires  |

---

### `auth.py`

**Function:** `get_auth_headers() -> dict`

Builds the 6 required HTTP headers for every Walmart API call:

```python
{
    "Authorization": "Bearer <TOKEN>",
    "WM_CONSUMER.ID": "<CONSUMER_ID>",
    "WM_SEC.AUTH_SIGNATURE": "<SIGNATURE>",
    "WM_CONSUMER.intimestamp": "<epoch_milliseconds>",
    "WM_SEC.KEY_VERSION": "<VERSION>",
    "Content-Type": "application/json",
}
```

- The `intimestamp` is generated fresh on each call using `time.time() * 1000` (epoch milliseconds).
- Raises `ValueError` if any of the three critical credentials (`TOKEN`, `CONSUMER_ID`, `AUTH_SIGNATURE`) are missing.

---

### `snapshot_client.py`

The core API client. Contains three public functions and one private validator.

#### `_validate_dates(report_type, start_date, end_date)`

Private function that enforces Walmart's date constraints:

1. **Order check** -- `start_date` must be before `end_date`.
2. **No current/future dates** -- `end_date` must be strictly before today.
3. **2-year lookback limit** -- `start_date` cannot be more than 730 days in the past.
4. **Range limit** -- Date span cannot exceed 60 days (or 15 days for `sku` reports).

All dates use `YYYY-MM-DD` format and are parsed via `datetime.strptime`.

#### `create_snapshot(advertiser_id, report_type, start_date, end_date) -> str`

Creates a snapshot report job.

- **Endpoint:** `POST {BASE_URL}/snapshot/report`
- **Request body:**
  ```json
  {
      "advertiserId": "...",
      "reportType": "campaign",
      "startDate": "2026-01-01",
      "endDate": "2026-01-15"
  }
  ```
- **Flow:**
  1. Validates `report_type` against the 7 allowed types.
  2. Validates date constraints via `_validate_dates()`.
  3. Sends POST request with JSON payload and auth headers.
  4. Extracts and returns `snapshotId` from the response.
- **Errors:** Raises `ValueError` for invalid inputs, `RuntimeError` if no `snapshotId` is returned, and `requests.HTTPError` on API failures.

#### `poll_snapshot(advertiser_id, snapshot_id) -> dict`

Polls the snapshot status until it reaches a terminal state.

- **Endpoint:** `GET {BASE_URL}/snapshot?advertiserId={id}&snapshotId={id}`
- **Flow:**
  1. Loops up to `MAX_POLL_ATTEMPTS` (60) times.
  2. On each iteration, sends a GET request with fresh auth headers.
  3. Checks `jobStatus` in the response:
     - `done` -- Returns the full response dict (contains `details` URL).
     - `failed` -- Raises `RuntimeError`.
     - `expired` -- Raises `RuntimeError`.
     - `pending` / `processing` -- Sleeps `POLL_INTERVAL` (30s) and retries.
     - Anything else -- Logs a warning and continues.
  4. If max attempts exceeded, raises `TimeoutError`.
- **Total timeout:** ~30 minutes (60 attempts x 30 seconds).

#### `download_report(file_url, advertiser_id, output_path) -> str`

Downloads, decompresses, and saves the report as a CSV file.

- **Endpoint:** `GET {DOWNLOAD_URL}/{fileId}?advertiserId={id}`
- **Flow:**
  1. Parses the `file_url` (from the poll response `details` field) to extract the file ID (last path segment).
  2. Constructs the download URL using the `DOWNLOAD_URL` base.
  3. Sends a streaming GET request (with `Content-Type` header removed).
  4. Writes the raw gzip response to a temporary `.gz` file.
  5. Decompresses the `.gz` file to the final CSV path using `gzip.open()`.
  6. Deletes the temporary `.gz` file.
- **Chunk size:** 8192 bytes for both download and decompression.

---

### `report_fetcher.py`

The CLI entry point that orchestrates the full workflow.

#### CLI Arguments

| Argument          | Required | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `--report-type`   | Yes      | One of the 7 valid report types                  |
| `--start-date`    | Yes      | Start date in `YYYY-MM-DD` format                |
| `--end-date`      | Yes      | End date in `YYYY-MM-DD` format                  |
| `--advertiser-id` | No       | Overrides `WALMART_ADVERTISER_ID` from `.env`    |

#### Execution Flow

```
1. Parse CLI arguments
2. Resolve advertiser ID (CLI flag > .env variable)
3. Validate date formats
4. Create reports/ directory if needed
5. Build output filename: {type}_{start}_{end}_{advertiser}_{timestamp}.csv
6. Step 1/3: create_snapshot() --> snapshotId
7. Step 2/3: poll_snapshot()   --> details URL
8. Step 3/3: download_report() --> CSV file on disk
9. Print summary (rows, columns, headers, file path)
```

#### Output Filename Format

```
{report_type}_{start_date}_{end_date}_{advertiser_id}_{YYYYMMDD_HHMMSS}.csv
```

Example: `campaign_2026-01-01_2026-01-15_500001_20260209_143022.csv`

#### Error Handling

The main function catches and handles these error types:

| Exception              | Cause                                    | Exit Code |
|------------------------|------------------------------------------|-----------|
| `ValueError`           | Invalid dates, report type, or inputs    | 1         |
| `requests.HTTPError`   | API returned a non-2xx status            | 1         |
| `TimeoutError`         | Polling exceeded max attempts            | 1         |
| `RuntimeError`         | Job failed/expired, missing response data| 1         |
| `KeyboardInterrupt`    | User pressed Ctrl+C                      | 130       |

For HTTP errors, the response body is also logged for debugging.

#### Summary Output

On successful download, the tool prints:

```
==================================================
DOWNLOAD COMPLETE
==================================================
  File:    reports/campaign_2026-01-01_2026-01-15_500001_20260209_143022.csv
  Rows:    1,234
  Columns: 12
  Headers: col1, col2, col3, col4, col5 ... (+7 more)
==================================================
```

---

## Supported Report Types

| Report Type | Max Date Range | Description          |
|-------------|---------------|----------------------|
| `campaign`  | 60 days       | Campaign-level data  |
| `lineItem`  | 60 days       | Line item metrics    |
| `tactic`    | 60 days       | Tactic performance   |
| `sku`       | 15 days       | SKU-level data       |
| `creative`  | 60 days       | Creative performance |
| `bid`       | 60 days       | Bid analytics        |
| `newBuyer`  | 60 days       | New buyer metrics    |

## API Workflow Diagram

```
Client                          Walmart API
  |                                  |
  |--- POST /snapshot/report ------->|  (create job)
  |<-------- { snapshotId } ---------|
  |                                  |
  |--- GET /snapshot?snapshotId= --->|  (poll status)
  |<-------- { status: pending } ----|
  |          ... sleep 30s ...       |
  |--- GET /snapshot?snapshotId= --->|  (poll again)
  |<-------- { status: done,     ----|
  |            details: <url> }      |
  |                                  |
  |--- GET /display/file/{id} ------>|  (download)
  |<-------- <gzip binary> ---------|
  |                                  |
  [decompress gzip -> save CSV]
```

## Dependencies

| Package        | Purpose                        |
|----------------|--------------------------------|
| `requests`     | HTTP client for API calls      |
| `python-dotenv`| Load `.env` file credentials   |

Standard library modules used: `argparse`, `csv`, `gzip`, `logging`, `os`, `sys`, `time`, `datetime`, `urllib.parse`.
