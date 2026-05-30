import io

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

BASE_URL = "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/"
TARGET   = "bronze.ais_raw"
MONTHS   = ["01"]
DAYS     = range(1, 32)
CHUNK        = 50_000
WRITE_EVERY  = 10        # scrivi su Delta ogni 10 chunk (= 500k righe)

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

for month in MONTHS:
    for day in DAYS:
        filename = f"ais-2024-{month}-{day:02d}.csv.zst"
        url      = BASE_URL + filename

        r = requests.get(url, timeout=300, stream=True)
        if r.status_code != 200:
            print(f"skip  {filename} — {r.status_code}")
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

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
