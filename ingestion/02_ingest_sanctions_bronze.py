import os
import json
import requests
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp
from pyspark.sql.types import StructType, StructField, StringType

spark = SparkSession.builder.getOrCreate()

BULK_URL = "https://data.opensanctions.org/datasets/default/entities.ftm.json"
TARGET   = "bronze.sanctions"

spark.sql("CREATE DATABASE IF NOT EXISTS bronze")

print("Downloading OpenSanctions bulk data (vessels only)...")
vessel_rows = []

with requests.get(BULK_URL, stream=True, timeout=300) as r:
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        entity = json.loads(line)
        if entity.get("schema") != "Vessel":
            continue
        props = entity.get("properties", {})
        vessel_rows.append({
            "entity_id":        entity.get("id"),
            "entity_name":      props.get("name", [None])[0],
            "mmsi":             props.get("mmsi", [None])[0],
            "imo_number":       props.get("imoNumber", [None])[0],
            "flag":             props.get("flag", [None])[0],
            "sanctions_list":   ", ".join(entity.get("datasets", [])),
            "designation_date": props.get("startDate", [None])[0],
        })

print(f"Found {len(vessel_rows):,} sanctioned vessels.")

SCHEMA = StructType([
    StructField("entity_id",        StringType(), True),
    StructField("entity_name",      StringType(), True),
    StructField("mmsi",             StringType(), True),
    StructField("imo_number",       StringType(), True),
    StructField("flag",             StringType(), True),
    StructField("sanctions_list",   StringType(), True),
    StructField("designation_date", StringType(), True),
])

df = spark.createDataFrame(vessel_rows, schema=SCHEMA).withColumn("_ingestion_ts", current_timestamp())
df.write.format("delta").mode("overwrite").saveAsTable(TARGET)
print(f"Written to {TARGET}.")
