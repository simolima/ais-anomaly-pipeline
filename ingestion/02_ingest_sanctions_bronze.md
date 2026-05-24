# 02_ingest_sanctions_bronze.py

**Layer:** Bronze  
**Runtime:** Databricks notebook (PySpark)  
**Schedule:** Weekly refresh (sanctions lists change infrequently)

## Purpose

Downloads the OpenSanctions bulk dataset, filters it to `Vessel` entities only, and overwrites the `bronze.sanctions` Delta table. This table is later joined against AIS anomalies to flag vessels appearing on international sanctions lists.

## Data source

`https://data.opensanctions.org/datasets/default/entities.ftm.json`  
The file is a newline-delimited JSON (FtM format) containing all entities across all OpenSanctions datasets (vessels, persons, companies, etc.).

## What it does

1. Streams the bulk JSON line by line to avoid loading the full dataset into memory.
2. Discards any entity whose `schema` is not `Vessel`.
3. Extracts key fields: `entity_id`, `entity_name`, `mmsi`, `imo_number`, `flag`, `sanctions_list` (comma-separated dataset names), and `designation_date`.
4. Creates a Spark DataFrame from the collected rows, appends `_ingestion_ts`.
5. **Overwrites** `bronze.sanctions` on each run (full refresh — the authoritative snapshot is always the latest).

## Outputs

| Table | Mode | Notes |
|---|---|---|
| `bronze.sanctions` | overwrite | Latest sanctioned vessel entities |

## Schema

| Column | Type | Source |
|---|---|---|
| `entity_id` | string | OpenSanctions entity ID |
| `entity_name` | string | Primary vessel name |
| `mmsi` | string | Maritime Mobile Service Identity |
| `imo_number` | string | IMO vessel number |
| `flag` | string | Flag state (ISO country code) |
| `sanctions_list` | string | Comma-separated dataset names (e.g. `us_ofac_sdn, eu_fsf`) |
| `designation_date` | string | Date first designated |
| `_ingestion_ts` | timestamp | Load time |

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENSANCTIONS_API_KEY` | Optional | API key for authenticated access (not used for bulk download) |

## Dependencies

- PySpark / Databricks Runtime
- `requests`

## Notes

The join key in downstream models is `MMSI`. IMO numbers are more stable identifiers, but not all sanctioned vessel records include both — the pipeline uses MMSI as the primary join key because it is the field present in the raw AIS stream.
