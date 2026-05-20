# Data Sources

All data used in this pipeline is publicly available and free to download. No API keys or paid subscriptions required.

---

## 1. NOAA MarineCadastre — US Coast Guard AIS

**The primary dataset.**

| Field | Value |
|---|---|
| URL | https://marinecadastre.gov/downloads/data/ais/ |
| License | CC0 — Public Domain |
| Format | GeoParquet / CSV (zipped) |
| Coverage | US coastal waters, 2009–2024 |
| Volume | ~820M messages per area |
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

**Download tips:**
- Start with 1–2 months for a single UTM zone to keep volume manageable (~2–5 GB compressed)
- High-interest areas: Zone 19 (US East Coast), Zone 10 (US West Coast)
- Files are named by year, month, and UTM zone: `AIS_2024_01_Zone19.zip`

**Direct download index:** https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/index.html

---

## 2. OpenSanctions

**For sanctions correlation — joins with MMSI / IMO to flag sanctioned vessels and owners.**

| Field | Value |
|---|---|
| URL | https://opensanctions.org |
| Bulk data | https://data.opensanctions.org/datasets/default/entities.ftm.json |
| License | CC BY 4.0 (attribution required) |
| Format | JSON (FollowTheMoney schema) / CSV |
| Coverage | OFAC, EU, UN, UK OFSI, and 40+ other lists |
| Update frequency | Daily |

**Relevant entity types for this pipeline:**
- `Vessel` — sanctioned ships (filter by `schema: Vessel`)
- `Company` — sanctioned companies that may own vessels
- `Person` — sanctioned individuals linked to vessel ownership

**Simple filtered download (vessels only):**
```bash
curl -L "https://data.opensanctions.org/datasets/default/entities.ftm.json" \
  | jq 'select(.schema == "Vessel")' > sanctioned_vessels.jsonl
```

**Alternative — pre-filtered CSVs:** https://www.opensanctions.org/docs/bulk/

---

## 3. IMO GISIS — Global Integrated Shipping Information System

**For vessel identity enrichment — cross-reference MMSI with IMO numbers, flag state, and owner.**

| Field | Value |
|---|---|
| URL | https://gisis.imo.org/Public/Ships/Default.aspx |
| License | Public lookup — no bulk download available |
| Format | Web lookup / manual export |
| Coverage | Global |

**Alternative bulk source — ITU MARS database:**
- URL: https://www.itu.int/en/ITU-R/terrestrial/mars/Pages/default.aspx
- Contains MMSI-to-vessel-name mappings (official ITU registry)

**Practical note:** For bulk MMSI resolution, the community-maintained dataset at https://www.mmsispace.com or the `aisdb` Python package (https://github.com/AISViz/AISdb) are more usable than GISIS for automated pipelines.

---

## 4. Supporting / Optional Sources

### Synthetic spoofing dataset (for model testing)
- **Agrebi — Synthetic GPS Spoofing Dataset for MASS** (IEEE DataPort, 2025)
- URL: https://ieee-dataport.org (search "GPS spoofing AIS MASS Agrebi")
- Useful for testing the IMM Kalman Filter without waiting for confirmed real-world spoofing events

### Global AIS via AISHub (near-real-time)
- URL: https://www.aishub.net
- Free for non-commercial use with registration
- Useful for live validation once the batch pipeline is stable

### VesselFinder historical data (paid)
- URL: https://www.vesselfinder.com/historical-ais-data
- Commercial — not required for this project but useful reference for validation

---

## Download Checklist for v1

- [ ] 2 months of NOAA AIS for Zone 19 (US East Coast) — ~4 GB
- [ ] OpenSanctions bulk export (vessels) — ~50 MB
- [ ] ITU MARS MMSI registry — ~10 MB
- [ ] Place all raw files under `data/raw/` before running the ingestion pipeline
