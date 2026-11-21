-- Read-side views and functions. Safe to re-run (CREATE OR REPLACE).
SET search_path = bgfin, public;

-- Views are rebuilt on every `bgfin init`, so their definitions can change freely.
DROP VIEW IF EXISTS v_threshold_status, v_source_health, v_freshness, v_forecast_revisions,
    v_forecast_vs_actual, v_changes, v_indicator_values, v_first_vs_latest, v_revisions,
    v_obs_current CASCADE;

CREATE OR REPLACE FUNCTION freq_step(freq text) RETURNS interval
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE freq
        WHEN 'A' THEN interval '1 year'
        WHEN 'S' THEN interval '6 months'
        WHEN 'Q' THEN interval '3 months'
        WHEN 'M' THEN interval '1 month'
        WHEN 'W' THEN interval '7 days'
        ELSE interval '1 day' END
$$;

-- Days after the end of a period by which a new value is normally published.
CREATE OR REPLACE FUNCTION freq_default_lag_days(freq text) RETURNS int
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE freq
        WHEN 'A' THEN 550 WHEN 'S' THEN 270 WHEN 'Q' THEN 160
        WHEN 'M' THEN 80  WHEN 'W' THEN 21  ELSE 10 END
$$;

-- Current version of every raw observation.
CREATE OR REPLACE VIEW v_obs_current AS
SELECT o.id AS obs_id, s.id AS series_id, s.source_code, s.dataset, s.source_key,
       s.indicator_code, s.role, s.geo, s.geo_scope, s.unit, s.frequency, s.adjustment,
       s.is_forecast, o.period, o.period_label, o.vintage, o.value, o.status, o.obs_type,
       o.revision, o.retrieved_at, o.published_at
FROM observation o
JOIN series s ON s.id = o.series_id
WHERE o.superseded_at IS NULL;

