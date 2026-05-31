{% macro ais_window() %}
    {#-
      Resolves the [start, end] processing window for the incremental models, in
      priority order:
        1. explicit start_date + end_date vars  -> manual run / reprocess a window
        2. rolling_days var                      -> scheduled run: last N days [today-N, today]
        3. neither                               -> 2999-01-01 sentinel (no-op, or full build
                                                    when combined with --full-refresh)
      Empty strings (the job-parameter defaults) count as "not set" — Jinja treats
      them as falsy. Returns a list [start, end, has_window].
    -#}
    {% set start = var('start_date', none) %}
    {% set end   = var('end_date', none) %}
    {% if start and end %}
        {% do return([start | string, end | string, true]) %}
    {% endif %}

    {% set rolling = var('rolling_days', none) %}
    {% if rolling %}
        {% set today = modules.datetime.datetime.utcnow().date() %}
        {% set s = (today - modules.datetime.timedelta(days=rolling | int)).strftime('%Y-%m-%d') %}
        {% do return([s, today.strftime('%Y-%m-%d'), true]) %}
    {% endif %}

    {% do return(['2999-01-01', '2999-01-01', false]) %}
{% endmacro %}
