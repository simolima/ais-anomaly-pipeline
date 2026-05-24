# ais_impossible_speed.sql

**Layer:** Gold  
**Materialization:** table  
**Depends on:** `silver.ais_clean`

## Purpose

Detects vessels reporting physically impossible speeds between consecutive AIS positions. A vessel appearing to travel faster than 30 knots between two pings — a conservative ceiling for cargo and tanker vessels — likely indicates GNSS spoofing, AIS data injection, or MMSI collision between two different physical vessels.

## What it does

### 1. Build per-vessel timeline (`vessel_timeline`)
Same window-function approach as `ais_dark_gaps`: `LAG` on `BaseDateTime`, `LAT`, and `LON` partitioned by `MMSI`.

### 2. Compute implied speed (`with_implied_speed`)
Calculates the great-circle distance between consecutive positions using the **Haversine formula** (result in nautical miles), and divides by the elapsed time in hours to derive `implied_speed_knots`.

```sql
distance_nm = 3440.065 * 2 * asin(sqrt(
    pow(sin(radians(LAT - prev_lat) / 2), 2) +
    cos(radians(prev_lat)) * cos(radians(LAT)) *
    pow(sin(radians(LON - prev_lon) / 2), 2)
))
```

Rows with zero elapsed time are excluded to avoid division-by-zero.

### 3. Filter and score (`impossible`)
Keeps only rows where `implied_speed_knots > 30`. Each row is labelled `anomaly_type = 'impossible_speed'` and scored:

```
anomaly_score = min((implied_speed_knots - 30) / 70.0, 1.0)
```

A vessel implying 100 knots scores 1.0. Anything above 100 knots is capped at 1.0.

## Outputs

| Table | Notes |
|---|---|
| `gold.ais_impossible_speed` | One row per impossible-speed event with distance, speed, and score |

## Downstream consumers

- `gold.ais_anomaly_cues` (unioned with `ais_dark_gaps`)
