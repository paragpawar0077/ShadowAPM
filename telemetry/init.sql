-- Run automatically by the timescaledb docker image on first startup.
-- Converts telemetry_events into a TimescaleDB hypertable once SQLAlchemy
-- (in common/db.py) has created the plain table on service startup.
--
-- NOTE: this script only enables the extension; the hypertable conversion
-- happens via docker-compose's init step (see scripts/init_hypertable.sh)
-- because the table must exist first, and SQLAlchemy creates it at
-- application startup, not at container startup.
CREATE EXTENSION IF NOT EXISTS timescaledb;
