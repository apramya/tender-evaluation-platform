#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required"
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/tender_db_$TIMESTAMP.sql.gz"
find "$BACKUP_DIR" -name "tender_db_*.sql.gz" -mtime "+$RETENTION_DAYS" -delete

echo "Backup written to $BACKUP_DIR/tender_db_$TIMESTAMP.sql.gz"
