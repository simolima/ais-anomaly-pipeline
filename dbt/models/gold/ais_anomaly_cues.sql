{%- set win = ais_window() -%}
{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ win[0] ~ "' and event_date <= date'" ~ win[1] ~ "'"
    ]
) }}

{%- set window_start = win[0] -%}
{%- set window_end   = win[1] -%}
{%- set has_window   = win[2] -%}
-- Windowed incremental. event_date is carried up unchanged from the gold anomaly tables
-- (date of the in-window detecting ping), so the same window predicate applies cleanly.
{% set apply_window = has_window or is_incremental() %}

with dark_gaps as (
    select
        mmsi, vessel_name,
        gap_start        as event_ts,
        last_known_lat   as lat,
        last_known_lon   as lon,
        event_date,
        anomaly_type,
        anomaly_score
    from {{ ref('ais_dark_gaps') }}
    {% if apply_window %}
    where event_date between date'{{ window_start }}' and date'{{ window_end }}'
    {% endif %}
),

impossible_speeds as (
    select
        mmsi, vessel_name,
        event_start      as event_ts,
        from_lat         as lat,
        from_lon         as lon,
        event_date,
        anomaly_type,
        anomaly_score
    from {{ ref('ais_impossible_speed') }}
    {% if apply_window %}
    where event_date between date'{{ window_start }}' and date'{{ window_end }}'
    {% endif %}
),

all_anomalies as (
    select * from dark_gaps
    union all
    select * from impossible_speeds
),

-- Join OpenSanctions on MMSI (best available public key)
enriched as (
    select
        a.*,
        s.entity_name      as sanctions_match,
        s.sanctions_list,
        s.designation_date
    from all_anomalies a
    left join {{ source('bronze', 'sanctions') }} s
        on a.mmsi = s.mmsi
)

select * from enriched
order by anomaly_score desc