-- Reproducible historical query: the database as it looked at a given time.
CREATE OR REPLACE FUNCTION obs_as_of(as_of timestamptz)
RETURNS TABLE (obs_id bigint, series_id int, period date, period_label text, vintage text,
               value double precision, status text, obs_type text, revision int,
               retrieved_at timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT o.id, o.series_id, o.period, o.period_label, o.vintage, o.value, o.status,
           o.obs_type, o.revision, o.retrieved_at
    FROM observation o
    WHERE o.retrieved_at <= as_of
      AND (o.superseded_at IS NULL OR o.superseded_at > as_of)
$$;

-- Every revision with the value it replaced.
CREATE OR REPLACE VIEW v_revisions AS
SELECT s.source_code, s.indicator_code, s.geo, s.source_key, o.series_id, o.period,
       o.period_label, o.vintage, o.revision,
       prev.value AS previous_value, o.value AS new_value,
       o.value - prev.value AS delta,
       prev.status AS previous_status, o.status AS new_status,
       prev.retrieved_at AS previous_retrieved_at, o.retrieved_at
FROM observation o
JOIN observation prev ON prev.series_id = o.series_id AND prev.period = o.period
     AND prev.vintage = o.vintage AND prev.revision = o.revision - 1
JOIN series s ON s.id = o.series_id
WHERE o.revision > 0;

-- First published value vs current value (total revision since first seen).
CREATE OR REPLACE VIEW v_first_vs_latest AS
SELECT s.source_code, s.indicator_code, s.geo, o.series_id, o.period, o.period_label,
       o.vintage, f.value AS first_value, o.value AS latest_value,
       o.value - f.value AS total_revision, o.revision AS revisions
FROM observation o
JOIN observation f ON f.series_id = o.series_id AND f.period = o.period
     AND f.vintage = o.vintage AND f.revision = 0
JOIN series s ON s.id = o.series_id
WHERE o.superseded_at IS NULL;

-- Raw and derived values side by side, mapped to indicators.
CREATE OR REPLACE VIEW v_indicator_values AS
SELECT 'raw'::text AS origin, c.indicator_code, c.source_code, c.role, c.geo, c.frequency,
       c.adjustment, c.unit, c.period, c.period_label, c.vintage, c.value, c.obs_type,
       c.series_id, NULL::text AS metric
FROM v_obs_current c
WHERE c.indicator_code IS NOT NULL
UNION ALL
SELECT 'derived', d.indicator_code, d.source_code,
       CASE WHEN d.vintage <> '' THEN 'forecast' ELSE 'primary' END,
       d.geo, d.frequency, 'NSA', d.unit, d.period, d.period_label, d.vintage, d.value,
       d.obs_type, NULL, d.metric
FROM derived_observation d
WHERE d.superseded_at IS NULL AND d.indicator_code IS NOT NULL;

-- Period-on-period and year-on-year changes of current actual values.
-- *_diff is an absolute difference (percentage points for rates),
-- *_pct is a relative change in percent (meaningful for levels and indices).
CREATE OR REPLACE VIEW v_changes AS
WITH v AS (
    SELECT coalesce(series_id::text, 'derived:' || metric || ':' || source_code || ':' || geo) AS skey,
           *
    FROM v_indicator_values
    WHERE vintage = '' AND frequency IN ('M', 'Q', 'S', 'A')
)
SELECT c.skey, c.origin, c.series_id, c.metric, c.source_code, c.indicator_code, c.role,
       c.geo, c.frequency, c.adjustment, c.unit, c.period, c.period_label, c.value, c.obs_type,
       c.value - p.value AS pop_diff,
       CASE WHEN p.value <> 0 THEN 100 * (c.value / p.value - 1) END AS pop_pct,
       c.value - y.value AS yoy_diff,
       CASE WHEN y.value <> 0 THEN 100 * (c.value / y.value - 1) END AS yoy_pct
FROM v c
LEFT JOIN v p ON p.skey = c.skey AND p.period = (c.period - freq_step(c.frequency))::date
LEFT JOIN v y ON y.skey = c.skey AND y.period = (c.period - interval '1 year')::date;

-- Forecasts of each vintage against the benchmark actual for the same year.
CREATE OR REPLACE VIEW v_forecast_vs_actual AS
WITH fc AS (
    SELECT * FROM v_indicator_values WHERE obs_type = 'forecast' AND vintage <> ''
), act AS (
    SELECT DISTINCT ON (indicator_code, geo, frequency, period)
           indicator_code, geo, frequency, period, value, source_code, obs_type
    FROM v_indicator_values
    WHERE role IN ('benchmark', 'primary') AND vintage = '' AND obs_type <> 'forecast'
    ORDER BY indicator_code, geo, frequency, period, (role = 'benchmark') DESC, origin DESC
)
SELECT fc.indicator_code, fc.geo, fc.frequency, fc.period, fc.period_label,
       fc.source_code AS forecaster, fc.vintage, fc.value AS forecast_value,
       act.value AS actual_value, act.source_code AS actual_source,
       act.obs_type AS actual_status, fc.value - act.value AS forecast_error
FROM fc
LEFT JOIN act ON act.indicator_code = fc.indicator_code AND act.geo = fc.geo
     AND act.frequency = fc.frequency AND act.period = fc.period;

-- Forecast revisions: how each forecaster's number for a target year moved between vintages.
CREATE OR REPLACE VIEW v_forecast_revisions AS
SELECT indicator_code, geo, period, period_label, source_code AS forecaster, vintage, value,
       value - lag(value) OVER w AS change_vs_previous_vintage,
       lag(vintage) OVER w AS previous_vintage
FROM v_indicator_values
WHERE obs_type = 'forecast' AND vintage <> ''
WINDOW w AS (PARTITION BY indicator_code, geo, period, source_code ORDER BY vintage);

-- Freshness of every series.
CREATE OR REPLACE VIEW v_freshness AS
SELECT s.id AS series_id, s.source_code, s.indicator_code, s.role, s.geo, s.source_key,
       s.frequency, s.last_checked_at, s.last_changed_at, s.source_updated_at,
       max(o.period) AS latest_period,
       (max(o.period) + freq_step(s.frequency))::date AS latest_period_end,
       coalesce((s.attrs->>'max_lag_days')::int, freq_default_lag_days(s.frequency)) AS max_lag_days,
       (current_date - (max(o.period) + freq_step(s.frequency))::date) AS days_since_period_end,
       (current_date - (max(o.period) + freq_step(s.frequency))::date)
           > coalesce((s.attrs->>'max_lag_days')::int, freq_default_lag_days(s.frequency)) AS is_stale
FROM series s
LEFT JOIN observation o ON o.series_id = s.id AND o.superseded_at IS NULL
     AND o.obs_type <> 'forecast' AND o.value IS NOT NULL
WHERE NOT s.is_forecast
GROUP BY s.id;

-- Latest run per source.
CREATE OR REPLACE VIEW v_source_health AS
SELECT src.code AS source_code, src.name, src.enabled, src.interval_hours,
       last_run.started_at AS last_run_at, last_run.status AS last_status,
       last_run.message AS last_message, last_ok.finished_at AS last_success_at,
       (SELECT count(*) FROM collection_run r WHERE r.source_code = src.code
          AND r.status = 'failed' AND r.started_at > now() - interval '7 days') AS failures_7d
FROM source src
LEFT JOIN LATERAL (SELECT * FROM collection_run r WHERE r.source_code = src.code
                   ORDER BY started_at DESC LIMIT 1) last_run ON true
LEFT JOIN LATERAL (SELECT * FROM collection_run r WHERE r.source_code = src.code
                   AND r.status IN ('ok', 'partial') ORDER BY started_at DESC LIMIT 1) last_ok ON true;

-- Latest value of each threshold's primary series against the threshold.
CREATE OR REPLACE VIEW v_threshold_status AS
WITH latest AS (
    SELECT DISTINCT ON (t.name) t.name, t.indicator_code, t.geo, t.measure, t.operator,
           t.threshold, t.severity, t.description, ch.period_label, ch.source_code,
           CASE t.measure WHEN 'level' THEN ch.value
                          WHEN 'change_pop' THEN ch.pop_diff
                          ELSE ch.yoy_diff END AS observed
    FROM alert_threshold t
    JOIN indicator i ON i.code = t.indicator_code
    JOIN v_changes ch ON ch.indicator_code = t.indicator_code AND ch.geo = t.geo
         AND ch.role IN ('primary', 'benchmark') AND ch.frequency = coalesce(t.frequency, i.frequency)
         AND ch.value IS NOT NULL
    ORDER BY t.name, ch.period DESC, (ch.role = 'primary') DESC
)
SELECT *, CASE operator
            WHEN '>'  THEN observed >  threshold
            WHEN '>=' THEN observed >= threshold
            WHEN '<'  THEN observed <  threshold
            ELSE           observed <= threshold END AS breached
FROM latest;
