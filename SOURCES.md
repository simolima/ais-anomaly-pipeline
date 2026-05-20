# Data Sources

All data is ingested programmatically — no manual downloads required.

---

## 1. NOAA MarineCadastre — US Coast Guard AIS

**The primary dataset. Public Azure Blob Storage, no authentication required.**

| Field | Value |
|---|---|
| Daily GeoParquet (2024) | `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/` |
| Monthly vessel tracks (2024–2025) | `https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/aistrack/` |
| Bulk index (all years, CSV) | https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/index.html |
| Interactive clip tool | https://marinecadastre.gov/accessais/ |
| License | CC0 — Public Domain |
| Format | GeoParquet (preferred) or CSV |
| Coverage | US coastal waters, 2009–2025 |

**Programmatic download (Python):**

```python
import requests

# Example: first day of January 2024
url = "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/AIS_2024_01_01.parquet"
r = requests.get(url)
with open("AIS_2024_01_01.parquet", "wb") as f:
    f.write(r.content)
```

**Or directly into a Databricks notebook:**

```python
df = spark.read.parquet(
    "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais2024/AIS_2024_01_01.parquet"
)
df.write.format("delta").mode("append").save("/mnt/bronze/ais_raw")
```

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

Official data dictionary: https://coast.noaa.gov/data/marinecadastre/ais/data-dictionary.pdf

---

## 2. OpenSanctions

**For sanctions correlation — REST API, free for non-commercial and academic use.**

| Field | Value |
|---|---|
| Homepage | https://opensanctions.org |
| API docs | https://www.opensanctions.org/docs/api/ |
| Bulk data docs | https://www.opensanctions.org/docs/bulk/ |
| License | CC BY 4.0 (free for non-commercial / academic) |
| API key | Free — register at https://www.opensanctions.org/api/ |
| Update frequency | Daily |

**API — match a vessel by name or IMO:**

```python
import requests

headers = {"Authorization": "ApiKey YOUR_FREE_KEY"}

# Search for a vessel by name
r = requests.get(
    "https://api.opensanctions.org/search/default",
    params={"q": "VESSEL_NAME", "schema": "Vessel"},
    headers=headers
)
results = r.json()["results"]
```

**Bulk download (no API key needed) — filter for vessels:**

```python
import requests, json

url = "https://data.opensanctions.org/datasets/default/entities.ftm.json"
with requests.get(url, stream=True) as r:
    for line in r.iter_lines():
        entity = json.loads(line)
        if entity.get("schema") == "Vessel":
            # process sanctioned vessel
            pass
```

**Load directly into Databricks:**

```python
# Parquet endpoint (check opensanctions.org/docs/bulk/ for latest URL)
df = spark.read.parquet("https://data.opensanctions.org/datasets/default/vessels.parquet")
df.write.format("delta").mode("overwrite").save("/mnt/bronze/sanctions")
```

---

## 3. IMO Ship Registry (GISIS)

**For cross-referencing MMSI with official IMO numbers and flag state.**

| Field | Value |
|---|---|
| URL | https://gisis.imo.org |
| License | Free with registration |
| Format | Web lookup only — no bulk API |

**Practical alternative — AISdb (Python):**

```bash
pip install aisdb
```

The `aisdb` package includes MMSI-to-vessel metadata resolution utilities that work without GISIS access. See https://github.com/AISViz/AISdb.

---

## Ingestion checklist for v1

- [ ] Run ingestion script: pulls 2 months of GeoParquet from NOAA blob → Bronze Delta table
- [ ] Run OpenSanctions sync: API or bulk download → Bronze Delta table
- [ ] Verify row counts and schema in Databricks notebook before running Silver transforms
