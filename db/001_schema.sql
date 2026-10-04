-- WatSen — core schema
-- Frozen on day 3. Any change after that costs the whole team.
-- Run: psql $DATABASE_URL -f db/001_schema.sql

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────────
-- 1. Geography
-- ─────────────────────────────────────────────────────────────

-- A monitored reach of river. Geometry is a LINESTRING in WGS84.
CREATE TABLE IF NOT EXISTS stream_segment (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            TEXT UNIQUE NOT NULL,          -- human key, e.g. 'PT-MND-03'
    name            TEXT NOT NULL,
    water_body      TEXT,
    city            TEXT,
    country_iso2    CHAR(2),
    geom            geometry(LineString, 4326) NOT NULL,
    centroid        geometry(Point, 4326)
                    GENERATED ALWAYS AS (ST_Centroid(geom)) STORED,
    length_m        DOUBLE PRECISION,
    -- catchment context, filled by the OSM land-use job
    impervious_pct  REAL,
    industry_within_1km INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_segment_geom ON stream_segment USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_segment_centroid ON stream_segment USING GIST (centroid);
CREATE INDEX IF NOT EXISTS ix_segment_city ON stream_segment (city);

-- A fixed sensor or sampling point bound to a segment.
CREATE TABLE IF NOT EXISTS station (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    segment_id   UUID NOT NULL REFERENCES stream_segment(id) ON DELETE CASCADE,
    external_id  TEXT,                              -- id in the upstream provider
    source       TEXT NOT NULL,                     -- 'openaq' | 'manual' | 'oneaquahealth'
    geom         geometry(Point, 4326) NOT NULL,
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS ix_station_geom ON station USING GIST (geom);

-- ─────────────────────────────────────────────────────────────
-- 2. Measurements  (the time series the forecaster trains on)
-- ─────────────────────────────────────────────────────────────

-- Long format on purpose: providers disagree about which variables exist.
CREATE TABLE IF NOT EXISTS measurement (
    id           BIGSERIAL PRIMARY KEY,
    segment_id   UUID NOT NULL REFERENCES stream_segment(id) ON DELETE CASCADE,
    station_id   UUID REFERENCES station(id) ON DELETE SET NULL,
    observed_at  TIMESTAMPTZ NOT NULL,
    variable     TEXT NOT NULL,      -- do_mgl | ph | turbidity_ntu | temp_c | rain_mm | nitrate_mgl
    value        DOUBLE PRECISION NOT NULL,
    unit         TEXT NOT NULL,
    source       TEXT NOT NULL,      -- openaq | openweather | citizen | copernicus | synthetic
    quality      REAL NOT NULL DEFAULT 1.0,  -- 0..1, written by the harmoniser
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_measurement_dedupe
    ON measurement (segment_id, variable, observed_at, source);
CREATE INDEX IF NOT EXISTS ix_measurement_series
    ON measurement (segment_id, variable, observed_at DESC);

-- ─────────────────────────────────────────────────────────────
-- 3. Citizen observations  (what the vision model consumes)
-- ─────────────────────────────────────────────────────────────

CREATE TYPE review_state AS ENUM ('pending', 'auto_accepted', 'needs_review', 'expert_confirmed', 'rejected');

CREATE TABLE IF NOT EXISTS contributor (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    handle        TEXT UNIQUE NOT NULL,
    joined_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- rolling mean of observation.quality_score, refreshed nightly
    trust_score   REAL NOT NULL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS observation (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    segment_id     UUID REFERENCES stream_segment(id) ON DELETE SET NULL,
    contributor_id UUID REFERENCES contributor(id) ON DELETE SET NULL,
    observed_at    TIMESTAMPTZ NOT NULL,
    geom           geometry(Point, 4326) NOT NULL,
    note           TEXT,
    photo_uri      TEXT,
    -- model output
    predicted_taxon   TEXT,
    taxon_confidence  REAL,
    bmwp_contribution SMALLINT,
    quality_score     REAL,            -- 0..1 from the anomaly detector
    anomaly_reasons   JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation       TEXT,            -- plain-language, shown to the contributor
    saliency_uri      TEXT,            -- Grad-CAM overlay
    state          review_state NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_observation_geom ON observation USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_observation_segment ON observation (segment_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_observation_state ON observation (state);

-- ─────────────────────────────────────────────────────────────
-- 4. Derived state  (what the map and the brief read)
-- ─────────────────────────────────────────────────────────────

-- One row per segment per day: the composite stress index.
CREATE TABLE IF NOT EXISTS stress_index (
    segment_id   UUID NOT NULL REFERENCES stream_segment(id) ON DELETE CASCADE,
    day          DATE NOT NULL,
    value        REAL NOT NULL,          -- 0 (healthy) .. 100 (severe stress)
    band         TEXT NOT NULL,          -- good | fair | poor | severe
    components   JSONB NOT NULL,         -- {"do":..,"turbidity":..,"temp":..,"bmwp":..}
    n_inputs     INT NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (segment_id, day)
);

-- Forecast runs are append-only so we can measure our own accuracy later.
CREATE TABLE IF NOT EXISTS forecast_run (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    segment_id   UUID NOT NULL REFERENCES stream_segment(id) ON DELETE CASCADE,
    issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version TEXT NOT NULL,
    horizon_h    INT NOT NULL DEFAULT 72
);
CREATE TABLE IF NOT EXISTS forecast_point (
    run_id       UUID NOT NULL REFERENCES forecast_run(id) ON DELETE CASCADE,
    valid_at     TIMESTAMPTZ NOT NULL,
    value        REAL NOT NULL,
    lower        REAL NOT NULL,          -- 10th percentile
    upper        REAL NOT NULL,          -- 90th percentile
    PRIMARY KEY (run_id, valid_at)
);

CREATE TABLE IF NOT EXISTS alert (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    segment_id   UUID NOT NULL REFERENCES stream_segment(id) ON DELETE CASCADE,
    run_id       UUID REFERENCES forecast_run(id) ON DELETE SET NULL,
    raised_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from   TIMESTAMPTZ NOT NULL,
    severity     TEXT NOT NULL,          -- watch | warning | critical
    hazard       TEXT NOT NULL,          -- do_crash | bloom_risk | runoff_spike
    headline     TEXT NOT NULL,
    audience     TEXT NOT NULL DEFAULT 'public',  -- public | agency | researcher
    acknowledged BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_alert_open ON alert (segment_id, raised_at DESC);

-- The One Health brief. `evidence` is the retrieved record set; nothing in
-- `body` may cite anything that is not in it.
CREATE TABLE IF NOT EXISTS health_brief (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    segment_id   UUID NOT NULL REFERENCES stream_segment(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end   DATE NOT NULL,
    headline     TEXT NOT NULL,
    body         TEXT NOT NULL,
    risk_level   TEXT NOT NULL,          -- low | moderate | high
    evidence     JSONB NOT NULL,
    model        TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_brief_segment ON health_brief (segment_id, period_end DESC);

-- ─────────────────────────────────────────────────────────────
-- 5. Convenience view for the map layer
-- ─────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW segment_current AS
SELECT
    s.id,
    s.code,
    s.name,
    s.city,
    ST_AsGeoJSON(s.geom)::jsonb      AS geometry,
    ST_Y(s.centroid)                 AS lat,
    ST_X(s.centroid)                 AS lon,
    si.value                         AS stress,
    si.band,
    si.day                           AS stress_day,
    (SELECT count(*) FROM observation o
      WHERE o.segment_id = s.id
        AND o.observed_at > now() - interval '30 days') AS observations_30d,
    (SELECT count(*) FROM alert a
      WHERE a.segment_id = s.id AND a.acknowledged = false) AS open_alerts
FROM stream_segment s
LEFT JOIN LATERAL (
    SELECT * FROM stress_index x
     WHERE x.segment_id = s.id
     ORDER BY x.day DESC LIMIT 1
) si ON true;
