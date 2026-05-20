# Maritime AIS Anomaly Detection — Context & State of the Problem

> Document version: May 2026
> Purpose: background reading for contributors to `ais-anomaly-pipeline`

---

## 1. The Problem in Numbers

The scale of maritime deception has expanded dramatically in the past two years. According to Windward AI's 2025 risk reports, more than 24,000 vessels experienced GPS jamming across Q1–Q3 2025 alone, with AIS position "jumps" averaging 6,300 km — meaning a vessel appears to teleport thousands of kilometres in seconds. GPS jamming incidents surged 510% between Q1 and Q3 2025, with new interference hubs identified in the Baltic Sea, Arabian Gulf, Eastern Mediterranean, Nakhodka Bay (Russia's Pacific export corridor), and — for the first time — off Venezuela.

The Kpler report of November 2025 documented 261 vessels that falsified AIS signals in the period January 2024 – July 2025, all of which were subsequently sanctioned. This makes AIS spoofing a leading indicator of sanctions designation: the manipulation appears months before the formal legal action.

The dark fleet — vessels operating systematically outside compliance controls — reached over 1,900 active tankers as of Q3 2025, supported by more than 1,200 gray fleet vessels. By year-end 2025, 76% of Windward's tracked dark fleet crude tankers had been formally sanctioned. False-flag registrations surged: the number of sanctioned, flagless, or stateless tankers doubled compared to 2024, with fraudulent registries emerging across 18 jurisdictions including Tonga, Mozambique, Angola, and Gambia.

The enforcement picture is fragmented. Regulators (OFAC, EU, UK OFSI) have explicitly identified AIS manipulation as a key evasion indicator in their guidance, but enforcement remains split across jurisdictions and relies heavily on commercial intelligence providers that most institutions cannot access.

---

## 2. How AIS Works — and Why It Is Fundamentally Vulnerable

AIS (Automatic Identification System) is a radio system mandated by international law (SOLAS convention) on all commercial vessels above 300 gross tonnes. Every transponder automatically broadcasts a packet every few seconds containing: identity (MMSI, vessel name, IMO number), position (GPS coordinates), movement (speed, course, heading), and vessel type.

Shore-based receivers — coastal stations, satellites in low Earth orbit, other vessels — capture these signals and aggregate them. The result is a near-real-time global map of commercial maritime traffic. It is the backbone of port authorities, compliance systems, marine insurers, and commodity traders tracking tankers.

**The fundamental flaw: AIS was designed for navigational safety, not identification.**

The transponder transmits whatever it is told to transmit. There is no authentication, no cryptographic signature, no external verification of coordinates. A vessel can program its transponder with any MMSI, any name, any position. The system trusts blindly what it receives.

This makes it intrinsically vulnerable to three categories of manipulation.

---

## 3. The Three Manipulation Techniques

### 3.1 Dark Gap (Transponder Shutdown)

The vessel simply switches off the transponder. It vanishes from all tracking for hours or days, conducts whatever it needs to conduct — a ship-to-ship oil transfer, entry into a sanctioned port, an arms delivery — then reappears elsewhere as if nothing happened.

The detection challenge is that not every gap is illicit. Technical failures, areas with poor receiver coverage, and inland waterways where AIS is not mandatory all generate innocent gaps. Distinguishing a deliberate shutdown from a technical outage requires contextual analysis: how long the gap lasts, where it occurs, and whether multiple vessels disappear simultaneously in the same area (a strong indicator of area-wide jamming rather than individual evasion).

Key statistical finding: dark gaps concentrated near known ship-to-ship (STS) transfer zones in the Strait of Gibraltar, Laconian Gulf (Greece), and Lamu (Kenya) correlate strongly with sanctions-linked cargo transfers.

### 3.2 Impossible Speed (Kinematic Inconsistency)

A variant of the dark gap. The vessel disappears, physically relocates, then reappears. But the delta between the last known position and the new position, divided by elapsed time, implies a speed no commercial vessel can physically achieve — 40, 60, 100 knots, when the realistic maximum for a cargo vessel is 25–30 knots. The signal is almost always unambiguous: the vessel moved while "switched off", and the distance betrays the actual displacement.

This anomaly can also appear without a gap: a vessel broadcasts a spoofed position far from its real location, creating an apparent trajectory jump. The detection criterion is simple (implied speed = distance / time > physical threshold), but separating intentional spoofing from sensor artifacts and MMSI collisions requires the data quality work described in Section 5.

