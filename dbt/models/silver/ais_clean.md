# ais_clean.sql

**Layer:** Silver  
**Materialization:** table  
**Depends on:** `bronze.ais_raw`

## Purpose

Cleans and validates the raw AIS positions ingested into the Bronze layer. Produces a deduplicated, quality-filtered table that all downstream Gold models read from.

## What it does

Three sequential CTEs apply data quality rules:

### 1. Deduplication (`deduplicated`)
Removes exact duplicate records sharing the same `MMSI` and `BaseDateTime`. When duplicates exist, keeps the row with the latest `_ingestion_ts` (most recent load wins), handling cases where the same message was re-downloaded across ingestion runs.

### 2. Retransmission removal (`no_retransmissions`)
Removes stale retransmissions — rows where `MMSI`, `LAT`, `LON`, `SOG`, and `COG` are all identical but the timestamp differs. These represent AIS messages that were re-broadcast by a relay station without any vessel movement. Only the earliest timestamp is kept per position/speed/course combination.

### 3. Coordinate and speed validation (`validated`)
Tags rows with a `quality_flag` if they contain out-of-range values:

| Flag | Condition |
|---|---|
| `invalid_lat` | LAT outside `[-90, 90]` |
| `invalid_lon` | LON outside `[-180, 180]` |
| `invalid_sog` | SOG outside `[0, 102.2]` knots |

The final `SELECT` discards all tagged rows (`quality_flag IS NULL`).

## Outputs

| Table | Notes |
|---|---|
| `silver.ais_clean` | Clean, deduplicated AIS positions ready for anomaly detection |

## Downstream consumers

- `gold.ais_dark_gaps`
- `gold.ais_impossible_speed`
