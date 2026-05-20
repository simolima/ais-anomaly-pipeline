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

with_implied_speed as (
    select
        *,
        -- Haversine distance in nautical miles
        3440.065 * 2 * asin(sqrt(
            pow(sin(radians(LAT - prev_lat) / 2), 2) +
            cos(radians(prev_lat)) * cos(radians(LAT)) *
            pow(sin(radians(LON  - prev_lon) / 2), 2)
        )) as distance_nm,
        timestampdiff(second, prev_ts, BaseDateTime) / 3600.0 as elapsed_hours
    from vessel_timeline
    where prev_ts is not null
      and timestampdiff(second, prev_ts, BaseDateTime) > 0
),

impossible as (
    select
        *,
        distance_nm / elapsed_hours as implied_speed_knots
    from with_implied_speed
    -- 30 knots: conservative physical ceiling for cargo/tanker vessels
    where distance_nm / elapsed_hours > 30
)

select
    MMSI,
    VesselName,
    prev_ts              as event_start,
    BaseDateTime         as event_end,
    prev_lat             as from_lat,
    prev_lon             as from_lon,
    LAT                  as to_lat,
    LON                  as to_lon,
    distance_nm,
    implied_speed_knots,
    'impossible_speed'                                  as anomaly_type,
    least((implied_speed_knots - 30) / 70.0, 1.0)      as anomaly_score
from impossible
