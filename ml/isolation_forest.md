# isolation_forest.py

**Layer:** Gold (ML scoring)  
**Runtime:** Databricks notebook (PySpark + scikit-learn)  
**Schedule:** Run after dbt Gold models complete

## Purpose

Applies an unsupervised Isolation Forest model to the rule-based anomaly cues produced by dbt, producing a calibrated outlier score for each event. The results are written to `gold.vessel_risk_scores`, which drives the daily alerting pipeline.

## What it does

1. **Loads** `gold.ais_anomaly_cues` into a Pandas DataFrame via `spark.table().toPandas()`.
2. **Feature matrix:** currently uses `anomaly_score` as the sole feature. The `FEATURES` list is designed to be extended with richer signals (`gap_hours`, `distance_nm`, etc.) as the pipeline matures.
3. **Scales** features with `StandardScaler` (zero mean, unit variance).
4. **Trains** an `IsolationForest` with:
   - `n_estimators=200` (200 trees for stable estimates)
   - `contamination=0.05` (assumes ~5% of events are genuine anomalies)
   - `random_state=42` (reproducible splits)
5. **Scores** each row: `if_score = -1` (outlier) or `1` (normal); adds boolean `is_outlier`.
6. **Writes** the scored DataFrame back to `gold.vessel_risk_scores` as a Delta table (overwrite on each run — scores are re-derived from the full current anomaly set).

## Outputs

| Table | Mode | Notes |
|---|---|---|
| `gold.vessel_risk_scores` | overwrite | Anomaly cues enriched with `if_score` and `is_outlier` |

## Schema additions over `ais_anomaly_cues`

| Column | Type | Description |
|---|---|---|
| `if_score` | int | `-1` = outlier, `1` = normal (raw Isolation Forest output) |
| `is_outlier` | bool | `True` when `if_score == -1` |
| `_scored_at` | timestamp | When this scoring run completed |

## Dependencies

- PySpark / Databricks Runtime
- `scikit-learn`
- `pandas`

## Notes

The model is retrained from scratch on each run — there is no model persistence. This is intentional for a daily batch pipeline where the distribution of anomalies shifts over time and stale models would drift. Persist the model artifact (MLflow) if scoring latency or reproducibility become requirements.
