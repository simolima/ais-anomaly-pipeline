# Data Sources

All data is ingested programmatically — no manual downloads required.

---

## 1. NOAA MarineCadastre — US Coast Guard AIS

**The primary dataset. Public Azure Blob Storage, no authentication required.**

| Field | Value |
|---|---|
| Dataset page | https://hub.marinecadastre.gov/pages/vesseltraffic |
| Broadcast points index (2024) | https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html |
| Vessel track lines index | https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais/aistrack/index-aistrack.html |
| Legacy mirror (still works, older format) | https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/index.html |
| License | CC0 — Public Domain |
| Format | **CSV compressed with Zstandard (`.csv.zst`)**, daily files, from 2015 onwards |
| Sampling | Pre-filtered to 1 ping per minute |
| Coverage | US coastal waters, 2009–2025 |

**Three data products available:**

| Product | Description | Use for this project |
|---|---|---|
| Broadcast Points | Individual AIS pings — one row per transmission | ✅ Yes — used for anomaly detection |
| Track Lines | Per-vessel trajectory lines, aggregated annually | No — GIS visualisation only |
| Transit Counts | Traffic density heatmap per grid cell | No — statistical summaries only |

**Programmatic download (Python):**

```python
import requests, zstandard

# Example: first day of January 2024
url = "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-01.csv.zst"
r = requests.get(url, timeout=300)

with open("ais-2024-01-01.csv.zst", "wb") as f:
    f.write(r.content)

# Decompress .zst → .csv
dctx = zstandard.ZstdDecompressor()
with open("ais-2024-01-01.csv.zst", "rb") as src, open("ais-2024-01-01.csv", "wb") as dst:
    dctx.copy_stream(src, dst)
```

**Full schema (all 17 columns):**

| Column | Type | Description |
|---|---|---|
| `mmsi` | string | 9-digit vessel identifier — kept as string for joins |
| `base_date_time` | timestamp | UTC broadcast time (`yyyy-MM-dd HH:mm:ss`, space not T) |
| `longitude` | double | Longitude (decimal degrees) — comes before latitude in the file |
| `latitude` | double | Latitude (decimal degrees) |
| `sog` | double | Speed Over Ground (knots); max valid = 102.2 |
| `cog` | double | Course Over Ground (degrees) |
| `heading` | integer | True heading (degrees); empty = not available (old format used 511) |
| `vessel_name` | string | Self-reported vessel name |
| `imo` | string | IMO number with "IMO" prefix (e.g. `IMO7938024`); `IMO0000000` = unavailable |
| `call_sign` | string | Radio call sign |
| `vessel_type` | integer | NAIS vessel type code |
| `status` | integer | Navigation status code (0 = under way, 15 = undefined) |
| `length` | integer | Vessel length (metres) |
| `width` | integer | Vessel beam (metres) |
| `draft` | double | Draught (metres) |
| `cargo` | integer | Cargo type code |
| `transceiver` | string | `A` (SOLAS-mandatory) or `B` (voluntary small vessel) |

Field-by-field reference (technical + operational meaning): [`docs/ais_schema.md`](docs/ais_schema.md)  
AIS protocol field definitions (open, navigable): https://gpsd.gitlab.io/gpsd/AIVDM.html — GPSD project, source last updated March 2026 ([GitLab](https://gitlab.com/gpsd/gpsd/-/blob/master/www/AIVDM.adoc)); rendered page header still shows June 2023 but content is current

**Notes on older years:**
- 2009–2014: geodatabase format (`.gdb`), MMSI encrypted — not compatible with the ingestion script
- 2015–2025: CSV Zstd, compatible with the ingestion script

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

- [ ] Run ingestion script: pulls 2 months of `.csv.zst` from NOAA blob → Bronze Delta table (`pip install zstandard` on cluster first)
- [ ] Run OpenSanctions sync: API or bulk download → Bronze Delta table
- [ ] Verify row counts and schema in Databricks notebook before running Silver transforms
