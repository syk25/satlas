-- Satlas Database Schema
-- Last updated: 2026-05-06

-- ────────────────────────────────────────
-- TYPES
-- ────────────────────────────────────────

CREATE TYPE orbit_class_type AS ENUM ('LEO', 'MEO', 'GEO', 'HEO');
CREATE TYPE operator_type AS ENUM ('GOVERNMENT', 'MILITARY', 'COMMERCIAL', 'INTERNATIONAL');
-- GOVERNMENT: civil government agencies and academic institutions (NASA, JAXA, universities)
-- MILITARY: defense-purpose satellites
-- COMMERCIAL: private companies (SpaceX, SES, Eutelsat); operator_country = country of legal incorporation
-- INTERNATIONAL: multinational bodies with no single country attribution (ESA, ITU); operator_country = NULL

-- ────────────────────────────────────────
-- SATELLITES
-- ────────────────────────────────────────

CREATE TABLE satellites (
  id               SERIAL PRIMARY KEY,
  norad_id         INTEGER UNIQUE NOT NULL,
  name             TEXT NOT NULL,
  operator_country CHAR(2),                        -- ISO 3166-1 alpha-2 (country of legal incorporation/HQ)
  operator_name    TEXT,                            -- e.g. "SpaceX", "ESA", "Intelsat"
  operator_type    operator_type,                   -- GOVERNMENT / MILITARY / COMMERCIAL / INTERNATIONAL
  orbit_class      orbit_class_type,
  launch_date      DATE,
  is_active        BOOLEAN DEFAULT TRUE,
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- ────────────────────────────────────────
-- TLE SNAPSHOTS
-- ────────────────────────────────────────

CREATE TABLE tle_snapshots (
  id           SERIAL PRIMARY KEY,
  satellite_id INTEGER NOT NULL REFERENCES satellites(id),
  line1        CHAR(69) NOT NULL,
  line2        CHAR(69) NOT NULL,
  epoch        TIMESTAMPTZ NOT NULL,               -- reference epoch of the orbital elements (CelesTrak issue time)
  ingested_at  TIMESTAMPTZ DEFAULT now()           -- timestamp when our system stored this TLE
);

CREATE INDEX ON tle_snapshots (satellite_id, ingested_at DESC);

-- ────────────────────────────────────────
-- PASS EVENTS
-- ────────────────────────────────────────

CREATE TABLE predicted_passes (
  id               SERIAL PRIMARY KEY,
  satellite_id     INTEGER NOT NULL REFERENCES satellites(id),
  country_code     CHAR(2) NOT NULL,
  tle_snapshot_id  INTEGER NOT NULL REFERENCES tle_snapshots(id),
  entry_time       TIMESTAMPTZ NOT NULL,
  exit_time        TIMESTAMPTZ NOT NULL,
  duration_seconds INTEGER NOT NULL,
  entry_lat        REAL,
  entry_lon        REAL,
  exit_lat         REAL,
  exit_lon         REAL,
  predicted_at     TIMESTAMPTZ NOT NULL             -- timestamp when this prediction was generated
);

CREATE INDEX ON predicted_passes (country_code, entry_time);
CREATE INDEX ON predicted_passes (satellite_id, entry_time);

CREATE TABLE actual_passes (
  id                SERIAL PRIMARY KEY,
  satellite_id      INTEGER NOT NULL REFERENCES satellites(id),
  country_code      CHAR(2) NOT NULL,
  tle_snapshot_id   INTEGER NOT NULL REFERENCES tle_snapshots(id),
  entry_time        TIMESTAMPTZ NOT NULL,
  exit_time         TIMESTAMPTZ NOT NULL,
  duration_seconds  INTEGER NOT NULL,
  entry_lat         REAL,
  entry_lon         REAL,
  exit_lat          REAL,
  exit_lon          REAL,
  predicted_pass_id INTEGER REFERENCES predicted_passes(id),  -- nullable
  anomaly_flag      BOOLEAN DEFAULT FALSE
);

CREATE INDEX ON actual_passes (country_code, entry_time);
CREATE INDEX ON actual_passes (satellite_id, entry_time);

-- ────────────────────────────────────────
-- USERS & AUTH
-- ────────────────────────────────────────

CREATE TABLE users (
  id           SERIAL PRIMARY KEY,
  email        TEXT UNIQUE NOT NULL,
  display_name TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE oauth_accounts (
  id               SERIAL PRIMARY KEY,
  user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider         TEXT NOT NULL,                  -- 'github', 'google'
  provider_user_id TEXT NOT NULL,
  created_at       TIMESTAMPTZ DEFAULT now(),
  UNIQUE (provider, provider_user_id)
);

-- Phase 2: dormant until passkey feature is activated (Issue #5)
CREATE TABLE passkey_credentials (
  id            SERIAL PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credential_id TEXT UNIQUE NOT NULL,
  public_key    TEXT NOT NULL,
  sign_count    INTEGER DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- ────────────────────────────────────────
-- BOOKMARKS
-- ────────────────────────────────────────

CREATE TABLE country_bookmarks (
  id           SERIAL PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  country_code CHAR(2) NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, country_code)
);

CREATE TABLE satellite_bookmarks (
  id           SERIAL PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  satellite_id INTEGER NOT NULL REFERENCES satellites(id) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, satellite_id)
);
