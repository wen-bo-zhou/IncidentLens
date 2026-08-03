#!/bin/sh
set -eu

umask 077

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
POSTGRES_DB="${POSTGRES_DB:-incidentlens}"
POSTGRES_USER="${POSTGRES_USER:-incidentlens}"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

case "$BACKUP_INTERVAL_SECONDS" in
  ''|*[!0-9]*) echo "BACKUP_INTERVAL_SECONDS must be a positive integer" >&2; exit 2 ;;
esac
case "$BACKUP_RETENTION_DAYS" in
  ''|*[!0-9]*) echo "BACKUP_RETENTION_DAYS must be a non-negative integer" >&2; exit 2 ;;
esac
if [ "$BACKUP_INTERVAL_SECONDS" -lt 1 ]; then
  echo "BACKUP_INTERVAL_SECONDS must be a positive integer" >&2
  exit 2
fi

mkdir -p /backups
temporary=""

cleanup() {
  rm -f "${temporary:-}"
}
trap cleanup EXIT HUP INT TERM

while true; do
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  destination="/backups/incidentlens-${timestamp}.dump"
  temporary="${destination}.tmp"

  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host postgres \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --format custom \
    --file "$temporary"
  pg_restore --list "$temporary" >/dev/null
  mv "$temporary" "$destination"
  temporary=""
  find /backups -type f -name 'incidentlens-*.dump' \
    -mtime "+$BACKUP_RETENTION_DAYS" -delete
  touch /tmp/incidentlens-backup-ready
  sleep "$BACKUP_INTERVAL_SECONDS"
done