### 3.3 AIS Spoofing (Active Position Falsification)

The most sophisticated form. The vessel does not switch off — it keeps broadcasting regularly — but transmits fabricated GPS coordinates. The transponder reports "I am in the port of Rotterdam" while the vessel is physically in the Arabian Gulf conducting an unauthorized transfer. To a naive monitoring system, the vessel looks clean: it is transmitting, it is in a legitimate port, everything appears normal.

Detection requires internal consistency checks: the transmitted coordinates must be compared against the physics of the prior trajectory (an IMM Kalman filter predicts where the vessel should be given its real kinematics), against the declared positions of nearby vessels (if twenty ships suddenly all report being at the same point, something is wrong), and against satellite imagery when available.

Common spoofing patterns documented in industry reports:
- **Port spoofing**: declaring a position inside a legitimate port while conducting STS transfers at sea
- **Circle spoofing**: positions that trace a geometrically perfect circle — a hardware artifact of certain spoofing devices
- **Historical replay**: looping a previous legitimate voyage track while the vessel deviates from it

---

## 4. Why This Has Industrialised — Geopolitical Context

Until a few years ago, AIS manipulation was rare and artisanal. Three factors have industrialised it.

**Post-2022 Russia sanctions** created a shadow fleet of hundreds of vessels moving Russian crude outside Western price caps and sanctions regimes. These vessels have an enormous economic incentive to become invisible. Windward's analysis shows that 91% of sanctions-related dark activities in 2025 were tied to Russia- and Iran-aligned fleets.

**Military GPS jamming** in the Baltic and Middle East — begun as a countermeasure against Ukrainian drones — normalised GPS signal manipulation across entire geographic areas. Commercial vessels became collateral damage, but opportunistic beneficiaries as well: jamming provides plausible cover for AIS anomalies that would otherwise be immediately suspicious.

**Accessible hardware**: the market for modified AIS transponders has matured. State-level resources are no longer required to falsify a signal.

The result: GPS jamming incidents surged 510% between Q1 and Q3 2025, with over 11,600 vessels affected in Q3 alone. The dark fleet reached over 1,900 active tankers. False-flag registrations surged across 18 jurisdictions. By year-end 2025, 76% of Windward's tracked dark fleet crude tankers had been formally sanctioned — but the manipulation preceded the designation, often by months.

**Iran**: OFAC's April 2025 guidance specifically addresses Iranian oil sanctions evasion, documenting multiple sequential STS transfers in a single shipment to obscure cargo origin, combined with falsified documents and AIS manipulation.

**Structural enabler**: Flag-hopping reached unprecedented levels. False-flag vessels accounted for 29% of the dark fleet. New fraudulent registries operate with minimal oversight across jurisdictions including Tonga, Mozambique, Angola, and Gambia.

---

## 5. Why Detection Is Hard — Current Limitations

### 5.1 Data Quality: The False Positive Problem

Raw AIS data is extremely noisy. Without careful preprocessing, naive anomaly detection produces massive false positive rates from entirely innocent sources:

- **MMSI collision**: Multiple vessels legally or illegally sharing the same MMSI identifier. A position jump between two vessels sharing an MMSI looks identical to spoofing.
- **Stale-data retransmission**: Buffered messages rebroadcast with updated timestamps, creating apparent backward motion.
- **Satellite receiver collision**: In congested areas, S-AIS receivers detect signals from thousands of vessels simultaneously, producing corrupted or misattributed messages.
- **Interpolation artifacts**: Many AIS aggregators fill gaps with linear interpolation, which then gets treated as real data by downstream detectors.

Park et al. (2026, arxiv:2603.11055) identify this preprocessing step as the critical bottleneck: without proper artifact removal, any clustering or ML approach generates enough false alarms to be operationally useless.

### 5.2 Ground Truth Scarcity

There are no large-scale publicly labeled AIS datasets where anomalies are confirmed. The academic literature consistently identifies the absence of labeled ground truth as the primary obstacle to supervised ML approaches. Researchers work around this through:
- Synthetic data injection (Agrebi, IEEE DataPort, 2025 — synthetic GPS spoofing dataset for MASS)
- Using post-hoc confirmed sanctions designations as weak labels
- Unsupervised methods that require no labels (Isolation Forest, DBSCAN, autoencoders)

