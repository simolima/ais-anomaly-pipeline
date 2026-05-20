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

## 2. How AIS Works — and Why It Breaks

The Automatic Identification System (AIS) is a maritime safety protocol, not a surveillance system. Vessels above a certain tonnage are legally required to broadcast their MMSI (Maritime Mobile Service Identity), position, speed, and course at regular intervals — every 2–10 seconds when moving, every 3 minutes at anchor.

The fundamental design flaw is that AIS is a **self-reported, unverified system**. There is no external authority validating that the position a vessel broadcasts corresponds to where it actually is. The signal is received by:
- Coastal VHF receivers (range ~40–60 km)
- Satellite AIS (S-AIS) receivers in low Earth orbit

Satellite coverage has improved dramatically, but gaps remain in open ocean areas and congested reception zones where signals from thousands of vessels collide.

---

## 3. The Three Manipulation Techniques

### 3.1 Dark Gap (Transponder Shutdown)

The simplest form of evasion: the crew manually disables the AIS transponder. The vessel disappears from tracking entirely. When it reappears, it may be hundreds of miles from its last known position, with no voyage record in between.

Detection is straightforward in principle — compute the time delta between consecutive messages for each MMSI — but requires careful separation from legitimate causes of signal loss: VHF dead zones, satellite coverage gaps, receiver overload in congested areas, and equipment failures.

Key statistical finding from industry reports: dark gaps concentrated near known ship-to-ship (STS) transfer zones in the Strait of Gibraltar, Laconian Gulf (Greece), and Lamu (Kenya) correlate strongly with sanctions-linked cargo transfers.

### 3.2 Impossible Speed (Kinematic Inconsistency)

After a dark gap, a vessel reappears at a position that would have required physically impossible speeds to reach from its last known location — often exceeding 50–100 knots for a cargo tanker whose real maximum is 14–16 knots.

This anomaly can also arise without a gap: a vessel broadcasts a spoofed position far from its actual location, creating an apparent "jump" in the trajectory. The detection criterion is simple (implied speed = distance / time > physical threshold), but distinguishing intentional spoofing from sensor artifacts and MMSI collisions requires the data quality work described in Section 5.

### 3.3 AIS Spoofing (Active Position Falsification)

Spoofing is qualitatively different from going dark: the vessel's AIS transponder actively broadcasts false coordinates. As Kpler's 2025 analysis describes, this is always intentional — it requires either manual entry of incorrect position data or software that manipulates the GPS feed into the AIS transponder.

Common spoofing patterns documented in industry reports include:
- **Port spoofing**: broadcasting a position inside a legitimate port while conducting STS transfers at sea
- **Circle spoofing**: transmitting positions that trace a perfect circle (a hardware artifact of certain spoofing devices)
- **Historical location replay**: looping a previous legitimate voyage track while the vessel deviates

The Kpler report notes that detection is technically faster than for dark gaps: when a vessel's AIS position contradicts satellite imagery or shows kinematically impossible movements, automated systems can flag the anomaly within hours.

---

## 4. Geopolitical Context

The acceleration of AIS manipulation is not random. Windward's analysis shows that 91% of sanctions-related dark activities in 2025 were tied to Russia- and Iran-aligned fleets. The motivations are clear:

**Russia**: Since the February 2022 invasion of Ukraine, a parallel logistics infrastructure has been constructed to move Russian crude outside the price cap and sanctions regime. Tankers disable AIS before entering known STS hotspots and reappear with implausible voyage histories. GPS jamming in the Baltic and Black Sea has a dual purpose: protecting military assets from Ukrainian drone strikes and obscuring commercial vessel movements.

**Iran**: OFAC's April 2025 guidance specifically addresses Iranian oil sanctions evasion, documenting the use of multiple STS transfers in a single shipment to obscure cargo origin, combined with falsified documents and AIS manipulation.

**Structural enablers**: Flag-hopping reached unprecedented levels in 2025. False-flag vessels accounted for 29% of the dark fleet. New fraudulent registries operate with minimal oversight, providing legal cover (however thin) for vessels that would otherwise be stateless.

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
