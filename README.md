# ais-anomaly-pipeline

**Open-source pipeline for maritime AIS anomaly detection and sanctions evasion intelligence.**

---

## What this is

A reproducible data engineering and ML pipeline that detects suspicious vessel behavior in AIS (Automatic Identification System) data — dark gaps, impossible speeds, and GPS spoofing — and correlates findings with public sanctions lists.

Built on public data. No proprietary APIs required.

---

## Why it exists

Commercial solutions (Windward, Kpler) solve this problem well but are closed-source and expensive. No open-source alternative integrates scalable data engineering, anomaly detection ML, and sanctions correlation in a single reproducible stack.

This project fills that gap.

---

## The 3 anomalies detected

| Anomaly | Description | Method |
|---|---|---|
| **Dark Gap** | Vessel disappears for N+ consecutive hours | Rule-based + statistical threshold |
| **Impossible Speed** | Vessel reappears at a physically unreachable location | Distance / time vs. max vessel speed |
| **AIS Spoofing** | Transmitted coordinates inconsistent with vessel kinematics | IMM Kalman Filter + ST-DBSCAN |

---

## Architecture

```
SOURCES
  US Coast Guard AIS (NOAA/MarineCadastre) ─┐
  OpenSanctions ─────────────────────────────┼──▶ Bronze (raw Delta Lake)
  IMO Ship Registry ─────────────────────────┘

PROCESSING (dbt)
  Silver: cleaned trajectories + artifact removal (MMSI duplicates, retransmissions)
  Gold:   anomaly scores + vessel risk profiles

ML (MLflow)
  1. Rule-based   — dark gap > 6h + anomalous reappearance
  2. Isolation Forest — unsupervised baseline
  3. IMM Kalman Filter + ST-DBSCAN — spoofing / jamming

DASHBOARD
  World map of anomalous vessels · Timeline of disappearances
  Risk score per vessel + OpenSanctions link · High-risk zone heatmap
```

---

## Stack

| Layer | Technology |
|---|---|
| Storage | Delta Lake (Bronze / Silver / Gold) |
| Transforms | dbt |
| ML | scikit-learn, MLflow |
| Dashboard | Streamlit or Evidence |
| Orchestration | Apache Airflow (planned) |

---

## Data sources

| Source | License | Coverage |
|---|---|---|
| [NOAA MarineCadastre AIS](https://marinecadastre.gov/downloads/data/ais/) | CC0 — public domain | US coastal waters, 2009–2024 |
| [OpenSanctions](https://opensanctions.org) | Public | Continuously updated |
| [IMO GISIS Ship Registry](https://gisis.imo.org) | Public lookup | Global |

See [`SOURCES.md`](SOURCES.md) for detailed download instructions and direct links.

---

## Getting started

```bash
git clone https://github.com/simolima/ais-anomaly-pipeline
cd ais-anomaly-pipeline
pip install -r requirements.txt
```

Full setup guide in [`docs/setup.md`](docs/setup.md) — coming soon.

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
