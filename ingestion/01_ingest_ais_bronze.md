# 01_ingest_ais_bronze.py

**Layer:** Bronze  
**Runtime:** Databricks notebook (PySpark)  
**Schedule:** Run manually or once per batch period before dbt models

## Purpose

Downloads daily AIS (Automatic Identification System) GeoParquet files from NOAA's public Azure Blob Storage and appends them into the `bronze.ais_raw` Delta table.

## Data source

`https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/`  
Files follow the naming convention `AIS_2024_<MM>_<DD>.zip` — each ZIP contains a single CSV for that day. The script currently ingests January and February (configurable via `MONTHS` and `DAYS`).

## What it does

1. Creates the `bronze` database if it does not exist.
2. Iterates over each configured month/day combination and constructs the file URL.
3. Downloads the ZIP file via HTTP (`requests`) into a local staging directory (`/tmp/ais_staging`).
4. Extracts the CSV from the ZIP archive.
5. Reads the CSV with Spark (`header=true`, `inferSchema=true`), adds `_ingestion_ts` (load timestamp) and `_source_file` (filename) metadata columns.
6. Appends the DataFrame to `bronze.ais_raw` in Delta format.
7. Deletes both the ZIP and the extracted CSV after each successful write to avoid disk pressure.
8. Skips files that return a non-200 HTTP status (day not published yet).

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

## Notes

Start with 1–2 months to validate the pipeline. The full 2024 dataset is ~116 GB zipped (CSV format). `inferSchema=true` scans the first CSV to derive column types — replace with an explicit schema once the column list is confirmed to avoid the extra scan on each file.
