"""Vessel-centric anomaly alert.

Reads the per-vessel risk scores (gold.vessel_risk_scores), takes the top-N vessels by
risk_score above a threshold, and emails an HTML summary of their behaviour. No per-event
drill-down — the alert answers "which vessels should an analyst look at first".
"""

import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pyspark.sql import SparkSession
from pyspark.dbutils import DBUtils

spark   = SparkSession.builder.getOrCreate()
dbutils = DBUtils(spark)

RISK_THRESHOLD = 0.7   # only alert on vessels at/above this risk_score
TOP_N          = 20


def _i(v):
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "—"


def _f(v, nd=1):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


vessels = spark.sql(f"""
    SELECT mmsi, vessel_name, risk_score,
           n_dark_gaps, max_gap_hours,
           n_impossible_speed, max_implied_speed,
           total_anomalies, is_sanctioned
    FROM gold.vessel_risk_scores
    WHERE is_outlier = true AND risk_score >= {RISK_THRESHOLD}
    ORDER BY risk_score DESC
    LIMIT {TOP_N}
""").toPandas()

if vessels.empty:
    print("No vessels above risk threshold — no alert sent.")
    raise SystemExit(0)

rows_html = ""
for _, r in vessels.iterrows():
    sanctioned = ('<td style="color:#b30000;font-weight:bold">SANCTIONED</td>'
                  if int(r["is_sanctioned"]) == 1 else "<td>—</td>")
    rows_html += f"""
    <tr>
      <td>{r['vessel_name'] or '—'}</td><td>{r['mmsi']}</td>
      <td style="font-weight:bold">{_f(r['risk_score'], 3)}</td>
      <td>{_i(r['n_dark_gaps'])} · max {_f(r['max_gap_hours'])} h</td>
      <td>{_i(r['n_impossible_speed'])} · max {_f(r['max_implied_speed'])} kn</td>
      <td>{_i(r['total_anomalies'])}</td>
      {sanctioned}
    </tr>"""

html = f"""<html><body style="font-family:sans-serif;max-width:960px;margin:auto">
  <h2 style="color:#1a1a2e">AIS Vessel Risk Report — {date.today()}</h2>
  <p style="color:#555">Top {len(vessels)} vessel{'s' if len(vessels) != 1 else ''} by risk score &middot; risk &ge; {RISK_THRESHOLD}</p>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
    <thead style="background:#1a1a2e;color:white">
      <tr><th>Vessel</th><th>MMSI</th><th>Risk</th>
      <th>Dark gaps</th><th>Speed jumps</th><th>Total anomalies</th><th>Sanctions</th></tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="color:#aaa;font-size:11px;margin-top:20px">AIS Anomaly Pipeline · {date.today()}</p>
</body></html>"""

plain = "\n".join(
    f"{r['vessel_name'] or '—'} | {r['mmsi']} | risk {float(r['risk_score']):.3f} | "
    f"{int(r['total_anomalies'])} anomalies"
    + (" | SANCTIONED" if int(r["is_sanctioned"]) == 1 else "")
    for _, r in vessels.iterrows()
)

# Recipients, sender and password come from the Databricks secret scope — no local file.
# (The previous config/alert_recipients.csv was read via __file__, which is undefined in
#  the Databricks exec context. ALERT_RECIPIENTS is a comma-separated list.)
recipients = [a.strip() for a in
              dbutils.secrets.get("ais_secrets", "ALERT_RECIPIENTS").split(",") if a.strip()]
sender     = dbutils.secrets.get("ais_secrets", "ALERT_EMAIL_FROM")
password   = dbutils.secrets.get("ais_secrets", "ALERT_EMAIL_PASSWORD")

msg = MIMEMultipart("alternative")
msg["Subject"] = f"[AIS Alert] {len(vessels)} high-risk vessel{'s' if len(vessels) != 1 else ''} — {date.today()}"
msg["From"]    = sender
msg["To"]      = ", ".join(recipients)
msg.attach(MIMEText(plain, "plain"))
msg.attach(MIMEText(html, "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(sender, password)
    server.sendmail(sender, recipients, msg.as_string())

print(f"Alert sent to {recipients} — {len(vessels)} vessels.")
