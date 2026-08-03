#!/bin/sh
set -eu

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${BACKUP_FILE:?BACKUP_FILE must name a file under /backups}"
POSTGRES_DB="${POSTGRES_DB:-incidentlens}"
POSTGRES_USER="${POSTGRES_USER:-incidentlens}"

case "$BACKUP_FILE" in
  /backups/incidentlens-*.dump) ;;
  *) echo "BACKUP_FILE must name an IncidentLens dump under /backups" >&2; exit 2 ;;
esac
if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 2
fi

PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
  --host postgres \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  "$BACKUP_FILE"
