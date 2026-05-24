# 01_ingest_ais_bronze.py

**Layer:** Bronze  
**Runtime:** Databricks notebook (PySpark)  
**Schedule:** Run manually or once per batch period before dbt models

## Purpose

Downloads daily AIS (Automatic Identification System) Zstd-compressed CSV files from NOAA MarineCadastre and appends them into the `bronze.ais_raw` Delta table.

## Data source

**Dataset page:** [hub.marinecadastre.gov/pages/vesseltraffic](https://hub.marinecadastre.gov/pages/vesseltraffic)  
**Download index:** `https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html`

Files follow the naming convention `ais-2024-<MM>-<DD>.csv.zst` — each file is a CSV compressed with Zstandard. The script currently ingests January and February (configurable via `MONTHS` and `DAYS`).

> `coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/` is a legacy mirror serving `.zip` files — still accessible but not the authoritative source.

## What it does

1. Creates the `bronze` database if it does not exist.
2. Iterates over each configured month/day combination and constructs the file URL.
3. Downloads the `.csv.zst` file via HTTP (`requests`) into a local staging directory (`/tmp/ais_staging`).
4. Decompresses the Zstd file to `.csv` using the `zstandard` library.
5. Reads the CSV with Spark (explicit schema, `timestampFormat` for ISO 8601), adds `_ingestion_ts` (load timestamp) and `_source_file` (filename) metadata columns.
6. Appends the DataFrame to `bronze.ais_raw` in Delta format.
7. Deletes both the ZIP and the extracted CSV after each successful write to avoid disk pressure.
8. Skips files that return a non-200 HTTP status (day not published yet).

## Schema (`bronze.ais_raw`)

| Column | Type | Notes |
|---|---|---|
| `MMSI` | string | 9-digit vessel identifier — kept as string to join with `bronze.sanctions.mmsi` |
| `BaseDateTime` | timestamp | ISO 8601 (`yyyy-MM-dd'T'HH:mm:ss`) |
| `LAT` | double | Decimal degrees |
| `LON` | double | Decimal degrees |
| `SOG` | double | Speed over ground in knots |
| `COG` | double | Course over ground in degrees |
| `Heading` | integer | True heading; `511` = not available |
| `VesselName` | string | |
| `IMO` | string | Includes "IMO" prefix in raw data (e.g. `IMO7938024`) |
| `CallSign` | string | |
| `VesselType` | integer | NAIS vessel type code |
| `Status` | integer | Navigation status code |
| `Length` | integer | Metres |
| `Width` | integer | Metres |
| `Draft` | double | Metres |
| `Cargo` | integer | Cargo type code |
| `TransceiverClass` | string | `A` or `B` |
| `_ingestion_ts` | timestamp | Load time (added by script) |
| `_source_file` | string | Source ZIP filename (added by script) |

## Outputs

| Table | Mode | Notes |
|---|---|---|
| `bronze.ais_raw` | append | Raw AIS positions with ingestion metadata |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MONTHS` | `["01", "02"]` | List of two-digit month strings to ingest |
| `DAYS` | `range(1, 32)` | Day range (non-existent days are skipped silently) |
| `TARGET` | `bronze.ais_raw` | Destination Delta table |

## Dependencies

- PySpark / Databricks Runtime
- `requests`
- `zstandard` (`pip install zstandard` se non presente nel cluster)

## Notes

Start with 1–2 months to validate the pipeline. The full 2024 dataset is ~116 GB zipped. The schema is declared explicitly (`AIS_SCHEMA`) — do not switch to `inferSchema` as Spark would infer `MMSI` as `long`, breaking the join against `bronze.sanctions.mmsi` (string).
