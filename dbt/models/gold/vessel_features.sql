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

-- Data-quality guard. ais_impossible_speed flags every implied speed > 30 kn, but most of
-- those rows are NOT vessels moving fast — they are artefacts of the implied-speed formula
-- (distance / dt) on noisy data:
--   * GPS jitter: two pings ~seconds apart with a sub-nm position wiggle -> huge implied
--     speed but no real movement (this produced the original millions-of-knots);
--   * fast ferries (SeaStreak, Catalina, Key West Express…) cruising at 35-45 kn -> they
--     trip the 30 kn rule on every ping and, pinging constantly, rack up tens of thousands
--     of events that drown real anomalies in the count;
--   * bad positions (0,0 / sentinel coord) -> a thousand-nm "jump" in one step.
-- DISTANCE is the clean discriminator, not implied speed (which is confounded: both jitter
-- and a real teleport read as high speed). A genuine AIS spoof/teleport is a LARGE but
-- bounded position jump at a physically impossible speed — keep only those:
--   distance_nm between 2 and 500  -> excludes jitter (<2 nm) and bad positions (>500 nm)
--   implied_speed_knots > 50       -> excludes ferry cruise (no real ship covers a multi-nm
--                                     jump at >50 kn)
-- Re-derives clean features from the already-persisted detail rows — no backfill needed.
speed as (
    select
        mmsi,
        count(*)                 as n_impossible_speed,
        max(implied_speed_knots) as max_implied_speed,
        max(distance_nm)         as max_jump_nm,
        max(anomaly_score)       as max_speed_score
    from {{ ref('ais_impossible_speed') }}
    where distance_nm between 2 and 500
      and implied_speed_knots > 50
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

-- Corroborated sanctions match. Matching on MMSI ALONE produces false positives because
-- MMSIs get reassigned/reused: in this dataset all 5 MMSI hits were collisions (e.g. MMSI
-- 249256000 is OFAC-listed 'SINA' but transmits as 'LUIGI GALVANI', a legitimate Italian
-- research vessel). A real hit needs a second key to agree. IMO would be strongest but the
-- OpenSanctions vessel pull carries no IMO here, so corroborate on the vessel NAME
-- (normalised: upper-case, strip non-alphanumerics).
--   is_sanctioned           = confirmed: MMSI AND name agree
--   sanctions_mmsi_only_hit = MMSI matched but name did not = likely collision; surface as
--                             "to investigate", never as a confirmed alert.
sanctioned as (
    select
        n.mmsi,
        max(case
            when regexp_replace(upper(trim(s.entity_name)), '[^A-Z0-9]', '')
               = regexp_replace(upper(trim(n.vessel_name)),  '[^A-Z0-9]', '')
            then 1 else 0 end)                        as is_sanctioned,
        1                                             as sanctions_mmsi_only_hit
    from {{ source('bronze', 'sanctions') }} s
    join names n on s.mmsi = n.mmsi
    where s.mmsi is not null
    group by n.mmsi
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
    coalesce(sa.is_sanctioned, 0)            as is_sanctioned,
    coalesce(sa.sanctions_mmsi_only_hit, 0)  as sanctions_mmsi_only_hit
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
