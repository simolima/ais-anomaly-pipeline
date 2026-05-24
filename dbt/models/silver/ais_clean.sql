{{ config(materialized='table') }}

with source as (
    select * from {{ source('bronze', 'ais_raw') }}
),

-- 1. Remove exact duplicates (same mmsi + same timestamp)
deduplicated as (
    select *
    from source
    qualify row_number() over (
        partition by mmsi, base_date_time
        order by _ingestion_ts desc
    ) = 1
),

-- 2. Remove stale retransmissions: identical position/speed/course with different timestamp
no_retransmissions as (
    select *
    from deduplicated
    qualify row_number() over (
        partition by mmsi, latitude, longitude, sog, cog
        order by base_date_time
    ) = 1
),

-- 3. Tag coordinate and speed errors; drop them
validated as (
    select *,
        case
            when latitude  < -90   or latitude  > 90    then 'invalid_lat'
            when longitude < -180  or longitude > 180   then 'invalid_lon'
            when sog       < 0     or sog       > 102.2 then 'invalid_sog'
            else null
        end as quality_flag
    from no_retransmissions
)

select * from validated
where quality_flag is null
