"""Per-vessel unsupervised risk scoring with an Isolation Forest.

Reads the per-vessel feature table (gold.vessel_features), fits an Isolation Forest on
the behavioural fingerprint of every vessel that tripped at least one rule, and writes a
continuous risk_score (0-1, higher = more anomalous) plus an is_outlier flag to
gold.vessel_risk_scores.

Scoring per vessel (not per event) is deliberate: the model's strength is isolating rare
*combinations* of behaviour (e.g. many moderate gaps + a position jump + sanctioned),
which a single threshold on anomaly_score would miss.
"""

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp

spark = SparkSession.builder.getOrCreate()

# Features fed to the model. total_anomalies is intentionally excluded (it is the sum of
# n_dark_gaps + n_impossible_speed, so including it would double-weight that dimension);
# it is kept in the output for reporting only.
FEATURES = [
    "n_dark_gaps",
    "avg_gap_hours",
    "max_gap_hours",
    "n_impossible_speed",
    "max_implied_speed",
    "max_jump_nm",
    "max_anomaly_score",
    "is_sanctioned",
]

df = spark.table("gold.vessel_features").toPandas()

if df.empty:
    print("gold.vessel_features is empty — no vessels to score. Nothing to do.")
    raise SystemExit(0)

X = df[FEATURES].fillna(0).astype(float)

# Defense-in-depth against heavy-tailed data-quality artefacts. gold.vessel_features already
# drops implausible impossible-speed events, but cap here too so a single residual extreme
# (a millions-of-knots implied speed from a near-zero dt, or a months-long coverage-edge
# "dark gap") can't dominate the standardized feature space and force the model to rank that
# one vessel as the sole outlier. Caps are physical sanity ceilings, not tuned thresholds.
CAPS = {
    "max_implied_speed": 90.0,    # kn — above this is a measurement error, not a vessel
    "max_jump_nm":       60.0,    # nm between consecutive pings
    "max_gap_hours":     720.0,   # 30 days — longer is a coverage gap, not AIS-dark
    "avg_gap_hours":     720.0,
}
for col, cap in CAPS.items():
    X[col] = X[col].clip(upper=cap)

scaler   = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
model.fit(X_scaled)

# score_samples: higher = more normal. Negate so higher = more anomalous, then min-max to
# 0-1 for an orderable risk score. predict() gives the hard ±1 outlier label.
raw   = -model.score_samples(X_scaled)
span  = raw.max() - raw.min()
df["risk_score"] = (raw - raw.min()) / span if span > 0 else 0.0
df["is_outlier"] = model.predict(X_scaled) == -1

spark.sql("CREATE DATABASE IF NOT EXISTS gold")

result = spark.createDataFrame(
    df[["mmsi", "vessel_name", *FEATURES, "total_anomalies", "risk_score", "is_outlier"]]
).withColumn("_scored_at", current_timestamp())

result.write.format("delta").mode("overwrite").saveAsTable("gold.vessel_risk_scores")

n_flagged = int(df["is_outlier"].sum())
print(f"Scored {len(df)} vessels — {n_flagged} flagged as outliers ({n_flagged/len(df):.1%})")

top = df.sort_values("risk_score", ascending=False).head(10)
print("Top 10 vessels by risk_score:")
print(top[["mmsi", "vessel_name", "risk_score",
           "total_anomalies", "is_sanctioned"]].to_string(index=False))
