"""Compute the next dbt processing window and expose it as Databricks task values.

Mirrors the bronze ingestion's _compute_window: it advances one 7-day window at a time
through 2024. The watermark is an EXPLICIT state table (silver.dbt_window_state) that is
only advanced by commit_window.py after the whole dbt task succeeds — NOT the max date in
silver.ais_clean. This way a partial failure (silver committed, a gold model failed) does
not skip the window: the watermark stays put and the next run reprocesses it (replace_where
is idempotent).

Run once per dbt job run, BEFORE the dbt task. The window is computed a single time here
and passed to every dbt model via --vars, so silver and gold all process the same window.

Behaviour:
  * explicit override (start_date + end_date passed as task params) -> use them verbatim,
    and do NOT advance the forward watermark (advance=false)
  * otherwise -> [last_end + 1 day, + 7 days], capped at END_DATE (advance=true)
  * once past END_DATE -> 2999-01-01 sentinel so the dbt run is a no-op (advance=false)

Sets task values start_date / end_date / advance, consumed by the dbt task and by
commit_window.py.
"""

import sys
from datetime import date, timedelta

from pyspark.sql import SparkSession
from pyspark.dbutils import DBUtils

spark   = SparkSession.builder.getOrCreate()
dbutils = DBUtils(spark)

START_DEFAULT = date(2024, 1, 1)
END_DATE      = date(2024, 12, 31)
WINDOW_DAYS   = 7
SENTINEL      = "2999-01-01"
STATE_TABLE   = "silver.dbt_window_state"

# Optional explicit override, passed as task parameters (job parameters start_date/end_date).
arg_start = sys.argv[1].strip() if len(sys.argv) > 1 else ""
arg_end   = sys.argv[2].strip() if len(sys.argv) > 2 else ""

if arg_start and arg_end:
    # explicit reprocess: use the given window, leave the forward watermark untouched
    start_str, end_str, advance = arg_start, arg_end, "false"
    print(f"Explicit reprocess window: {start_str} -> {end_str} (watermark unchanged)")
else:
    try:
        rows = spark.sql(f"select last_end from {STATE_TABLE}").collect()
        last_end = rows[0]["last_end"] if rows else None
    except Exception as e:  # state table not created yet (very first run)
        print(f"{STATE_TABLE} not readable yet ({e}); starting from {START_DEFAULT}")
        last_end = None

    start = START_DEFAULT if last_end is None else last_end + timedelta(days=1)

    if start > END_DATE:
        print("All 2024 data already transformed — emitting no-op window.")
        start_str = end_str = SENTINEL
        advance = "false"
    else:
        end = min(start + timedelta(days=WINDOW_DAYS - 1), END_DATE)
        start_str, end_str, advance = start.isoformat(), end.isoformat(), "true"
        print(f"Next dbt window: {start_str} -> {end_str}")

dbutils.jobs.taskValues.set(key="start_date", value=start_str)
dbutils.jobs.taskValues.set(key="end_date",   value=end_str)
dbutils.jobs.taskValues.set(key="advance",    value=advance)
