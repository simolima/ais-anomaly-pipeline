import io
import sys
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import requests
import zstandard
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit
from pyspark.sql.types import (
    StructType, StructField,
    StringType, TimestampType, DoubleType, IntegerType,
)


def _parse_date(filename: str) -> Optional[date]:
    try:
        return date(int(filename[4:8]), int(filename[9:11]), int(filename[12:14]))
    except (ValueError, IndexError):
        return None


def _compute_window(
    ingested_files: set,
    window_days: int,
    end_date: date,
    default_start: date = date(2024, 1, 1),
) -> Optional[tuple]:
    dates = [d for f in ingested_files if (d := _parse_date(f)) is not None]
    start = max(dates) + timedelta(days=1) if dates else default_start
    if start > end_date:
        return None
    return start, min(start + timedelta(days=window_days - 1), end_date)


def _flush(spark, buf, filename, schema, target):
    pdf = pd.concat(buf, ignore_index=True)
    (
        spark.createDataFrame(pdf, schema=schema)
        .withColumn("_ingestion_ts", current_timestamp())
        .withColumn("_source_file",  lit(filename))
        .write.format("delta").mode("append").saveAsTable(target)
    )
    return len(pdf)


spark = SparkSession.builder.getOrCreate()

BASE_URL    = "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/"
TARGET      = "bronze.ais_raw"
END_DATE    = date(2024, 12, 31)
WINDOW_DAYS = 7
CHUNK       = 50_000
WRITE_EVERY = 50   # flush every 2.5M rows (~20 Delta commits per 7-day run)

AIS_SCHEMA = StructType([
    StructField("mmsi",          StringType(),    True),
    StructField("base_date_time",TimestampType(), True),
    StructField("longitude",     DoubleType(),    True),
    StructField("latitude",      DoubleType(),    True),
    StructField("sog",           DoubleType(),    True),
    StructField("cog",           DoubleType(),    True),
    StructField("heading",       IntegerType(),   True),
    StructField("vessel_name",   StringType(),    True),
    StructField("imo",           StringType(),    True),
    StructField("call_sign",     StringType(),    True),
    StructField("vessel_type",   IntegerType(),   True),
    StructField("status",        IntegerType(),   True),
    StructField("length",        IntegerType(),   True),
    StructField("width",         IntegerType(),   True),
    StructField("draft",         DoubleType(),    True),
    StructField("cargo",         IntegerType(),   True),
    StructField("transceiver",   StringType(),    True),
])

DTYPES = {
    "mmsi": str, "vessel_name": str, "imo": str,
    "call_sign": str, "transceiver": str,
    "heading": "Int32", "vessel_type": "Int32", "status": "Int32",
    "length": "Int32", "width": "Int32", "cargo": "Int32",
}

spark.sql("CREATE DATABASE IF NOT EXISTS bronze")

try:
    ingested_files = {
        row._source_file
        for row in spark.table(TARGET).select("_source_file").distinct().collect()
    }
except Exception as e:
    print(f"Could not read ingested files (table may not exist yet): {e}")
    ingested_files = set()

window = _compute_window(ingested_files, WINDOW_DAYS, END_DATE)
if window is None:
    print("All 2024 data already ingested. Nothing to do.")
    sys.exit(0)

start_date, end_date = window
print(f"Window: {start_date} -> {end_date}")

current = start_date
while current <= end_date:
    filename = f"ais-2024-{current.month:02d}-{current.day:02d}.csv.zst"

    buffer     = []
    total_rows = 0

    with requests.get(BASE_URL + filename, timeout=300, stream=True) as r:
        if r.status_code != 200:
            print(f"skip  {filename} — HTTP {r.status_code}")
            current += timedelta(days=1)
            continue

        # Delete only after confirming the source file is available
        if filename in ingested_files:
            spark.sql(f"DELETE FROM {TARGET} WHERE _source_file = '{filename}'")

        dctx = zstandard.ZstdDecompressor()
        with dctx.stream_reader(r.raw) as zst_stream:
            text_stream = io.TextIOWrapper(zst_stream, encoding="utf-8")
            for i, chunk in enumerate(pd.read_csv(
                text_stream,
                chunksize=CHUNK,
                dtype=DTYPES,
            ), start=1):
                chunk["base_date_time"] = pd.to_datetime(
                    chunk["base_date_time"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
                )
                buffer.append(chunk)
                if i % WRITE_EVERY == 0:
                    total_rows += _flush(spark, buffer, filename, AIS_SCHEMA, TARGET)
                    buffer = []

    if buffer:
        total_rows += _flush(spark, buffer, filename, AIS_SCHEMA, TARGET)

    print(f"ok    {filename} — {total_rows:,} rows")
    current += timedelta(days=1)

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
