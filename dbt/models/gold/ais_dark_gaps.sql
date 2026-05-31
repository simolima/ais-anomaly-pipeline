{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ var('start_date', '2999-01-01') ~ "' and event_date <= date'" ~ var('end_date', '2999-01-01') ~ "'"
    ]
) }}

-- Windowed incremental. event_date is anchored on the REAPPEARANCE ping (gap_end),
-- which is always inside [start_date, end_date]; the gap_start may live in a prior
-- window and is only supplied as lookback context (never re-emitted).
{% set has_window  = var('start_date', none) is not none %}
{% set lookback_days = var('lookback_days', 7) %}

with window_rows as (
    select mmsi, vessel_name, base_date_time, latitude, longitude
    from {{ ref('ais_clean') }}
    {% if has_window %}
    where event_date between date'{{ var("start_date") }}' and date'{{ var("end_date") }}'
    {% endif %}
),

{% if has_window %}
-- The single most recent ping per vessel strictly BEFORE the window (bounded lookback),
-- so a gap straddling the window boundary is still detected. LAG only looks one row back,
-- so one prior ping per vessel is sufficient.
prior_ping as (
    select mmsi, vessel_name, base_date_time, latitude, longitude
    from (
        select
            mmsi, vessel_name, base_date_time, latitude, longitude,
            row_number() over (partition by mmsi order by base_date_time desc) as rn
        from {{ ref('ais_clean') }}
        where event_date >= date_sub(date'{{ var("start_date") }}', {{ lookback_days }})
          and event_date <  date'{{ var("start_date") }}'
    )
    where rn = 1
),
combined as (
    select * from window_rows
    union all
    select mmsi, vessel_name, base_date_time, latitude, longitude from prior_ping
),
{% else %}
combined as (
    select * from window_rows
),
{% endif %}

vessel_timeline as (
    select
        mmsi, vessel_name, base_date_time, latitude, longitude,
        lag(base_date_time) over (partition by mmsi order by base_date_time) as prev_ts,
        lag(latitude)       over (partition by mmsi order by base_date_time) as prev_lat,
        lag(longitude)      over (partition by mmsi order by base_date_time) as prev_lon
    from combined
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
        longitude      as reappearance_lon,
        cast(base_date_time as date) as event_date
    from vessel_timeline
    where prev_ts is not null
      and timestampdiff(hour, prev_ts, base_date_time) >= 6
      {% if has_window %}
      -- only emit gaps whose reappearance falls in the window, so the prior_ping rows
      -- (outside the window) never produce a duplicate anomaly
      and cast(base_date_time as date)
          between date'{{ var("start_date") }}' and date'{{ var("end_date") }}'
      {% endif %}
)

select
    *,
    'dark_gap'                     as anomaly_type,
    least(gap_hours / 24.0, 1.0)  as anomaly_score
from gaps