### 5.3 The Single-Source Problem

AIS-only detection has a fundamental ceiling. Sophisticated evasion actors know exactly what algorithmic detection looks like and adapt accordingly — spoofing positions that are kinematically plausible, timing dark gaps to coincide with known satellite coverage gaps, using relay vessels to create clean AIS histories.

The frontier of maritime intelligence fuses multiple modalities:
- **SAR (Synthetic Aperture Radar)**: detects vessels regardless of AIS status, in all weather conditions
- **EO (Electro-Optical) satellite imagery**: visual confirmation of vessel identity and position
- **RF detection**: identifies AIS transmissions independently of their reported content

Open-source access to SAR and RF data remains limited. This project focuses on what is achievable with public AIS data alone, while acknowledging this ceiling explicitly.

### 5.4 The Closed-Source / Interpretability Problem

Commercial platforms (Windward Maritime AI, Kpler) have invested heavily in the fusion approach above and deliver operational intelligence. But their models are black boxes. Analysts cannot inspect why a specific vessel was flagged, audit the model's behavior on edge cases, or reproduce findings independently.

The academic literature (AIS-LLM, arxiv 2025) explicitly flags poor interpretability as a systemic problem: deep learning models "output predictions merely as numerical values" that are "difficult to interpret intuitively and limit the range of actionable insights." A compliance analyst needs to explain a flag to a regulator or counterparty, not just cite a model score.

### 5.5 Real-Time vs. Batch Processing

Most published research operates in batch mode on historical AIS data. Operational maritime intelligence requires near-real-time detection — ideally within hours of a dark gap beginning, not days later when the vessel has already completed an STS transfer.

---

## 6. What This Project Contributes

**In scope:**
- A reproducible Bronze/Silver/Gold data pipeline on public NOAA AIS data
- Artifact removal that addresses MMSI collision, retransmission, and coordinate errors (following Park et al. 2026)
- Rule-based dark gap and impossible speed detection with explainable thresholds
- Unsupervised ML baseline (Isolation Forest) for anomaly scoring
- IMM Kalman Filter + ST-DBSCAN for spoofing/jamming pattern detection
- Join with OpenSanctions for risk profile enrichment
- A dashboard that makes findings interpretable, not just numeric scores

**Explicitly out of scope (v1):**
- SAR / EO / RF fusion — requires data access not publicly available
- Real-time streaming — the pipeline is designed for batch processing of historical data
- Supervised classification — no labeled ground truth exists at scale
- Coverage outside NOAA's US coastal zone without additional data procurement

---

## 7. References

| Source | Type | Year |
|---|---|---|
| Park, Cho, Son — *Wide-Area GNSS Spoofing and Jamming Detection Using AIS* (arxiv:2603.11055) | Academic paper | 2026 |
| Windward AI — *2025 Was a Stress Test: Maritime AI Is the Only Way to Pass* | Industry report | 2025 |
| Windward AI — *Beyond AIS: Why Maritime Visibility Now Depends on Remote Sensing Intelligence* | Industry report | Dec 2025 |
| Windward AI — *What Is the Dark Fleet?* | Industry report | Jan 2026 |
| Kpler — *AIS Spoofing: The Fast Track to Sanctions* | Industry report | Nov 2025 |
| VLMAR — *Maritime Scene Anomaly Detection via Retrieval-Augmented Vision-Language Models* | Academic paper | Dec 2025 |
| AIS-LLM — *A Unified Framework for Maritime Trajectory Prediction, Anomaly Detection and Collision Risk Assessment* (arxiv:2508.07668) | Academic paper | Aug 2025 |
| Agrebi — *Synthetic GPS Dataset for AI-Based Spoofing Detection on MASS* (IEEE DataPort) | Dataset | Oct 2025 |
| NATO STO — *Real-Time AIS Data Analysis for Anomaly Detection* | NATO paper | 2024 |
| Singh & Heymann (DLR) — *ML-Assisted Anomaly Detection Using AIS* (arxiv:2002.05013) | Academic paper | 2020 |
| NOAA / US Coast Guard — MarineCadastre.gov AIS Dataset | Public dataset (CC0) | 2009–2024 |
| OpenSanctions | Public dataset | Continuously updated |
