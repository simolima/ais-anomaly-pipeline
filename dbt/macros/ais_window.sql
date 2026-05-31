{% macro ais_window() %}
    {#-
      Resolves the [start, end] processing window for the incremental models from the
      start_date / end_date vars. Both are normally supplied by the `compute_window` job
      task (next 7-day window after the max already-processed date, mirroring the bronze
      ingestion), or set explicitly for a manual reprocess. Empty strings (the job-parameter
      defaults) and the missing case both fall through to the 2999-01-01 sentinel, which
      makes a run a no-op — or, with --full-refresh, a full build (the filter is skipped
      when is_incremental() is false). Returns a list [start, end, has_window].
    -#}
    {% set start = var('start_date', none) %}
    {% set end   = var('end_date', none) %}
    {% if start and end %}
        {% do return([start | string, end | string, true]) %}
    {% endif %}

    {% do return(['2999-01-01', '2999-01-01', false]) %}
{% endmacro %}
