# CLAUDE.md — AIS Anomaly Pipeline

Engineering reference for AI-assisted work on this repo. Read before making any changes.

---

## Project purpose

End-to-end data pipeline that ingests AIS (Automatic Identification System) vessel tracking data from NOAA, transforms it through a medallion architecture, detects anomalous vessel behaviour, cross-references with OpenSanctions, and surfaces alerts. Built in a NATO maritime security context.

---

## Tech stack

| Layer | Technology |
|---|---|
| Compute | Databricks Serverless (Free Edition) |
| Storage | Delta Lake on Unity Catalog |
| Orchestration | Databricks Workflows (Asset Bundles) |
| Ingestion | Python · PySpark · pandas · zstandard |
| Transformation | dbt-databricks |
| ML | scikit-learn (Isolation Forest) |
| CI/CD | GitHub Actions → `databricks bundle deploy` |
| Tests | pytest |

---

## Databricks environment — critical constraints

This workspace is **Databricks Free Edition Serverless**. Several standard patterns do NOT work here:

| Approach | Status | Reason |
|---|---|---|
| `saveAsTable` to Unity Catalog | ⚠️ Works but fragile | S3 CRC HEAD request fails at high commit frequency |
| `USE CATALOG hive_metastore` | ❌ Fails | hive_metastore does not exist — UC-only workspace |
| `dbfs:/` paths | ❌ Fails | DBFS root is disabled on this workspace |
| Many small Delta commits | ❌ Risky | Triggers S3 400 Bad Request CRC error |
| `__file__` in exec context | ❌ Not defined | Databricks runs scripts via `exec()`, `__file__` is unavailable |

**What works:**
- `saveAsTable("bronze.ais_raw")` with infrequent writes (WRITE_EVERY=50, ~20 commits per 7-day run)
- Unity Catalog catalog name is `workspace` (visible in UI as `workspace.bronze.ais_raw`)
- All Python utilities must be inlined in scripts — no local module imports via sys.path manipulation

---

## Data source

- **Provider:** NOAA MarineCadastre (CC0 public domain)
- **URL pattern:** `https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-MM-DD.csv.zst`
- **Format:** CSV compressed with Zstandard, ~7.3M rows per day
- **Scale:** ~2.7B rows for full year 2024

### Column names (current format — post-2024 NOAA schema)

The source uses **lowercase snake_case** column names. Never use the legacy uppercase names.

| CSV column | Spark schema field | Type |
|---|---|---|
| `mmsi` | `mmsi` | StringType (keep as string for joins) |
| `base_date_time` | `base_date_time` | TimestampType, format `yyyy-MM-dd HH:mm:ss` |
| `latitude` | `latitude` | DoubleType |
| `longitude` | `longitude` | DoubleType |
| `sog` | `sog` | DoubleType (knots, 0–102.2) |
| `cog` | `cog` | DoubleType |
| `heading` | `heading` | IntegerType nullable, use `"Int32"` pandas dtype |
| `vessel_name` | `vessel_name` | StringType |
| `imo` | `imo` | StringType |
| `call_sign` | `call_sign` | StringType |
| `vessel_type` | `vessel_type` | IntegerType, use `"Int32"` pandas dtype |
| `status` | `status` | IntegerType, use `"Int32"` pandas dtype |
| `length` | `length` | IntegerType, use `"Int32"` pandas dtype |
| `width` | `width` | IntegerType, use `"Int32"` pandas dtype |
| `draft` | `draft` | DoubleType |
| `cargo` | `cargo` | IntegerType, use `"Int32"` pandas dtype |
| `transceiver` | `transceiver` | StringType |

---

## Architecture — medallion layers

```
NOAA Azure Blob (daily .csv.zst)
        ↓
bronze.ais_raw          ← raw AIS, append-only Delta table
bronze.sanctions        ← OpenSanctions vessel entities (overwrite)
        ↓ dbt
silver.ais_clean        ← deduplicated, validated, no bad coords/speed
        ↓ dbt
gold.ais_dark_gaps      ← AIS silence ≥ 6 hours per vessel
gold.ais_impossible_speed ← implied speed > 30 knots
gold.ais_anomaly_cues   ← union of all anomalies + sanctions join (per-event detail)
gold.vessel_features    ← per-vessel behavioural aggregates (feature table for ML)
        ↓
ml/isolation_forest.py  ← per-vessel Isolation Forest → gold.vessel_risk_scores
        ↓
alerts/send_alert.py    ← email top-N vessels by risk_score
```

