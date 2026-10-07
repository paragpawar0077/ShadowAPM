#!/bin/sh
# Converts telemetry_events into a TimescaleDB hypertable, partitioned on
# timestamp, for efficient time-series queries as data volume grows.
# Run this ONCE after `docker compose up` has created the tables:
#
#   docker compose exec db psql -U shadowapm -d shadowapm -f /scripts/init_hypertable.sh
#
# (or simply run the SQL below directly with psql / any Postgres client)

set -e
psql -U "${POSTGRES_USER:-shadowapm}" -d "${POSTGRES_DB:-shadowapm}" -c \
  "SELECT create_hypertable('telemetry_events', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
