{{ config(materialized='table') }}

with dark_gaps as (
    select
        mmsi, vessel_name,
        gap_start        as event_ts,
        last_known_lat   as lat,
        last_known_lon   as lon,
        anomaly_type,
        anomaly_score
    from {{ ref('ais_dark_gaps') }}
),

impossible_speeds as (
    select
        mmsi, vessel_name,
        event_start      as event_ts,
        from_lat         as lat,
        from_lon         as lon,
        anomaly_type,
        anomaly_score
    from {{ ref('ais_impossible_speed') }}
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
        on a.MMSI = s.mmsi
)

select * from enriched
order by anomaly_score desc
