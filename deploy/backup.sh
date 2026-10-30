#!/bin/sh
# Nightly backups (spec section 15): pg_dump custom format + tar of ASSET_DIR into /backups, kept 30 days.
# v1.1 D25: when BACKUP_COPY_ENABLED is set, each backup is also copied to /backup-copy (a folder off this
# machine: network share, NAS or synced OneDrive folder, mounted from BACKUP_COPY_TO), with the same retention.
# A failed copy is logged and leaves the local backup in place. /backups/last-backup.json records the result
# for Settings -> General.
#   backup.sh loop   -> runs every day at BACKUP_AT (HH:MM, container local time; TZ env) — the Compose service
#   backup.sh once   -> one backup now (scripts/backup-now.ps1)
set -eu

BACKUP_DIR=/backups
COPY_DIR=/backup-copy
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
AT="${BACKUP_AT:-02:00}"
STATUS="$BACKUP_DIR/last-backup.json"

json_text() {
  # A JSON string: backslashes and quotes escaped, newlines dropped.
  printf '%s' "$1" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g'
}

write_status() {
  # $1 = copied: true | false | null (no copy folder set up), $2 = error text
  at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '{"at": "%s", "copied": %s, "copy_error": "%s"}\n' "$at" "$1" "$(json_text "${2:-}")" \
    > "$STATUS.partial"
  mv "$STATUS.partial" "$STATUS"
}

prune() {
  find "$1" -maxdepth 1 -type f \( -name 'label-*.dump' -o -name 'assets-*.tar.gz' \) -mtime +"$KEEP_DAYS" -delete
}

copy_off() {
  # Copies this backup's two files to the copy folder; prints the error and returns 1 on failure.
  stamp=$1
  for f in "label-$stamp.dump" "assets-$stamp.tar.gz"; do
    if ! err=$(cp "$BACKUP_DIR/$f" "$COPY_DIR/$f.partial" 2>&1 && mv "$COPY_DIR/$f.partial" "$COPY_DIR/$f" 2>&1); then
      rm -f "$COPY_DIR/$f.partial" 2>/dev/null || true
      echo "$err"
      return 1
    fi
  done
  prune "$COPY_DIR" 2>/dev/null || true
}

backup_once() {
  stamp=$(date +%Y%m%d-%H%M%S)
  mkdir -p "$BACKUP_DIR"
  echo "backup $stamp: database"
  PGPASSWORD="$DB_PASSWORD" pg_dump -h db -U label -d label -Fc -f "$BACKUP_DIR/label-$stamp.dump.partial"
  mv "$BACKUP_DIR/label-$stamp.dump.partial" "$BACKUP_DIR/label-$stamp.dump"
  echo "backup $stamp: assets"
  tar -czf "$BACKUP_DIR/assets-$stamp.tar.gz.partial" -C /data assets
  mv "$BACKUP_DIR/assets-$stamp.tar.gz.partial" "$BACKUP_DIR/assets-$stamp.tar.gz"
  prune "$BACKUP_DIR"
  if [ -n "${BACKUP_COPY_ENABLED:-}" ]; then
    echo "backup $stamp: copying off this machine"
    if err=$(copy_off "$stamp"); then
      write_status true ""
    else
      echo "backup $stamp: copy FAILED: $err" >&2
      write_status false "${err:-copy failed}"
    fi
  else
    write_status null ""
  fi
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
