-- bgfin core schema.
--
-- Principles:
--   * Raw observations are append-only. A changed value never overwrites the
--     old row: the old row gets superseded_at set and a new row with
--     revision + 1 is inserted. "As of" queries are therefore reproducible.
--   * Forecasts are keyed by vintage (e.g. "WEO-2026-10"), so each forecast
--     round is kept side by side with actuals and with earlier rounds.
--   * Derived metrics live in their own table and never mix with raw data.

CREATE SCHEMA IF NOT EXISTS bgfin;
SET search_path = bgfin, public;

CREATE TABLE IF NOT EXISTS source (
    code            text PRIMARY KEY,               -- eurostat, ecb, imf ...
    name            text NOT NULL,
    institution     text NOT NULL,
    homepage        text,
    api_base        text,
    formats         text[],
    notes           text,
    enabled         boolean NOT NULL DEFAULT true,
    interval_hours  double precision NOT NULL DEFAULT 24,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE source ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;
ALTER TABLE source ADD COLUMN IF NOT EXISTS interval_hours double precision NOT NULL DEFAULT 24;

CREATE TABLE IF NOT EXISTS indicator (
    code            text PRIMARY KEY,               -- hicp_inflation ...
    name            text NOT NULL,
    category        text NOT NULL,                  -- activity, inflation ...
    description     text,
    unit            text NOT NULL,                  -- canonical unit label
    frequency       text NOT NULL,                  -- canonical frequency
    priority        boolean NOT NULL DEFAULT false,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- One concrete time series at one source.
CREATE TABLE IF NOT EXISTS series (
    id              serial PRIMARY KEY,
    source_code     text NOT NULL REFERENCES source(code),
    source_key      text NOT NULL,                  -- full source identifier
    dataset         text NOT NULL,
    indicator_code  text REFERENCES indicator(code),
    role            text NOT NULL DEFAULT 'primary'
                    CHECK (role IN ('primary', 'secondary', 'benchmark', 'forecast', 'input')),
    geo             text NOT NULL,                  -- ISO 3166 alpha-2 or aggregate (EU27_2020, EA21)
    geo_scope       text NOT NULL DEFAULT 'country'
                    CHECK (geo_scope IN ('country', 'aggregate')),
    label           text,
    unit            text NOT NULL,
    frequency       text NOT NULL CHECK (frequency IN ('D', 'B', 'W', 'M', 'Q', 'S', 'A')),
    adjustment      text NOT NULL DEFAULT 'NSA',    -- NSA, SA, SCA, CA, TC
    is_forecast     boolean NOT NULL DEFAULT false,
    attrs           jsonb NOT NULL DEFAULT '{}',    -- dimension values, source metadata
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_checked_at timestamptz,
    last_changed_at timestamptz,
    source_updated_at timestamptz,                  -- dataset "last updated" reported by source
    UNIQUE (source_code, source_key)
);
CREATE INDEX IF NOT EXISTS series_indicator_idx ON series (indicator_code, geo);

CREATE TABLE IF NOT EXISTS collection_run (
    id              bigserial PRIMARY KEY,
    source_code     text NOT NULL REFERENCES source(code),
    mode            text NOT NULL CHECK (mode IN ('backfill', 'incremental')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'ok', 'partial', 'failed', 'skipped')),
    requests        int NOT NULL DEFAULT 0,
    series_seen     int NOT NULL DEFAULT 0,
    obs_new         int NOT NULL DEFAULT 0,
    obs_revised     int NOT NULL DEFAULT 0,
    obs_unchanged   int NOT NULL DEFAULT 0,
    errors          jsonb NOT NULL DEFAULT '[]',
    message         text
);
CREATE INDEX IF NOT EXISTS collection_run_source_idx ON collection_run (source_code, started_at DESC);

-- Raw observations, every retrieved version.
CREATE TABLE IF NOT EXISTS observation (
    id              bigserial PRIMARY KEY,
    series_id       int NOT NULL REFERENCES series(id),
    period          date NOT NULL,                  -- first day of the period
    period_label    text NOT NULL,                  -- as published: 2026-Q3, 2026-10, 2026
    vintage         text NOT NULL DEFAULT '',       -- '' for actuals, release id for forecasts
    value           double precision,               -- NULL when the source flags a missing value
    status          text,                           -- raw source flag(s): p, e, b, A, P, (..)
    obs_type        text NOT NULL
                    CHECK (obs_type IN ('actual', 'preliminary', 'estimate', 'forecast', 'missing')),
    revision        int NOT NULL DEFAULT 0,         -- 0 = first value we retrieved
    retrieved_at    timestamptz NOT NULL DEFAULT now(),
    published_at    timestamptz,                    -- source release / update timestamp
    superseded_at   timestamptz,                    -- set when a newer version arrives
    run_id          bigint REFERENCES collection_run(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS observation_current_uq
    ON observation (series_id, period, vintage) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS observation_series_period_idx
    ON observation (series_id, period, vintage, retrieved_at);

-- Per-dataset state for conditional / incremental requests.
CREATE TABLE IF NOT EXISTS dataset_state (
    source_code     text NOT NULL REFERENCES source(code),
    dataset         text NOT NULL,
    etag            text,
    last_modified   text,
    source_updated  text,
    checked_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_code, dataset)
);

-- Derived metrics. Same versioning as raw data, plus the inputs used.
CREATE TABLE IF NOT EXISTS derived_observation (
    id              bigserial PRIMARY KEY,
    metric          text NOT NULL,                  -- e.g. real_wage_growth
    indicator_code  text REFERENCES indicator(code),
    source_code     text NOT NULL,                  -- origin of the inputs
    geo             text NOT NULL,
    frequency       text NOT NULL,
    period          date NOT NULL,
    period_label    text NOT NULL,
    vintage         text NOT NULL DEFAULT '',
    value           double precision,
    unit            text NOT NULL,
    obs_type        text NOT NULL,
    method          text NOT NULL,                  -- human readable formula
    inputs          jsonb NOT NULL,                 -- observation ids and values used
    revision        int NOT NULL DEFAULT 0,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    superseded_at   timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS derived_current_uq
    ON derived_observation (metric, source_code, geo, period, vintage) WHERE superseded_at IS NULL;

-- Validation and anomaly findings.
CREATE TABLE IF NOT EXISTS quality_issue (
    id              bigserial PRIMARY KEY,
    check_name      text NOT NULL,                  -- stale, outlier_change, large_revision ...
    severity        text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    series_id       int REFERENCES series(id),
    source_code     text,
    period          date,
    detail          jsonb NOT NULL DEFAULT '{}',
    first_detected_at timestamptz NOT NULL DEFAULT now(),
    last_detected_at  timestamptz NOT NULL DEFAULT now(),
    resolved_at     timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS quality_issue_open_uq
    ON quality_issue (check_name, coalesce(source_code, ''), coalesce(series_id, 0),
                      coalesce(period, '1900-01-01'::date))
    WHERE resolved_at IS NULL;

-- Configurable alert thresholds (loaded from config/alerts.yaml).
CREATE TABLE IF NOT EXISTS alert_threshold (
    name            text PRIMARY KEY,
    indicator_code  text NOT NULL REFERENCES indicator(code),
    geo             text NOT NULL DEFAULT 'BG',
    frequency       text,                           -- NULL: the indicator's canonical frequency
    measure         text NOT NULL DEFAULT 'level'
                    CHECK (measure IN ('level', 'change_pop', 'change_yoy')),
    operator        text NOT NULL CHECK (operator IN ('>', '>=', '<', '<=')),
    threshold       double precision NOT NULL,
    severity        text NOT NULL DEFAULT 'warning',
    description     text
);

CREATE TABLE IF NOT EXISTS schema_version (
    version         int PRIMARY KEY,
    applied_at      timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_version (version) VALUES (1) ON CONFLICT DO NOTHING;
