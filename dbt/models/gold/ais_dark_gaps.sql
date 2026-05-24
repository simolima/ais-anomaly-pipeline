{{ config(materialized='table') }}

with vessel_timeline as (
    select
        mmsi,
        vessel_name,
        base_date_time,
        latitude,
        longitude,
        lag(base_date_time) over (partition by mmsi order by base_date_time) as prev_ts,
        lag(latitude)       over (partition by mmsi order by base_date_time) as prev_lat,
        lag(longitude)      over (partition by mmsi order by base_date_time) as prev_lon
    from {{ ref('ais_clean') }}
),

gaps as (
    select
        mmsi,
        vessel_name,
        prev_ts        as gap_start,
        base_date_time as gap_end,
        timestampdiff(hour, prev_ts, base_date_time) as gap_hours,
        prev_lat       as last_known_lat,
        prev_lon       as last_known_lon,
        latitude       as reappearance_lat,
        longitude      as reappearance_lon
    from vessel_timeline
    where prev_ts is not null
      and timestampdiff(hour, prev_ts, base_date_time) >= 6
)

select
    *,
    'dark_gap'                              as anomaly_type,
    least(gap_hours / 24.0, 1.0)           as anomaly_score
from gaps
