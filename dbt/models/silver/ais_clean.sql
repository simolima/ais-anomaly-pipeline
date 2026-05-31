{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ var('start_date', '2999-01-01') ~ "' and event_date <= date'" ~ var('end_date', '2999-01-01') ~ "'"
    ]
) }}

-- Window-driven incremental model.
--   * Full (re)build:   dbt run --full-refresh                         (no vars -> all history)
--   * Windowed run:     dbt run --vars '{start_date: X, end_date: Y}'  (replace_where on [X,Y])
-- A windowed run atomically deletes+reinserts only the days in [start_date, end_date].
{% set has_window = var('start_date', none) is not none %}
-- Apply the window filter on any incremental run (with no vars the default 2999-01-01
-- range makes the run a true no-op that matches the replace_where predicate) and on a
-- windowed/first build. Only a full build with no vars reads all history.
{% set apply_window = has_window or is_incremental() %}

with source as (
    select * from {{ source('bronze', 'ais_raw') }}
    {% if apply_window %}
    where cast(base_date_time as date)
          between date'{{ var("start_date", "2999-01-01") }}' and date'{{ var("end_date", "2999-01-01") }}'
    {% endif %}
),

-- Remove exact duplicates (same vessel, same timestamp); keep the latest ingested copy.
deduplicated as (
    select *
    from source
    qualify row_number() over (
        partition by mmsi, base_date_time
        order by _ingestion_ts desc
    ) = 1
),

-- NOTE: the legacy global "no_retransmissions" dedup was removed. It collapsed the
-- timeline of moored vessels (identical lat/lon/sog/cog) to a single row, which made
-- ais_dark_gaps report false gaps for vessels that were in fact transmitting. It was
-- also globally scoped and therefore incompatible with windowed incremental builds.

-- Tag coordinate/speed errors and drop them.
validated as (
    select *,
        case
            when latitude  < -90   or latitude  > 90    then 'invalid_lat'
            when longitude < -180  or longitude > 180   then 'invalid_lon'
            when sog       < 0     or sog       > 102.2 then 'invalid_sog'
            else null
        end as quality_flag
    from deduplicated
)

select
    *,
    cast(base_date_time as date) as event_date
from validated
where quality_flag is null
