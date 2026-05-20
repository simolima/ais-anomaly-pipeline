# Setup Guide

## 1. Python virtual environment

Requires Python 3.11+. Check your version:

```bash
python3 --version
```

Create and activate the virtual environment:

```bash
# Create
python3 -m venv .venv

# Activate — macOS / Linux
source .venv/bin/activate

# Activate — Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Deactivate when done
deactivate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 2. Environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Where to find it |
|---|---|
| `DATABRICKS_HOST` | Databricks workspace URL (Settings → Workspace) |
| `DATABRICKS_TOKEN` | User Settings → Access tokens → Generate new token |
| `DATABRICKS_HTTP_PATH` | SQL Warehouses → your warehouse → Connection details |
| `OPENSANCTIONS_API_KEY` | opensanctions.org/api/ → free registration |
| `ALERT_EMAIL_FROM` | Gmail address you'll send alerts from |
| `ALERT_EMAIL_PASSWORD` | Gmail App Password (not your login password) |
| `ALERT_EMAIL_TO` | Address that receives the alerts |

Load variables in your shell:

```bash
source .env   # or: export $(cat .env | xargs)
```

---

## 3. dbt

Copy the profile template to the dbt home directory (outside the repo):

```bash
cp dbt/profiles.yml.example ~/.dbt/profiles.yml
```

The profile reads credentials from environment variables automatically — no hardcoded values.

Test the connection:

```bash
cd dbt
dbt debug
```

Run all models:

```bash
dbt run
```

Run a single layer:

```bash
dbt run --select silver
dbt run --select gold
```

---

## 4. Databricks Free Edition

1. Sign up at [databricks.com/try-databricks](https://www.databricks.com/try-databricks)  
   Choose **Azure** → **Free Edition**
2. Create a SQL Warehouse (Compute → SQL Warehouses → Create → 2X-Small)
3. Copy the HTTP path into `.env`
4. Upload the notebooks in `ingestion/` and `ml/` via the Databricks UI  
   (Workspace → Import → select the `.py` file)

---

## 5. Apache Superset (dashboard)

Requires Docker:

```bash
# Clone Superset
git clone https://github.com/apache/superset.git
cd superset

# Start with Docker Compose
docker compose up -d

# Open in browser
open http://localhost:8088
# Default login: admin / admin
```

Connect to Databricks:
1. Settings → Database Connections → + Database
2. Select **Databricks**
3. Paste your `DATABRICKS_HOST` and `DATABRICKS_HTTP_PATH`
4. Test connection → Save

---

## 6. Gmail App Password (for email alerts)

Regular Gmail password won't work with SMTP. You need an App Password:

1. Google Account → Security → 2-Step Verification (must be on)
2. Security → App passwords → Select app: Mail → Generate
3. Copy the 16-character password into `ALERT_EMAIL_PASSWORD` in `.env`
