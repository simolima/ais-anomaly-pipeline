import math
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pyspark.sql import SparkSession
from pyspark.dbutils import DBUtils

spark   = SparkSession.builder.getOrCreate()
dbutils = DBUtils(spark)

SCORE_THRESHOLD = 0.7


def _f(v):
    try:
        return f"{float(v):.4f}" if v is not None and not math.isnan(float(v)) else "—"
    except (TypeError, ValueError):
        return "—"


def _v(v):
    return str(v) if v else "—"


outliers = spark.sql(f"""
    SELECT mmsi, vessel_name, event_ts, anomaly_type, anomaly_score, sanctions_match, lat, lon
    FROM gold.vessel_risk_scores
    WHERE is_outlier = true AND anomaly_score >= {SCORE_THRESHOLD}
    ORDER BY anomaly_score DESC
    LIMIT 50
""").toPandas()

if outliers.empty:
    print("No outliers above threshold — no alert sent.")
    raise SystemExit(0)

dark_gaps = spark.sql("""
    SELECT mmsi, gap_start, gap_hours,
           last_known_lat, last_known_lon,
           reappearance_lat, reappearance_lon
    FROM gold.ais_dark_gaps
""").toPandas()

df = outliers.merge(dark_gaps, left_on=["mmsi", "event_ts"],
                    right_on=["mmsi", "gap_start"], how="left")


def calc_distance(row):
    if row["anomaly_type"] == "dark_gap":
        try:
            R = 3440.065
            lat1, lon1 = float(row["last_known_lat"]), float(row["last_known_lon"])
            lat2, lon2 = float(row["reappearance_lat"]), float(row["reappearance_lon"])
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return round(R * 2 * math.asin(math.sqrt(a)), 1)
        except (TypeError, ValueError):
            pass
    return None


df["distance_nm"] = df.apply(calc_distance, axis=1)

rows_html = ""
for _, r in df.iterrows():
    sanctions = (f'<td style="color:#b30000;font-weight:bold">{r["sanctions_match"]}</td>'
                 if r.get("sanctions_match") else "<td>—</td>")
    if r["anomaly_type"] == "dark_gap":
        disappeared = f"{_f(r.get('last_known_lat'))}°N  {_f(r.get('last_known_lon'))}°E"
        reappeared  = f"{_f(r.get('reappearance_lat'))}°N  {_f(r.get('reappearance_lon'))}°E"
        movement    = f"{_v(r.get('gap_hours'))} h gap · {_v(r.get('distance_nm'))} nm"
    else:
        disappeared = f"{_f(r.get('lat'))}°N  {_f(r.get('lon'))}°E"
        reappeared  = "—"
        movement    = "impossible speed"

    rows_html += f"""
    <tr>
      <td>{_v(r['vessel_name'])}</td><td>{r['mmsi']}</td>
      <td>{r['anomaly_type'].replace('_', ' ')}</td>
      <td>{disappeared}</td><td>{reappeared}</td>
      <td>{movement}</td><td>{r['anomaly_score']:.2f}</td>
      {sanctions}
    </tr>"""

html = f"""<html><body style="font-family:sans-serif;max-width:960px;margin:auto">
  <h2 style="color:#1a1a2e">AIS Anomaly Report — {date.today()}</h2>
  <p style="color:#555">{len(df)} vessel{'s' if len(df) != 1 else ''} flagged &middot; score &ge; {SCORE_THRESHOLD}</p>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px">
    <thead style="background:#1a1a2e;color:white">
      <tr><th>Vessel</th><th>MMSI</th><th>Anomaly</th>
      <th>Disappeared at</th><th>Reappeared at</th>
      <th>Movement</th><th>Score</th><th>Sanctions</th></tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="color:#aaa;font-size:11px;margin-top:20px">AIS Anomaly Pipeline · {date.today()}</p>
</body></html>"""

plain = "\n".join(
    f"{r['vessel_name']} | {r['mmsi']} | {r['anomaly_type']} | score {r['anomaly_score']:.2f}"
    for _, r in df.iterrows()
)

_config = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "../config/alert_recipients.csv")
with open(_config) as f:
    recipients = [l.strip() for l in f if l.strip() and l.strip() != "email"]

sender   = dbutils.secrets.get("ais_secrets", "ALERT_EMAIL_FROM")
password = dbutils.secrets.get("ais_secrets", "ALERT_EMAIL_PASSWORD")

msg = MIMEMultipart("alternative")
msg["Subject"] = f"[AIS Alert] {len(df)} anomal{'y' if len(df) == 1 else 'ies'} — {date.today()}"
msg["From"]    = sender
msg["To"]      = ", ".join(recipients)
msg.attach(MIMEText(plain, "plain"))
msg.attach(MIMEText(html, "html"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(sender, password)
    server.sendmail(sender, recipients, msg.as_string())

print(f"Alert sent to {recipients} — {len(df)} anomalies.")
