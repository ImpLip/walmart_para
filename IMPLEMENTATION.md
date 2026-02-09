# Implementation Guide

Technical documentation for the Walmart Ads Report Snapshot Fetcher.

## Architecture

The project follows a layered design with clear separation of concerns:

```
report_fetcher.py   (CLI orchestrator)
       |
snapshot_client.py  (API client - create, poll, download)
       |
   auth.py          (OAuth token + RSA signature + header assembly)
       |
  config.py         (environment variables & constants)
```

## File Breakdown

### `config.py`

Loads credentials from a `.env` file using `python-dotenv` and exposes them as module-level constants.

| Constant                | Purpose                                      | Default            |
|-------------------------|----------------------------------------------|--------------------|
| `WALMART_CLIENT_ID`     | Consumer ID (used in headers and signing)    | `""`               |
| `WALMART_CLIENT_SECRET` | Client secret (used for OAuth token request) | `""`               |
| `WALMART_PRIVATE_KEY_PATH` | Path to RSA private key `.pem` file       | `"private_key.pem"`|
| `WALMART_KEY_VERSION`   | Signature key version                        | `"1"`              |
| `WALMART_ADVERTISER_ID` | Default advertiser (overridable via CLI)     | `""`               |

**API Endpoints:**

| Constant       | URL                                                                                     |
|---------------|-----------------------------------------------------------------------------------------|
| `TOKEN_URL`   | `https://api-gateway.walmart.com/v3/token`                                              |
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

Handles the full Walmart authentication flow: OAuth token management, per-request RSA signature generation, and header assembly.

#### Authentication Flow

Every API request requires:
1. A valid **OAuth access token** (fetched dynamically, cached ~1 hour)
2. A **per-request RSA SHA256 signature** (generated from private key)
3. A **current timestamp** in epoch milliseconds

```
[Validate credentials]
        |
[Fetch OAuth token]  ←── cached until ~60s before expiry
        |
[Generate timestamp]
        |
[Build sign string]  →  ClientID\nTimestamp\nMETHOD\nPATH\n
        |
[RSA SHA256 sign]    →  sign with private key (.pem)
        |
[Base64 encode]      →  WM_SEC.AUTH_SIGNATURE
        |
[Assemble headers]
```

#### `_validate_credentials()`

Checks that `WALMART_CLIENT_ID`, `WALMART_CLIENT_SECRET`, and `WALMART_PRIVATE_KEY_PATH` are set. Raises `ValueError` if any are missing.

#### `_get_access_token() -> str`

Fetches an OAuth access token via the Walmart token endpoint.

- **Endpoint:** `POST https://api-gateway.walmart.com/v3/token`
- **Auth:** HTTP Basic (`base64(clientId:clientSecret)`)
- **Body:** `grant_type=client_credentials`
- **Response:** `{ "access_token": "...", "expires_in": 3600 }`
- **Caching:** Token is cached in a module-level `_token_cache` dict. A new token is only fetched when the cached one is within 60 seconds of expiry.

#### `_load_private_key()`

Reads and parses the RSA private key from the PEM file specified by `WALMART_PRIVATE_KEY_PATH`. Uses `cryptography.hazmat.primitives.serialization.load_pem_private_key()`.

#### `_generate_signature(method, url, timestamp) -> str`

Generates the per-request RSA SHA256 signature.

1. Extracts the **request path** from the full URL (e.g., `/api/v1/snapshot/report`)
2. Builds the **string to sign** in the exact format required by Walmart:
   ```
   {ConsumerID}\n{Timestamp}\n{HTTP_METHOD}\n{REQUEST_PATH}\n
   ```
3. Signs with **RSA PKCS1v15 + SHA256** using the private key
4. **Base64 encodes** the result

The signature must be regenerated for every request because it includes the timestamp and request path.

#### `get_auth_headers(method, url) -> dict`

Main entry point. Assembles all 6 required headers for a Walmart API request.

**Parameters:**
- `method` — HTTP method (`"GET"`, `"POST"`, etc.)
- `url` — Full request URL (path is extracted for signing)

