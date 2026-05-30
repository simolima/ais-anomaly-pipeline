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
CHUNK    = 50_000

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

RENAME = {
    "MMSI": "mmsi", "BaseDateTime": "base_date_time",
    "LAT": "longitude", "LON": "latitude",
    "SOG": "sog", "COG": "cog", "Heading": "heading",
    "VesselName": "vessel_name", "IMO": "imo", "CallSign": "call_sign",
    "VesselType": "vessel_type", "Status": "status",
    "Length": "length", "Width": "width", "Draft": "draft",
    "Cargo": "cargo", "TransceiverClass": "transceiver",
}

DTYPES = {
    "MMSI": str, "VesselName": str, "IMO": str,
    "CallSign": str, "TransceiverClass": str,
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
        total_rows = 0

        with dctx.stream_reader(r.raw) as zst_stream:
            text_stream = io.TextIOWrapper(zst_stream, encoding="utf-8")
            for chunk in pd.read_csv(
                text_stream,
                chunksize=CHUNK,
                dtype=DTYPES,
            ):
                chunk["BaseDateTime"] = pd.to_datetime(
                    chunk["BaseDateTime"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
                )
                chunk = chunk.rename(columns=RENAME)
                df = (
                    spark.createDataFrame(chunk, schema=AIS_SCHEMA)
                    .withColumn("_ingestion_ts", current_timestamp())
                    .withColumn("_source_file",  lit(filename))
                )
                df.write.format("delta").mode("append").saveAsTable(TARGET)
                total_rows += len(chunk)

        print(f"ok    {filename} — {total_rows:,} rows")

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
