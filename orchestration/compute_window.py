"""Compute the next dbt processing window and expose it as Databricks task values.

Mirrors the bronze ingestion's _compute_window: it advances one 7-day window at a time
through 2024, based on the max event_date already transformed into silver.ais_clean.

Run once per dbt job run, BEFORE the dbt task. The window is computed a single time here
and passed to every dbt model via --vars, so silver and gold all process the same window
(computing it inside dbt would be wrong: by the time the gold models run, silver has
already advanced).

Behaviour:
  * explicit override (start_date + end_date passed as task params) -> use them verbatim
  * otherwise -> [max(event_date in silver.ais_clean) + 1 day, + 7 days], capped at END_DATE
  * once past END_DATE -> emit the 2999-01-01 sentinel so the dbt run is a no-op

Sets task values `start_date` and `end_date`, consumed by the dbt task as
{{tasks.compute_window.values.start_date}} / .end_date.
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

# Optional explicit override, passed as task parameters (job parameters start_date/end_date).
arg_start = sys.argv[1].strip() if len(sys.argv) > 1 else ""
arg_end   = sys.argv[2].strip() if len(sys.argv) > 2 else ""

if arg_start and arg_end:
    start_str, end_str = arg_start, arg_end
    print(f"Explicit reprocess window: {start_str} -> {end_str}")
else:
    try:
        max_date = spark.sql(
            "select max(event_date) as m from silver.ais_clean"
        ).collect()[0]["m"]
    except Exception as e:  # table not created yet on the very first run
        print(f"silver.ais_clean not readable yet ({e}); starting from {START_DEFAULT}")
        max_date = None

    start = START_DEFAULT if max_date is None else max_date + timedelta(days=1)

    if start > END_DATE:
        print("All 2024 data already transformed — emitting no-op window.")
        start_str = end_str = SENTINEL
    else:
        end = min(start + timedelta(days=WINDOW_DAYS - 1), END_DATE)
        start_str, end_str = start.isoformat(), end.isoformat()
        print(f"Next dbt window: {start_str} -> {end_str}")

dbutils.jobs.taskValues.set(key="start_date", value=start_str)
dbutils.jobs.taskValues.set(key="end_date",   value=end_str)
