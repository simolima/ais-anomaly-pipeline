# ais_dark_gaps.sql

**Layer:** Gold  
**Materialization:** table  
**Depends on:** `silver.ais_clean`

## Purpose

Detects vessels that went "dark" — periods where a vessel's AIS transponder was silent for 6 or more consecutive hours. AIS silence can indicate deliberate transponder shutdown, a tactic associated with illicit ship-to-ship transfers, sanctions evasion, or entry into restricted waters.

## What it does

### 1. Build per-vessel timeline (`vessel_timeline`)
Uses window functions (`LAG`) partitioned by `MMSI` and ordered by `BaseDateTime` to attach each position record with its predecessor's timestamp and coordinates.

### 2. Identify gaps (`gaps`)
Computes the time difference (in hours) between consecutive records. Rows where the gap exceeds **6 hours** are selected as dark-gap events. The CTE captures:
- `gap_start` / `gap_end`: the timestamps bracketing the silence
- `gap_hours`: duration of the gap
- Last known position (`prev_lat`, `prev_lon`) and reappearance position (`LAT`, `LON`)

### 3. Score and label
Each gap row is labelled `anomaly_type = 'dark_gap'` and assigned an `anomaly_score` capped at 1.0:

```
anomaly_score = min(gap_hours / 24.0, 1.0)
```

A 24-hour gap scores 1.0 (maximum). A 6-hour gap scores 0.25.

## Outputs

| Table | Notes |
|---|---|
| `gold.ais_dark_gaps` | One row per dark-gap event, with duration, positions, and score |

## Downstream consumers

- `gold.ais_anomaly_cues` (unioned with `ais_impossible_speed`)
