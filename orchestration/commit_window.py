"""Advance the dbt window watermark — only after the dbt task has fully succeeded.

Runs as the last task of ais_dbt, depending on dbt_transform, so Databricks only starts it
when dbt_transform succeeded. It writes the processed window's end date to the state table
silver.dbt_window_state, which compute_window.py reads on the next run.

If dbt_transform fails, this task never runs, the watermark is not advanced, and the next
job reprocesses the same window (replace_where is idempotent) instead of skipping it.

Skips writing for explicit reprocess runs and the past-2024 no-op (advance != "true").
"""

from datetime import date

from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp
from pyspark.dbutils import DBUtils

spark   = SparkSession.builder.getOrCreate()
dbutils = DBUtils(spark)

STATE_TABLE = "silver.dbt_window_state"

advance = dbutils.jobs.taskValues.get(
    taskKey="compute_window", key="advance", default="false", debugValue="false")
end_str = dbutils.jobs.taskValues.get(
    taskKey="compute_window", key="end_date", default="", debugValue="")

if advance != "true" or not end_str:
    print(f"Watermark not advanced (advance={advance!r}, end={end_str!r}).")
    raise SystemExit(0)

spark.sql("CREATE DATABASE IF NOT EXISTS silver")

# Single-row state table, overwritten each successful window.
(
    spark.createDataFrame([(date.fromisoformat(end_str),)], "last_end date")
    .withColumn("_updated_at", current_timestamp())
    .write.format("delta").mode("overwrite").saveAsTable(STATE_TABLE)
)

print(f"Watermark advanced to {end_str}.")
