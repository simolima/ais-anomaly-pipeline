{{ config(materialized='table') }}

with vessel_timeline as (
    select
        MMSI,
        VesselName,
        BaseDateTime,
        LAT,
        LON,
        lag(BaseDateTime) over (partition by MMSI order by BaseDateTime) as prev_ts,
        lag(LAT)          over (partition by MMSI order by BaseDateTime) as prev_lat,
        lag(LON)          over (partition by MMSI order by BaseDateTime) as prev_lon
    from {{ ref('ais_clean') }}
),

gaps as (
    select
        MMSI,
        VesselName,
        prev_ts      as gap_start,
        BaseDateTime as gap_end,
        timestampdiff(hour, prev_ts, BaseDateTime) as gap_hours,
        prev_lat     as last_known_lat,
        prev_lon     as last_known_lon,
        LAT          as reappearance_lat,
        LON          as reappearance_lon
    from vessel_timeline
    where prev_ts is not null
      and timestampdiff(hour, prev_ts, BaseDateTime) >= 6
)

select
    *,
    'dark_gap'                              as anomaly_type,
    least(gap_hours / 24.0, 1.0)           as anomaly_score
from gaps
