{{ config(materialized='table') }}

-- Per-vessel behavioural fingerprint: one row per vessel that has at least one anomaly,
-- aggregating the gold detail tables into the feature vector consumed by the Isolation
-- Forest (ml/isolation_forest.py). The point of per-vessel aggregation is that the model
-- can isolate rare *combinations* of behaviour (many moderate gaps + a jump + sanctioned),
-- which a single-event threshold on anomaly_score cannot.

with dark as (
    select
        mmsi,
        count(*)           as n_dark_gaps,
        avg(gap_hours)     as avg_gap_hours,
        max(gap_hours)     as max_gap_hours,
        max(anomaly_score) as max_dark_score
    from {{ ref('ais_dark_gaps') }}
    group by mmsi
),

-- Data-quality guard: ais_impossible_speed flags everything > 30 kn, but a large share of
-- those rows are artefacts, not vessels actually moving fast — two pings ~1 s apart (dt in
-- the denominator -> millions of knots) or a garbage position (0,0 / sentinel) producing a
-- thousand-nm "jump" in one second. Those inflate n_impossible_speed / max_implied_speed /
-- max_jump_nm and let the Isolation Forest rank stationary infrastructure (oil rigs,
-- dredges) and bad transponders at the top. Keep only a physically plausible band: above
-- ~50 kn is already faster than almost any real ship, 90 kn is a generous hard ceiling;
-- anything above that is a measurement error, not an anomaly. This re-derives clean
-- features from the already-persisted detail rows — no need to reprocess the windowed model.
speed as (
    select
        mmsi,
        count(*)                 as n_impossible_speed,
        max(implied_speed_knots) as max_implied_speed,
        max(distance_nm)         as max_jump_nm,
        max(anomaly_score)       as max_speed_score
    from {{ ref('ais_impossible_speed') }}
    where implied_speed_knots <= 90
    group by mmsi
),

-- every vessel that tripped at least one rule
vessels as (
    select mmsi from dark
    union
    select mmsi from speed
),

-- a display name from whichever detail table carries it
names as (
    select mmsi, max(vessel_name) as vessel_name
    from (
        select mmsi, vessel_name from {{ ref('ais_dark_gaps') }}
        union all
        select mmsi, vessel_name from {{ ref('ais_impossible_speed') }}
    )
    group by mmsi
),

sanctioned as (
    select distinct mmsi, 1 as is_sanctioned
    from {{ source('bronze', 'sanctions') }}
    where mmsi is not null
)

select
    v.mmsi,
    n.vessel_name,
    coalesce(d.n_dark_gaps, 0)            as n_dark_gaps,
    coalesce(d.avg_gap_hours, 0)          as avg_gap_hours,
    coalesce(d.max_gap_hours, 0)          as max_gap_hours,
    coalesce(s.n_impossible_speed, 0)     as n_impossible_speed,
    coalesce(s.max_implied_speed, 0)      as max_implied_speed,
    coalesce(s.max_jump_nm, 0)            as max_jump_nm,
    coalesce(d.n_dark_gaps, 0)
        + coalesce(s.n_impossible_speed, 0) as total_anomalies,
    greatest(
        coalesce(d.max_dark_score, 0),
        coalesce(s.max_speed_score, 0)
    )                                     as max_anomaly_score,
    coalesce(sa.is_sanctioned, 0)         as is_sanctioned
from vessels v
left join dark        d  on v.mmsi = d.mmsi
left join speed       s  on v.mmsi = s.mmsi
left join names       n  on v.mmsi = n.mmsi
left join sanctioned  sa on v.mmsi = sa.mmsi
-- Keep only well-formed ship MMSIs. A valid ship identity is 9 digits with a leading MID
-- digit 2-7; the other ranges are not independent vessels and pollute the ranking:
--   0xx = base/coast station, 1xx = SAR aircraft, 8xx = handheld/directional,
--   98x = craft associated with a parent ship, 99x = aid to navigation (e.g. rig markers).
-- Also drops obvious placeholders like 123456789. mmsi is StringType (kept for joins).
where length(v.mmsi) = 9
  and substring(v.mmsi, 1, 1) between '2' and '7'
