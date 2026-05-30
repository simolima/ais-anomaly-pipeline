import os
import zstandard
import requests
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit
from pyspark.sql.types import (
    StructType, StructField,
    StringType, TimestampType, DoubleType, IntegerType,
)

spark = SparkSession.builder.getOrCreate()

BASE_URL = "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/"
TMP_DIR  = "/tmp/ais_staging"
TARGET   = "bronze.ais_raw"
MONTHS   = ["01"]
DAYS     = range(1, 32)

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

import os as _os
_os.makedirs(TMP_DIR, exist_ok=True)
spark.sql("CREATE DATABASE IF NOT EXISTS bronze")

for month in MONTHS:
    for day in DAYS:
        filename = f"ais-2024-{month}-{day:02d}.csv.zst"
        url      = BASE_URL + filename
        dst_zst  = f"{TMP_DIR}/{filename}"
        dst_csv  = dst_zst[:-4]

        r = requests.get(url, timeout=300)
        if r.status_code != 200:
            print(f"skip  {filename} — {r.status_code}")
            continue

        with open(dst_zst, "wb") as f:
            f.write(r.content)

        dctx = zstandard.ZstdDecompressor()
        with open(dst_zst, "rb") as src, open(dst_csv, "wb") as dst:
            dctx.copy_stream(src, dst)

        df = (
            spark.read
            .option("header", "true")
            .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
            .schema(AIS_SCHEMA)
            .csv(f"file://{dst_csv}")
            .withColumn("_ingestion_ts", current_timestamp())
            .withColumn("_source_file",  lit(filename))
        )

        df.write.format("delta").mode("append").saveAsTable(TARGET)
        os.remove(dst_zst)
        os.remove(dst_csv)
        print(f"ok    {filename} — {df.count():,} rows")

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
