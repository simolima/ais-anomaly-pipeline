{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ var('start_date', '2999-01-01') ~ "' and event_date <= date'" ~ var('end_date', '2999-01-01') ~ "'"
    ]
) }}

-- Windowed incremental. event_date is anchored on the SECOND ping (event_end), which is
-- always inside [start_date, end_date]; the first ping (event_start) may come from the
-- lookback window.
{% set has_window   = var('start_date', none) is not none %}
-- Apply the window on any incremental run (no vars -> default 2999-01-01 -> true no-op
-- matching the replace_where predicate) and on a windowed/first build. Only a full build
-- with no vars reads all history.
{% set apply_window = has_window or is_incremental() %}

with window_rows as (
    select mmsi, vessel_name, base_date_time, latitude, longitude
    from {{ ref('ais_clean') }}
    {% if apply_window %}
    where event_date between date'{{ var("start_date", "2999-01-01") }}' and date'{{ var("end_date", "2999-01-01") }}'
    {% endif %}
),

{% if apply_window %}
-- One prior ping per vessel strictly before the window, over ALL prior history
-- (unbounded), so a position jump straddling the window boundary is still evaluated.
-- LAG only needs one row back.
prior_ping as (
    select mmsi, vessel_name, base_date_time, latitude, longitude
    from (
        select
            mmsi, vessel_name, base_date_time, latitude, longitude,
            row_number() over (partition by mmsi order by base_date_time desc) as rn
        from {{ ref('ais_clean') }}
        where event_date < date'{{ var("start_date", "2999-01-01") }}'
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

with_implied_speed as (
    select
        *,
        -- Haversine distance in nautical miles
        3440.065 * 2 * asin(sqrt(
            pow(sin(radians(latitude - prev_lat) / 2), 2) +
            cos(radians(prev_lat)) * cos(radians(latitude)) *
            pow(sin(radians(longitude - prev_lon) / 2), 2)
        )) as distance_nm,
        timestampdiff(second, prev_ts, base_date_time) / 3600.0 as elapsed_hours
    from vessel_timeline
    where prev_ts is not null
      and timestampdiff(second, prev_ts, base_date_time) > 0
),

impossible as (
    select
        *,
        distance_nm / elapsed_hours as implied_speed_knots
    from with_implied_speed
    -- 30 knots: conservative physical ceiling for cargo/tanker vessels
    where distance_nm / elapsed_hours > 30
      {% if apply_window %}
      and cast(base_date_time as date)
          between date'{{ var("start_date", "2999-01-01") }}' and date'{{ var("end_date", "2999-01-01") }}'
      {% endif %}
)

select
    mmsi,
    vessel_name,
    prev_ts        as event_start,
    base_date_time as event_end,
    prev_lat       as from_lat,
    prev_lon       as from_lon,
    latitude       as to_lat,
    longitude      as to_lon,
    distance_nm,
    implied_speed_knots,
    cast(base_date_time as date)                   as event_date,
    'impossible_speed'                             as anomaly_type,
    least((implied_speed_knots - 30) / 70.0, 1.0)  as anomaly_score
from impossible
