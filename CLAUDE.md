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
gold.ais_anomaly_cues   ← union of all anomalies + sanctions join
        ↓
ml/isolation_forest.py  ← unsupervised anomaly scoring
        ↓
alerts/send_alert.py    ← dispatch on high-scoring anomalies
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

## Git & CI workflow

**Never commit directly to `main`.** All changes go through a pull request:

1. Create a branch: `git checkout -b <type>/<short-desc>` (e.g. `feat/…`, `fix/…`, `docs/…`)
2. Commit on the branch (single commit unless the change is genuinely separable)
3. Push the branch and open a PR against `main` with `gh pr create`
4. CI (`.github/workflows/ci.yml`) runs on the PR: **pytest + `dbt parse`**. It must pass before merge.
5. Merge to `main` → `.github/workflows/deploy.yml` runs `databricks bundle deploy --target prod`

So: **CI tests gate the PR, deploy happens on merge.** Direct pushes to `main` bypass the
test gate — don't do it. Enable branch protection (require the `CI` check) so this is enforced.

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
- Silver/gold models are **incremental** (`incremental_strategy='replace_where'`), schemas `silver` / `gold`
- All models have a corresponding `schema.yml` with `not_null` and `accepted_values` tests
- `sources.yml` defines `bronze.ais_raw` and `bronze.sanctions` with column-level tests

### Incremental (windowed) processing

Every silver/gold model is driven by an `event_date` window. With 2B+ rows in
`bronze.ais_raw`, a full refresh is infeasible on Serverless — always process a window.

- **`event_date`** is the window/replace_where key on every model. It is anchored on the
  **in-window ping**: the row date for `ais_clean`, the reappearance (`gap_end`) for
  `ais_dark_gaps`, the second ping (`event_end`) for `ais_impossible_speed`, carried up
  unchanged into `ais_anomaly_cues`. Never key on the gap/event *start* — it may sit in a
  prior window and `replace_where` would reject rows outside the predicate.
- **Lookback**: the gold LAG models need only the single prior ping per vessel before the
  window (LAG looks one row back). They recompute it from `ais_clean` over **all prior
  history** (unbounded `event_date < start_date`) for full-history parity — durable and
  reprocess-safe, no mutable state table. Cost: each windowed run scans the history before
  the window to find that one prior ping; if this gets too heavy, cluster `ais_clean` by
  `event_date` or introduce a per-vessel state table.
- **Removed** the legacy global `no_retransmissions` dedup in `ais_clean`: it collapsed
  moored-vessel timelines and produced false dark gaps, and was globally scoped.

The window is resolved by the `ais_window()` macro (`dbt/macros/ais_window.sql`), in
priority order: explicit `start_date`+`end_date` → `rolling_days` → no-op sentinel.

```bash
# Explicit window / reprocess (delete+reinsert only those days):
dbt run  --vars '{start_date: 2024-03-01, end_date: 2024-03-07}'
dbt test --vars '{start_date: 2024-03-01, end_date: 2024-03-07}'

# Rolling window — the NORMAL scheduled mode: process the last N days [today-N, today]:
dbt run  --vars '{rolling_days: 7}'

# Initial load: run successive explicit windows (avoids a 2B-row full build).
# Full rebuild (small datasets only): dbt run --full-refresh  (NO vars — never combine
# --full-refresh with vars, it would wipe the table down to a single window).
```

The `ais_dbt` job exposes `rolling_days` (default `7`) plus empty `start_date` / `end_date`
params. **Scheduled runs use the rolling 7-day window**; setting the date params overrides
it for a manual reprocess. The schedule is defined but **PAUSED** — unpause when going live.
The daily 7-day overlap also keeps boundary anomalies fresh (see reprocessing caveat below).

### Migration & reprocessing caveats

- **Switching an existing `materialized='table'` relation to incremental**: the old table
  has no `event_date` column, so the first `replace_where` run would fail. The first run
  after this change **must be `dbt run --full-refresh`** (drops & recreates with the new
  schema), or drop the old tables first. Only relevant if silver/gold were already built;
  a fresh first run creates them correctly.
- **Reprocessing a window with *changed* data**: the LAG lookback reaches backward, not
  forward, so re-running window W with corrected data does not refresh the first anomaly
  in W+1 (which depended on W's last ping). NOAA files are immutable, so a reprocess
  normally reproduces identical results. If you ever reprocess *corrected* data, also
  reprocess the following window. The rolling daily 7-day window mitigates this in normal
  operation by re-deriving recent boundaries every day.
- **`dbt test` is not windowed yet**: generic tests (`not_null`, `accepted_values`) scan
  the whole target relation regardless of `--vars`. On 2B-row tables this is a full scan
  each run — open item, window the tests with a `where` config if it becomes a problem.

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
