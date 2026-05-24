# AIS Data Schema — Column Reference

Source: NOAA MarineCadastre Broadcast Points, format `.csv.zst`, daily files 2015–2025.  
Technical standard: ITU-R M.1371-6 (February 2026). Primary open reference: [AIVDM/AIVDO Protocol Decoding Guide — GPSD project](https://gpsd.gitlab.io/gpsd/AIVDM.html) (source last updated March 2026; rendered page header shows June 2023 but content is current — [GitLab source](https://gitlab.com/gpsd/gpsd/-/blob/master/www/AIVDM.adoc))  
Sample file: [`sample_ais.csv`](../sample_ais.csv)

---

## `mmsi` — Maritime Mobile Service Identity

**Technical:** 9-digit numeric string. Unique identifier of the AIS transponder unit on board.  
**Operational:** The vessel's radio "licence plate" — it identifies the transponder, not the hull. Assigned by the maritime authority of the flag state. An MMSI can change when a vessel re-flags, and two vessels can share the same MMSI either by misconfiguration or deliberately (known as MMSI collision). For this reason it is not a fully reliable identifier: the pipeline stores it as a string to preserve any leading zeros and avoids arithmetic operations on it.

---

## `base_date_time` — Broadcast timestamp

**Technical:** UTC timestamp, format `yyyy-MM-dd HH:mm:ss` (space separator, not `T`). The moment the AIS transponder transmitted the message.  
**Operational:** NOAA pre-filters the raw data to **one ping per minute** per vessel. The physical transponder broadcasts far more frequently (every few seconds for vessels underway), but NOAA sub-samples to manage volume. Practical consequence: a gap of 6+ hours in this dataset represents a genuine prolonged absence, not a sampling artefact.

---

## `longitude` — Longitude

**Technical:** Decimal degrees, range `[-180, 180]`. Appears **before** `latitude` in the file — opposite to the standard geographic convention (lat, lon).  
**Operational:** East–west coordinate. Negative values = western hemisphere (Americas, Atlantic). Positive values = eastern hemisphere (Europe, Asia, eastern Pacific). The transponder receives this from the on-board GPS receiver. If the GPS signal is jammed or spoofed, this is the first field to become unreliable.

---

## `latitude` — Latitude

**Technical:** Decimal degrees, range `[-90, 90]`. Out-of-range values indicate hardware errors and are discarded by `ais_clean.sql`.  
**Operational:** North–south coordinate. Positive = northern hemisphere, negative = southern hemisphere. Together with longitude, this forms the vessel's self-reported position — which may not match its physical position if the transponder is transmitting falsified coordinates.

---

## `sog` — Speed Over Ground

**Technical:** Knots (1 knot = 1.852 km/h), precision 0.1 knots. Valid range: `[0, 102.2]`. The AIS protocol value 102.3 means "not available" — NOAA maps this to an empty field.  
**Operational:** The vessel's actual speed relative to the seabed, measured by GPS. Distinct from speed through water (which accounts for currents). A vessel at anchor or alongside has SOG ≈ 0. SOG > 30 knots for a cargo vessel or tanker is physically impossible and flags an anomaly. The 30-knot threshold used by `ais_impossible_speed.sql` is a conservative ceiling for this vessel class.

---

## `cog` — Course Over Ground

**Technical:** Decimal degrees, range `[0, 360)`. Actual direction of movement relative to true north, measured by GPS.  
**Operational:** The direction the vessel is actually travelling, which can differ from the heading (bow direction) due to wind and current drift. A vessel at rest or manoeuvring has an unstable or meaningless COG. Used to reconstruct trajectories when analysing dark gaps or cross-checking reported positions.

---

## `heading` — True heading

**Technical:** Integer degrees, range `[0, 359]`. Empty field = not available. (The legacy `.zip` format used the sentinel value `511` for this; the current `.csv.zst` format uses an empty field.)  
**Operational:** The compass direction the vessel's bow physically points, measured by the gyrocompass — not the direction of travel. Many class B vessels (small craft) lack a gyrocompass, so this field is frequently empty. Differs from COG when there is current or wind drift. Useful for detecting anomalous manoeuvres: a vessel pointing north while moving east indicates unusual behaviour.

---

## `vessel_name` — Vessel name

**Technical:** Free-text string, max 20 characters per the AIS protocol.  
**Operational:** The commercial name of the vessel, self-reported by the transponder. It is not verified in real time and can be changed by the operator at any time. Dark fleet vessels change names frequently to evade watchlists. Since 2015, NOAA corrects this field using the AVIS/AVID database for US-registered vessels; for foreign-flagged vessels it remains self-reported.

---

## `imo` — IMO number

**Technical:** String with a literal `"IMO"` prefix followed by 7 digits (e.g. `IMO9840879`). The value `IMO0000000` indicates absence. Empty for many small craft.  
**Operational:** Assigned by the International Maritime Organization to the **hull** — not the transponder. Unlike MMSI, it does not change when the vessel re-flags or changes ownership, and follows the hull throughout its operational life. It is the most reliable identifier for linking a vessel to official registries, port state inspections, and sanctions lists. The presence of `IMO0000000` or an empty field is itself a risk indicator: the vessel may be unregistered or deliberately concealing its identity.

---

## `call_sign` — Radio call sign

**Technical:** Alphanumeric string, assigned by the telecommunications authority of the flag state.  
**Operational:** The identifier used in VHF radio communications between vessel and port, or vessel-to-vessel. Tied to the radio licence, not the hull — can change with the flag. Useful as an additional cross-check but less reliable than the IMO number. Often empty for small craft.

---

## `vessel_type` — Vessel type

**Technical:** Integer code per the NAIS classification. Most relevant codes for this project:

| Code | Type |
|---|---|
| 30 | Fishing |
| 31–32 | Tug / towing |
| 36–37 | Sailing / pleasure craft |
| 52 | Tug |
| 70–79 | General cargo |
| 80–89 | Tanker |
| 90 | Other |

**Operational:** Provides context for any anomaly. A tanker (80–89) with a 12-hour dark gap near a sanctioned port is a high-priority signal. A pleasure craft (36) with a similar gap likely just switched off the transponder overnight. The type is self-reported and can be falsified — some dark fleet tankers declare themselves as "cargo" to reduce scrutiny.

---

## `status` — Navigation status

**Technical:** Integer code. Primary values:

| Code | Status |
|---|---|
| 0 | Under way using engine |
| 1 | At anchor |
| 3 | Restricted manoeuvrability |
| 5 | Moored |
| 8 | Under way sailing |
| 15 | Not defined / not available |

**Operational:** Self-reported by the master — not automatically verified. A vessel declaring "at anchor" (1) while showing SOG > 5 knots is inconsistent and may indicate falsified data. Code 15 (not available) is common on class B vessels or badly configured transponders.

---

## `length` — Length

**Technical:** Metres, integer. Derived from the AIS dimension fields (A+B).  
**Operational:** Overall length of the vessel. Useful for contextualising anomalies: a 300 m VLCC tanker reporting SOG of 40 knots is physically impossible; a 30 m patrol craft could approach that figure. Often `0` or empty for small craft that do not transmit dimensions.

---

## `width` — Beam

**Technical:** Metres, integer. Maximum hull width.  
**Operational:** Used together with length to estimate tonnage and vessel category. Useful as a sanity check: `length=200` with `width=2` indicates corrupt data.

---

## `draft` — Draught

**Technical:** Metres, decimal. Depth of the hull below the waterline.  
**Operational:** Changes with the cargo load — increases when laden, decreases when in ballast. A high draught in shallow water is physically impossible and indicates bad data. For tankers, comparing declared draught at departure and arrival is one of the methods port state authorities use to detect clandestine ship-to-ship (STS) oil transfers at sea: a vessel that departs full and arrives full without visiting a terminal has likely offloaded at sea.

---

## `cargo` — Cargo type

**Technical:** Integer code per the NAIS classification. Partial overlap with `vessel_type`.  
**Operational:** The type of cargo carried, self-reported. In sanctions-evasion investigations, the combination `vessel_type=80–89` (tanker) with a cargo code inconsistent with the vessel type is a flag of interest.

---

## `transceiver` — Transceiver class

**Technical:** Single character: `A` or `B`.  
**Operational:** Class A = mandatory under SOLAS for commercial vessels > 300 GT on international voyages and > 500 GT on coastal voyages. Transmits every 2–10 seconds. Class B = voluntary, for pleasure craft and small fishing vessels. Transmits every 30 seconds. Vessels of interest to this pipeline (tankers, cargo ships) should always be class A. A tanker broadcasting as class B is anomalous in itself and warrants investigation.
