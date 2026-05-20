# Databricks notebook — schedule daily via Databricks Workflows
# Reads high-confidence anomalies from gold.vessel_risk_scores → sends email alert

import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

SCORE_THRESHOLD = 0.7   # only alert on high-confidence anomalies

# ── Load today's high-score anomalies ──────────────────────────────────────────
df = spark.sql(f"""
    select *
    from gold.vessel_risk_scores
    where is_outlier = true
      and anomaly_score >= {SCORE_THRESHOLD}
      and date(event_ts) = current_date() - interval 1 day
    order by anomaly_score desc
    limit 20
""").toPandas()

if df.empty:
    print("No high-confidence anomalies today — no alert sent.")
    raise SystemExit(0)

# ── Build recommended action per anomaly type ──────────────────────────────────
def recommend_action(row) -> str:
    if row.get("sanctions_match"):
        return "Flag for OFAC / EU reporting"
    if row["anomaly_type"] == "impossible_speed":
        return "Cross-reference with satellite imagery"
    if row["anomaly_type"] == "dark_gap":
        return "Alert port authority at next declared port of call"
    return "Flag for manual review"

# ── Build HTML email body ──────────────────────────────────────────────────────
def build_html(rows) -> str:
    table_rows = ""
    for _, r in rows.iterrows():
        match = f"⚠ {r['sanctions_match']}" if r.get("sanctions_match") else "—"
        action = recommend_action(r)
        table_rows += f"""
        <tr>
          <td><b>{r['VesselName']}</b><br><small>MMSI: {r['MMSI']}</small></td>
          <td>{r['anomaly_type'].replace('_', ' ').title()}</td>
          <td>{r['anomaly_score']:.2f}</td>
          <td>{match}</td>
          <td><i>{action}</i></td>
        </tr>"""

    return f"""
    <html><body style="font-family:sans-serif">
      <h2 style="color:#b30000">Maritime Anomaly Alert — {date.today()}</h2>
      <p>{len(rows)} high-confidence anomal{'y' if len(rows)==1 else 'ies'} detected (last 24 h).</p>
      <table border="1" cellpadding="6" style="border-collapse:collapse;font-size:14px">
        <tr style="background:#f0f0f0;font-weight:bold">
          <td>Vessel</td><td>Anomaly</td><td>Score</td>
          <td>Sanctions</td><td>Recommended action</td>
        </tr>
        {table_rows}
      </table>
    </body></html>
    """

# ── Send via Gmail SMTP ────────────────────────────────────────────────────────
sender   = os.environ["ALERT_EMAIL_FROM"]
password = os.environ["ALERT_EMAIL_PASSWORD"]
recipient = os.environ["ALERT_EMAIL_TO"]

msg = MIMEMultipart("alternative")
msg["Subject"] = f"[AIS Alert] {len(df)} maritime anomal{'y' if len(df)==1 else 'ies'} — {date.today()}"
msg["From"]    = sender
msg["To"]      = recipient
msg.attach(MIMEText(build_html(df), "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(sender, password)
    server.sendmail(sender, recipient, msg.as_string())

print(f"Alert sent to {recipient} — {len(df)} anomalies.")
