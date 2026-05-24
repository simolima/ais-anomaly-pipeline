# Databricks notebook — run cell by cell
# Reads NOAA AIS GeoParquet from public Azure Blob → Bronze Delta table

import os
import requests
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit

spark = SparkSession.builder.getOrCreate()

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/"
TMP_DIR  = "/tmp/ais_staging"
TARGET   = "bronze.ais_raw"

# Adjust: which months to ingest (start small — 1-2 months, ~5 GB zipped)
MONTHS   = ["01", "02"]
DAYS     = range(1, 32)

os.makedirs(TMP_DIR, exist_ok=True)
spark.sql("CREATE DATABASE IF NOT EXISTS bronze")

# ── Ingestion loop ─────────────────────────────────────────────────────────────
import zipfile

for month in MONTHS:
    for day in DAYS:
        stem     = f"AIS_2024_{month}_{day:02d}"
        filename = stem + ".zip"
        url      = BASE_URL + filename
        dst_zip  = f"{TMP_DIR}/{filename}"
        dst_csv  = f"{TMP_DIR}/{stem}.csv"

        r = requests.get(url, timeout=300)
        if r.status_code != 200:
            print(f"skip  {filename} — {r.status_code}")
            continue

        with open(dst_zip, "wb") as f:
            f.write(r.content)

        with zipfile.ZipFile(dst_zip, "r") as z:
            csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
            z.extract(csv_name, TMP_DIR)
            extracted = f"{TMP_DIR}/{csv_name}"

        df = (
            spark.read.option("header", "true").option("inferSchema", "true").csv(extracted)
            .withColumn("_ingestion_ts",  current_timestamp())
            .withColumn("_source_file",   lit(filename))
        )

        df.write.format("delta").mode("append").saveAsTable(TARGET)
        os.remove(dst_zip)
        os.remove(extracted)
        print(f"ok    {filename} — {df.count():,} rows")

print(f"\nDone. Total rows in {TARGET}: {spark.table(TARGET).count():,}")
