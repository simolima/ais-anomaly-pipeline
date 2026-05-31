{%- set win = ais_window() -%}
{{ config(
    materialized='incremental',
    incremental_strategy='replace_where',
    incremental_predicates=[
        "event_date >= date'" ~ win[0] ~ "' and event_date <= date'" ~ win[1] ~ "'"
    ]
) }}

-- Window-driven incremental model. The window is resolved by ais_window():
--   * explicit:   dbt run --vars '{start_date: X, end_date: Y}'  (manual run / reprocess)
--   * scheduled:  the Databricks compute_window task passes the next watermark window
--   * full:       dbt run --full-refresh                         (no vars -> all history)
-- A windowed run atomically deletes+reinserts only the days in the window.
{%- set window_start = win[0] -%}
{%- set window_end   = win[1] -%}
{%- set has_window   = win[2] -%}
-- Apply the window on any incremental run (no vars -> default 2999-01-01 -> true no-op
-- matching the replace_where predicate) and on a windowed/first build. Only a full build
-- with no vars reads all history.
{%- set apply_window = has_window or is_incremental() -%}

with source as (
    select * from {{ source('bronze', 'ais_raw') }}
    {% if apply_window %}
    where cast(base_date_time as date) between date'{{ window_start }}' and date'{{ window_end }}'
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
