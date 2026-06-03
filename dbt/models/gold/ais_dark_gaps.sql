{%- set win = ais_window() -%}
{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ win[0] ~ "' and event_date <= date'" ~ win[1] ~ "'"
    ]
) }}

-- Windowed incremental. event_date is anchored on the REAPPEARANCE ping (gap_end),
-- which is always inside the window; the gap_start may live in a prior window and is
-- only supplied as lookback context (never re-emitted).
{%- set window_start = win[0] -%}
{%- set window_end   = win[1] -%}
{%- set has_window   = win[2] -%}
{% set apply_window = has_window or is_incremental() %}

with window_rows as (
    select mmsi, vessel_name, base_date_time, latitude, longitude
    from {{ ref('ais_clean') }}
    {% if apply_window %}
    where event_date between date'{{ window_start }}' and date'{{ window_end }}'
    {% endif %}
),

{% if apply_window %}
-- The single most recent ping per vessel strictly BEFORE the window, over ALL prior
-- history (unbounded), so a dark gap of any length straddling the window boundary is
-- still detected — parity with the old full-history LAG. LAG only looks one row back,
-- so one prior ping per vessel is sufficient.
prior_ping as (
    select mmsi, vessel_name, base_date_time, latitude, longitude
    from (
        select
            mmsi, vessel_name, base_date_time, latitude, longitude,
            row_number() over (partition by mmsi order by base_date_time desc) as rn
        from {{ ref('ais_clean') }}
        where event_date < date'{{ window_start }}'
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
      {% if apply_window %}
      -- only emit gaps whose reappearance falls in the window, so the prior_ping rows
      -- (outside the window) never produce a duplicate anomaly
      and cast(base_date_time as date) between date'{{ window_start }}' and date'{{ window_end }}'
      {% endif %}
)

select
    *,
    'dark_gap'                     as anomaly_type,
    least(gap_hours / 24.0, 1.0)  as anomaly_score
from gaps
