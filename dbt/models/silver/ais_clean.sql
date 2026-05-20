{{ config(materialized='table') }}

with source as (
    select * from {{ source('bronze', 'ais_raw') }}
),

-- 1. Remove exact duplicates (same MMSI + same timestamp)
deduplicated as (
    select *
    from source
    qualify row_number() over (
        partition by MMSI, BaseDateTime
        order by _ingestion_ts desc
    ) = 1
),

-- 2. Remove stale retransmissions: identical position/speed/course with different timestamp
no_retransmissions as (
    select *
    from deduplicated
    qualify row_number() over (
        partition by MMSI, LAT, LON, SOG, COG
        order by BaseDateTime
    ) = 1
),

-- 3. Tag coordinate and speed errors; drop them
validated as (
    select *,
        case
            when LAT  < -90   or LAT  > 90    then 'invalid_lat'
            when LON  < -180  or LON  > 180   then 'invalid_lon'
            when SOG  < 0     or SOG  > 102.2 then 'invalid_sog'
            else null
        end as quality_flag
    from no_retransmissions
)

select * from validated
where quality_flag is null
