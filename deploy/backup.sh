#!/bin/sh
# Nightly backups (spec section 15): pg_dump custom format + tar of ASSET_DIR into /backups, kept 30 days.
#   backup.sh loop   -> runs every day at BACKUP_AT (HH:MM, container local time; TZ env) — the Compose service
#   backup.sh once   -> one backup now (scripts/backup-now.ps1)
set -eu

BACKUP_DIR=/backups
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
AT="${BACKUP_AT:-02:00}"

backup_once() {
  stamp=$(date +%Y%m%d-%H%M%S)
  mkdir -p "$BACKUP_DIR"
  echo "backup $stamp: database"
  PGPASSWORD="$DB_PASSWORD" pg_dump -h db -U label -d label -Fc -f "$BACKUP_DIR/label-$stamp.dump.partial"
  mv "$BACKUP_DIR/label-$stamp.dump.partial" "$BACKUP_DIR/label-$stamp.dump"
  echo "backup $stamp: assets"
  tar -czf "$BACKUP_DIR/assets-$stamp.tar.gz.partial" -C /data assets
  mv "$BACKUP_DIR/assets-$stamp.tar.gz.partial" "$BACKUP_DIR/assets-$stamp.tar.gz"
  find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'label-*.dump' -o -name 'assets-*.tar.gz' \) -mtime +"$KEEP_DAYS" -delete
  echo "backup $stamp: done"
}

case "${1:-loop}" in
  once)
    backup_once
    ;;
  loop)
    echo "nightly backups at $AT, keeping $KEEP_DAYS days"
    while true; do
      now=$(date +%s)
      target=$(date -d "$(date +%Y-%m-%d) $AT" +%s)
      [ "$target" -le "$now" ] && target=$((target + 86400))
      sleep $((target - now))
      backup_once || echo "backup failed" >&2
    done
    ;;
  *)
    echo "usage: backup.sh [loop|once]" >&2
    exit 2
    ;;
esac
