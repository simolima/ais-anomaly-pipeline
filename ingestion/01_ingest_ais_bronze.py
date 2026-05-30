import io
import sys
from datetime import date, timedelta

import pandas as pd
import requests
import zstandard
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit
from pyspark.sql.types import (
    StructType, StructField,
    StringType, TimestampType, DoubleType, IntegerType,
)

spark = SparkSession.builder.getOrCreate()

BASE_URL    = "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/"
TARGET      = "bronze.ais_raw"
END_DATE    = date(2024, 12, 31)
WINDOW_DAYS = 7
CHUNK       = 50_000
WRITE_EVERY = 10   # flush every 500k rows

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
}

spark.sql("CREATE DATABASE IF NOT EXISTS bronze")

# Determine start date from already-ingested files
try:
    ingested_files = {
        row._source_file
        for row in spark.table(TARGET).select("_source_file").distinct().collect()
    }
    dates_ingested = []
    for f in ingested_files:
        try:
            dates_ingested.append(date(int(f[4:8]), int(f[9:11]), int(f[12:14])))
        except (ValueError, IndexError):
            pass
    start_date = max(dates_ingested) + timedelta(days=1) if dates_ingested else date(2024, 1, 1)
except Exception:
    ingested_files = set()
    start_date = date(2024, 1, 1)

if start_date > END_DATE:
    print("All 2024 data already ingested. Nothing to do.")
    sys.exit(0)

end_date = min(start_date + timedelta(days=WINDOW_DAYS - 1), END_DATE)
print(f"Window: {start_date} -> {end_date}")

current = start_date
while current <= end_date:
    filename = f"ais-2024-{current.month:02d}-{current.day:02d}.csv.zst"

    if filename in ingested_files:
        print(f"skip  {filename} — already ingested")
        current += timedelta(days=1)
        continue

    url = BASE_URL + filename
    r   = requests.get(url, timeout=300, stream=True)
    if r.status_code != 200:
        print(f"skip  {filename} — HTTP {r.status_code}")
        current += timedelta(days=1)
        continue

    dctx       = zstandard.ZstdDecompressor()
    buffer     = []
    total_rows = 0

    def flush(buf):
        pdf = pd.concat(buf, ignore_index=True)
        (
            spark.createDataFrame(pdf, schema=AIS_SCHEMA)
            .withColumn("_ingestion_ts", current_timestamp())
            .withColumn("_source_file",  lit(filename))
            .write.format("delta").mode("append").saveAsTable(TARGET)
        )
        return len(pdf)

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
                total_rows += flush(buffer)
                buffer = []

    if buffer:
        total_rows += flush(buffer)

    print(f"ok    {filename} — {total_rows:,} rows")
    current += timedelta(days=1)

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
