# ais_anomaly_cues.sql

**Layer:** Gold  
**Materialization:** table  
**Depends on:** `gold.ais_dark_gaps`, `gold.ais_impossible_speed`, `bronze.sanctions`

## Purpose

Merges all rule-based anomaly signals into a single unified table, then enriches each anomaly with OpenSanctions data. This is the primary feed for the ML scoring step and the alerting layer.

## What it does

### 1. Normalize schemas
`ais_dark_gaps` and `ais_impossible_speed` use slightly different column names for the event timestamp and position. Two CTEs (`dark_gaps`, `impossible_speeds`) rename these columns to a common schema:

| Unified column | Dark gap source | Impossible speed source |
|---|---|---|
| `event_ts` | `gap_start` | `event_start` |
| `lat` | `last_known_lat` | `from_lat` |
| `lon` | `last_known_lon` | `from_lon` |

### 2. Union all anomalies (`all_anomalies`)
`UNION ALL` on the two normalized CTEs. Each row carries `MMSI`, `VesselName`, `event_ts`, `lat`, `lon`, `anomaly_type`, and `anomaly_score`.

### 3. Enrich with sanctions (`enriched`)
Left-joins `bronze.sanctions` on `MMSI`. Vessels with a sanctions match gain three additional columns:
- `sanctions_match` — entity name from OpenSanctions
- `sanctions_list` — which list(s) the vessel appears on
- `designation_date` — when the designation was issued

Vessels with no match retain `NULL` in these columns.

### 4. Final output
Results ordered by `anomaly_score DESC` so the highest-risk events appear first.

## Outputs

| Table | Notes |
|---|---|
| `gold.ais_anomaly_cues` | Unified, enriched anomaly events ready for ML scoring |

## Downstream consumers

- `ml/isolation_forest.py` — reads this table to add an Isolation Forest outlier score
- `alerts/send_alert.py` — reads `gold.vessel_risk_scores` (output of the ML step)
