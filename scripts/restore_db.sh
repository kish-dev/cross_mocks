#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup.sql>"
  exit 1
fi

BACKUP_FILE="$1"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE"
  exit 1
fi

docker-compose exec -T db psql -U postgres -d tgmocks -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker-compose exec -T db psql -U postgres -d tgmocks < "$BACKUP_FILE"
echo "Restore completed from: $BACKUP_FILE"