**Returns:**
```python
{
    "Authorization": "Bearer <access_token>",
    "WM_CONSUMER.ID": "<client_id>",
    "WM_SEC.AUTH_SIGNATURE": "<rsa_signature>",
    "WM_CONSUMER.intimestamp": "<epoch_milliseconds>",
    "WM_SEC.KEY_VERSION": "<version>",
    "Content-Type": "application/json",
}
```

The timestamp used in the header matches the one used in the signature — both are generated in the same call.

---

### `snapshot_client.py`

The core API client. Contains three public functions and one private validator. Each function passes the HTTP method and URL to `get_auth_headers()` so that signatures are generated correctly per-request.

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
  3. Sends POST request with JSON payload and auth headers (signed for `POST` + request path).
  4. Extracts and returns `snapshotId` from the response.
- **Errors:** Raises `ValueError` for invalid inputs, `RuntimeError` if no `snapshotId` is returned, and `requests.HTTPError` on API failures.

#### `poll_snapshot(advertiser_id, snapshot_id) -> dict`

Polls the snapshot status until it reaches a terminal state.

- **Endpoint:** `GET {BASE_URL}/snapshot?advertiserId={id}&snapshotId={id}`
- **Flow:**
  1. Loops up to `MAX_POLL_ATTEMPTS` (60) times.
  2. On each iteration, sends a GET request with fresh auth headers (new signature + timestamp each poll).
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
  3. Sends a streaming GET request signed for the download path (with `Content-Type` header removed).
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
  |--- POST /v3/token ------------->|  (OAuth: get access token)
  |<-------- { access_token } ------|
  |                                  |
  |  [generate timestamp]           |
  |  [build sign string]            |
  |  [RSA SHA256 sign + base64]     |
  |                                  |
  |--- POST /snapshot/report ------>|  (create job, signed)
  |<-------- { snapshotId } --------|
  |                                  |
  |  [re-sign for GET]              |
  |--- GET /snapshot?snapshotId= -->|  (poll status, signed)
  |<-------- { status: pending } ---|
  |          ... sleep 30s ...      |
  |  [re-sign for GET]              |
  |--- GET /snapshot?snapshotId= -->|  (poll again, signed)
  |<-------- { status: done,     ---|
  |            details: <url> }     |
  |                                  |
  |  [re-sign for GET]              |
  |--- GET /display/file/{id} ----->|  (download, signed)
  |<-------- <gzip binary> --------|
  |                                  |
  [decompress gzip -> save CSV]
```

## Authentication Deep Dive

### OAuth Token (Step 1)

```
POST https://api-gateway.walmart.com/v3/token
Authorization: Basic base64(clientId:clientSecret)
Content-Type: application/x-www-form-urlencoded
Body: grant_type=client_credentials

Response: { "access_token": "xxx", "expires_in": 3600 }
```

The token is cached in memory and reused until 60 seconds before expiry.

### RSA Signature (Per Request)

For every API call, a unique signature is generated:

1. **Build the sign string** (newlines are required):
   ```
   {CLIENT_ID}
   {TIMESTAMP_MS}
   {HTTP_METHOD}
   {REQUEST_PATH}

   ```

2. **Sign** with RSA PKCS1v15 + SHA256 using the private key (`.pem`)

3. **Base64 encode** the raw signature bytes

The timestamp in the signature must exactly match the `WM_CONSUMER.intimestamp` header.

### Common Auth Failures

| Symptom               | Cause                                          |
|-----------------------|------------------------------------------------|
| 401 Unauthorized       | Expired token, wrong key, or signature mismatch|
| Invalid Signature      | Wrong path in sign string, bad newline format  |
| Token request fails    | Wrong client ID or secret                      |

## Dependencies

| Package        | Purpose                                    |
|----------------|--------------------------------------------|
| `requests`     | HTTP client for API calls                  |
| `python-dotenv`| Load `.env` file credentials               |
| `cryptography` | RSA SHA256 signing with private key (.pem) |

Standard library modules used: `argparse`, `base64`, `csv`, `gzip`, `logging`, `os`, `sys`, `time`, `datetime`, `urllib.parse`.
