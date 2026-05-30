import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp

spark = SparkSession.builder.getOrCreate()

df = spark.table("gold.ais_anomaly_cues").toPandas()

FEATURES = ["anomaly_score"]
X        = df[FEATURES].fillna(0)

scaler   = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
df["if_score"]   = model.fit_predict(X_scaled)
df["is_outlier"] = df["if_score"] == -1

spark.sql("CREATE DATABASE IF NOT EXISTS gold")

result = spark.createDataFrame(
    df[["mmsi", "vessel_name", "event_ts", "anomaly_type",
        "anomaly_score", "if_score", "is_outlier",
        "sanctions_match", "lat", "lon"]]
).withColumn("_scored_at", current_timestamp())

result.write.format("delta").mode("overwrite").saveAsTable("gold.vessel_risk_scores")

n_flagged = int(df["is_outlier"].sum())
print(f"Flagged {n_flagged} outliers out of {len(df)} anomaly events ({n_flagged/len(df):.1%})")