---

## File structure

```
ingestion/
  01_ingest_ais_bronze.py   — incremental AIS ingestion (Databricks script)
  02_ingest_sanctions_bronze.py — OpenSanctions vessel pull (Databricks script)
  utils.py                  — pure Python helpers for tests (NOT imported on Databricks)

dbt/
  models/sources.yml        — bronze source definitions + schema tests
  models/silver/ais_clean.sql
  models/silver/schema.yml
  models/gold/ais_anomaly_cues.sql
  models/gold/ais_dark_gaps.sql
  models/gold/ais_impossible_speed.sql
  models/gold/schema.yml

ml/
  isolation_forest.py

alerts/
  send_alert.py

tests/
  test_ingestion_utils.py   — pytest for incremental window logic

.github/workflows/
  deploy.yml                — auto bundle deploy on push to main

databricks.yml              — Asset Bundle: two jobs defined
```

---

## Databricks jobs (databricks.yml)

Two separate jobs — do not merge them:

**`ais_ingest`** — runs hourly, `max_concurrent_runs: 1`
- Task: `ingest_ais` only
- Processes next 7-day window of AIS data
- Exits cleanly with `sys.exit(0)` when all 2024 data is loaded

**`ais_pipeline`** — no schedule, run manually
- Tasks: `ingest_sanctions` → `dbt_transform` → `ml_scoring` → `send_alert`
- Run only after `bronze.ais_raw` is fully loaded

---

## Incremental ingestion logic

State is tracked via the `_source_file` column in `bronze.ais_raw`:

1. At startup, query distinct `_source_file` values → `ingested_files`
2. `_compute_window()` finds the max ingested date, returns the next 7-day window
3. For each file in the window: DELETE existing rows (idempotent), then download and write
4. DELETE happens only AFTER confirming HTTP 200 — prevents data loss on network failures
5. `WRITE_EVERY = 50` (flush every 2.5M rows) keeps Delta commits to ~20 per run

---

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Deploy bundle to dev (safe — creates isolated job copy)
databricks bundle deploy --target dev

# Deploy to prod (done automatically by GitHub Actions on push to main)
databricks bundle deploy --target prod

# Trigger a manual run
databricks bundle run ais_ingest --target prod
```

---

## dbt conventions

- Profile: `ais_databricks` (defined in `~/.dbt/profiles.yml`)
- Catalog: `workspace` (Unity Catalog, Free Edition default)
- Silver models: `+materialized: table`, schema `silver`
- Gold models: `+materialized: table`, schema `gold`
- All models have a corresponding `schema.yml` with `not_null` and `accepted_values` tests
- `sources.yml` defines `bronze.ais_raw` and `bronze.sanctions` with column-level tests

---

## Testing

```bash
python -m pytest tests/ -v          # unit tests (no Spark required)
databricks bundle run dbt_transform  # dbt schema tests on live data
```

`ingestion/utils.py` is the source of truth for pure logic. The functions are **duplicated inline** in `01_ingest_ais_bronze.py` (prefixed with `_`) because `__file__` is not available in the Databricks exec context and module imports cannot be resolved at runtime.

---

## Lessons learned

- **Create a named catalog before writing any code.** Tables currently live in `workspace.bronze.*` (Databricks default). In a real project, create `CREATE CATALOG ais_pipeline` first, then `CREATE SCHEMA ais_pipeline.bronze` etc. Migrating data after the fact is expensive.
- **Databricks Free Edition is not representative of a real environment.** hive_metastore is gone, DBFS root is disabled, UC S3 has CRC restrictions. Patterns that work here may not be the right patterns for production.
- **Test the data source before designing the schema.** The original schema used legacy NOAA column names (uppercase). The actual files use snake_case. Always download a sample file first.

---

## Known issues

- **S3 CRC error** (`400 Bad Request` on `HEAD` to UC S3): occurs when Delta commit frequency is too high. Mitigated by `WRITE_EVERY=50`. If it recurs, increase further.
- **OOM on Serverless**: loading a full day (~7.3M rows) at once crashes the driver. Use chunked reads with `CHUNK=50_000` and buffer-based flushing.
- **`__file__` undefined**: do not use `__file__` in Databricks scripts. Do not attempt `sys.path` manipulation to import local modules — inline the code instead.
