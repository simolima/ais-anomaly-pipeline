# ais-anomaly-pipeline

**Open-source pipeline for maritime AIS anomaly detection and sanctions evasion intelligence.**

---

## What this is

A reproducible data engineering and ML pipeline that detects suspicious vessel behavior in AIS (Automatic Identification System) data — dark gaps, impossible speeds, and GPS spoofing — and correlates findings with public sanctions lists.

Built on public data and open-source tooling. Data is ingested programmatically via public endpoints — no manual downloads, no proprietary APIs required.

---

## Why it exists

Commercial solutions (Windward, Kpler) solve this problem well but are closed-source and expensive. No open-source alternative integrates scalable cloud data engineering, anomaly detection ML, and sanctions correlation in a single reproducible stack.

This project fills that gap.

---

## The 3 anomalies detected

| Anomaly | Description | Method |
|---|---|---|
| **Dark Gap** | Vessel disappears for N+ consecutive hours | Rule-based + statistical threshold |
| **Impossible Speed** | Vessel reappears at a physically unreachable location | Distance / time vs. max vessel speed |
| **AIS Spoofing** | Transmitted coordinates inconsistent with vessel kinematics | Rule-based consistency checks |

---

## Architecture

```
SOURCES
  US Coast Guard AIS — public Azure Blob (GeoParquet) ─┐
  OpenSanctions — REST API (free, non-commercial) ──────┼──▶ Bronze (Delta Lake)
  IMO Ship Registry ───────────────────────────────────┘

PROCESSING (dbt + Databricks)
  Silver: cleaned trajectories + artifact removal (MMSI duplicates, retransmissions)
  Gold:   anomaly scores + vessel risk profiles

ML (MLflow on Databricks)
  1. Rule-based       — dark gap > 6h + anomalous reappearance
  2. Isolation Forest — unsupervised outlier scoring

DASHBOARD (Apache Superset)
  World map of anomalous vessels · Timeline of disappearances
  Risk score per vessel + OpenSanctions link · High-risk zone heatmap
```

---

## Stack

| Layer | Technology |
|---|---|
| Cloud platform | Azure Databricks (Free Edition) |
| Lakehouse / compute | Delta Lake (Bronze / Silver / Gold) |
| Transforms | dbt (dbt-databricks connector) |
| Orchestration | Azure Databricks Workflows |
| ML tracking | MLflow (managed, built into Databricks) |
| ML models | scikit-learn |
| Dashboard | Apache Superset (Databricks SQL connector) |
| Data | NOAA MarineCadastre AIS (CC0), OpenSanctions (public) |

---

## Data sources

| Source | License | Coverage |
|---|---|---|
| [NOAA MarineCadastre AIS](https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/) | CC0 — public domain | US coastal waters, 2009–2025 |
| [OpenSanctions](https://opensanctions.org) | CC BY 4.0 | Continuously updated |
| [IMO Ship Registry](https://gisis.imo.org) | Public (registration required) | Global |

See [`SOURCES.md`](SOURCES.md) for detailed download instructions and direct links.

---

## Getting started

```bash
git clone https://github.com/simolima/ais-anomaly-pipeline
cd ais-anomaly-pipeline

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env        # fill in your credentials
```

Full setup guide (Databricks, dbt, Superset, Gmail alerts): [`docs/setup.md`](docs/setup.md)

---

## References

- Park, Cho, Son — *Wide-Area GNSS Spoofing and Jamming Detection Using AIS* (arxiv:2603.11055, 2026)
- NATO STO — *Real-Time AIS Data Analysis for Anomaly Detection* (2024)
- Singh & Heymann (DLR) — *ML-Assisted Anomaly Detection Using AIS* (arxiv:2002.05013, 2020)
- Windward AI — *GPS Jamming Is Now a Mainstream Maritime Threat* (2025)
- Kpler — *AIS Spoofing: The Fast Track to Sanctions* (2025)

---

## License

MIT
