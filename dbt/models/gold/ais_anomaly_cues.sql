{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ var('start_date', '2999-01-01') ~ "' and event_date <= date'" ~ var('end_date', '2999-01-01') ~ "'"
    ]
) }}

-- Windowed incremental. event_date is carried up unchanged from the gold anomaly tables
-- (date of the in-window detecting ping), so the same window predicate applies cleanly.
{% set has_window = var('start_date', none) is not none %}

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
    {% if has_window %}
    where event_date between date'{{ var("start_date") }}' and date'{{ var("end_date") }}'
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
    {% if has_window %}
    where event_date between date'{{ var("start_date") }}' and date'{{ var("end_date") }}'
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
