# Databricks notebook — run after Gold layer is built
# Adds an Isolation Forest outlier score to gold.ais_anomaly_cues

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp

spark = SparkSession.builder.getOrCreate()

# ── Load Gold anomaly cues ─────────────────────────────────────────────────────
df = spark.table("gold.ais_anomaly_cues").toPandas()

FEATURES = ["anomaly_score"]          # extend with gap_hours, distance_nm etc. as built
X = df[FEATURES].fillna(0)

# ── Train Isolation Forest ─────────────────────────────────────────────────────
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = IsolationForest(
    n_estimators=200,
    contamination=0.05,   # assume ~5% of events are true anomalies
    random_state=42,
)
df["if_score"]    = model.fit_predict(X_scaled)   # -1 = outlier, 1 = normal
df["is_outlier"]  = df["if_score"] == -1

# ── Write scores back to Delta ─────────────────────────────────────────────────
spark.sql("CREATE DATABASE IF NOT EXISTS gold")

result = spark.createDataFrame(
    df[["MMSI", "VesselName", "event_ts", "anomaly_type",
        "anomaly_score", "if_score", "is_outlier",
        "sanctions_match", "lat", "lon"]]
).withColumn("_scored_at", current_timestamp())

result.write.format("delta").mode("overwrite").saveAsTable("gold.vessel_risk_scores")

n_flagged = df["is_outlier"].sum()
print(f"Flagged {n_flagged} outliers out of {len(df)} anomaly events ({n_flagged/len(df):.1%})")
