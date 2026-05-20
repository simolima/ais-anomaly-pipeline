# Databricks notebook — run cell by cell
# Reads NOAA AIS GeoParquet from public Azure Blob → Bronze Delta table

import os
import requests
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit

spark = SparkSession.builder.getOrCreate()

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/"
TMP_DIR  = "/tmp/ais_staging"
TARGET   = "bronze.ais_raw"

# Adjust: which months to ingest (start small — 1-2 months, ~2 GB)
MONTHS   = ["01", "02"]
DAYS     = range(1, 32)

os.makedirs(TMP_DIR, exist_ok=True)
spark.sql("CREATE DATABASE IF NOT EXISTS bronze")

# ── Ingestion loop ─────────────────────────────────────────────────────────────
for month in MONTHS:
    for day in DAYS:
        filename = f"AIS_2024_{month}_{day:02d}.parquet"
        url      = BASE_URL + filename
        dst      = f"{TMP_DIR}/{filename}"

        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            print(f"skip  {filename} — {r.status_code}")
            continue

        with open(dst, "wb") as f:
            f.write(r.content)

        df = (
            spark.read.parquet(dst)
            .withColumn("_ingestion_ts",  current_timestamp())
            .withColumn("_source_file",   lit(filename))
        )

        df.write.format("delta").mode("append").saveAsTable(TARGET)
        os.remove(dst)
        print(f"ok    {filename} — {df.count():,} rows")

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
