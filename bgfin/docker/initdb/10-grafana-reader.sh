#!/bin/sh
# Read-only role for Grafana. Runs once, when the database volume is created.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v pw="$GRAFANA_DB_PASSWORD" <<'SQL'
CREATE ROLE grafana_reader LOGIN PASSWORD :'pw';
CREATE SCHEMA IF NOT EXISTS bgfin AUTHORIZATION bgfin;
GRANT USAGE ON SCHEMA bgfin TO grafana_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE bgfin IN SCHEMA bgfin GRANT SELECT ON TABLES TO grafana_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE bgfin IN SCHEMA bgfin GRANT EXECUTE ON FUNCTIONS TO grafana_reader;
ALTER ROLE grafana_reader SET search_path = bgfin, public;
SQL
