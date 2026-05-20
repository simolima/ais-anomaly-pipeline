# Data Sources

All data used in this pipeline is publicly available and free to download. No API keys or paid subscriptions required.

---

## 1. NOAA MarineCadastre — US Coast Guard AIS

**The primary dataset.**

| Field | Value |
|---|---|
| Interactive tool | https://marinecadastre.gov/accessais/ |
| Direct file index (2024) | https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/index.html |
| Direct file index (2023) | https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/index.html |
| License | CC0 — Public Domain |
| Format | CSV (zipped, one file per day) |
| Coverage | US coastal waters, 2009–2024 |
| Total size (2024) | ~116.7 GB uncompressed |
| Update frequency | Annual |

**Schema — key columns:**

| Column | Description |
|---|---|
| `MMSI` | Maritime Mobile Service Identity — vessel identifier |
| `BaseDateTime` | UTC timestamp of the AIS broadcast |
| `LAT` | Latitude (decimal degrees) |
| `LON` | Longitude (decimal degrees) |
| `SOG` | Speed Over Ground (knots) |
| `COG` | Course Over Ground (degrees) |
| `Heading` | True heading (degrees) |
| `VesselName` | Self-reported vessel name |
| `IMO` | IMO ship number (when available) |
| `CallSign` | Radio call sign |
| `VesselType` | Numeric vessel type code |
| `Status` | Navigational status |
| `Length` | Vessel length (meters) |
| `Width` | Vessel beam (meters) |
| `Draft` | Vessel draft (meters) |
| `Cargo` | Cargo type code |

Data dictionary (official): https://coast.noaa.gov/data/marinecadastre/ais/data-dictionary.pdf

**Download tips:**
- **Interactive (recommended for small areas):** Use the [AccessAIS tool](https://marinecadastre.gov/accessais/) to clip by geography and time range — avoids downloading the full daily files
- **Direct bulk download:** Files follow the pattern `AIS_2024_MM_DD.zip` from the index pages above
- Start with 1–2 months for a single coastal zone to keep volume manageable (~2–5 GB compressed)
- Note: direct download links from the tool expire after 5 accesses or 14 days

---

## 2. OpenSanctions

**For sanctions correlation — joins with MMSI / IMO to flag sanctioned vessels and owners.**

| Field | Value |
|---|---|
| Homepage | https://opensanctions.org |
| Bulk data docs | https://www.opensanctions.org/docs/bulk/ |
| License | CC BY 4.0 (attribution required; non-commercial free) |
| Format | JSON (FollowTheMoney schema), CSV, Parquet |
| Coverage | OFAC, EU, UN, UK OFSI, and 40+ other lists |
| Update frequency | Daily |
| Total entities | 2.1M+ across 333 sources |

**Relevant entity types for this pipeline:**
- `Vessel` — sanctioned ships
- `Company` — sanctioned companies that may own vessels
- `Person` — sanctioned individuals linked to vessel ownership

**Download (vessels filtered):**
```bash
# Full default dataset (2.1M entities, ~1 GB)
curl -L "https://data.opensanctions.org/datasets/default/entities.ftm.json" \
  -o opensanctions_default.jsonl

# Filter vessels locally
grep '"schema":"Vessel"' opensanctions_default.jsonl > sanctioned_vessels.jsonl
```

**Parquet alternative (easier for Databricks):**
Check https://www.opensanctions.org/docs/bulk/ for the latest Parquet/CSV endpoints — these load directly into a Databricks table with `spark.read.parquet(...)`.

---

## 3. IMO GISIS — Global Integrated Shipping Information System

**For vessel identity enrichment — cross-reference MMSI with IMO numbers, flag state, and owner.**

| Field | Value |
|---|---|
| URL | https://gisis.imo.org |
| License | Public (free registration required) |
| Format | Web lookup only — no bulk download |
| Coverage | Global |

**Note:** GISIS now requires account registration even for basic vessel lookups. For automated bulk MMSI resolution, the alternatives below are more practical.

**Practical alternative — ITU MARS (List V):**
- URL: https://www.itu.int/en/ITU-R/terrestrial/mars/Pages/default.aspx
- Contains official MMSI assignments from national administrations (~1M ship stations)
- Online search only; bulk export requires ITU membership or data agreement

**Community alternative — AISdb:**
- Python package: https://github.com/AISViz/AISdb
- Includes MMSI-to-vessel metadata resolution utilities

---

## 4. Supporting / Optional Sources

### Synthetic spoofing dataset (for model testing without waiting for confirmed real events)
- **Agrebi — Synthetic GPS Spoofing Dataset for MASS** (IEEE DataPort, 2025)
- Search "GPS spoofing AIS MASS Agrebi" on https://ieee-dataport.org
- Useful for testing the IMM Kalman Filter against known spoofing patterns

### AISHub — near-real-time global AIS feed
- URL: https://www.aishub.net
- Free for non-commercial use with registration
- Useful for live validation once the batch pipeline is stable

---

## Download Checklist for v1

- [ ] AIS data: 2 months via [AccessAIS](https://marinecadastre.gov/accessais/) for a specific coastal zone (~4 GB)
- [ ] OpenSanctions bulk export (vessels filtered) — ~50 MB
- [ ] Place all raw files under `data/raw/` before running the ingestion pipeline
- [ ] Upload to Azure Data Lake Storage Gen2 (`abfss://raw@<storage-account>.dfs.core.windows.net/ais/`)
