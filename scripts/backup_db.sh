#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p backups
TS="$(date +%Y%m%d_%H%M%S)"
OUT="backups/backup_${TS}.sql"

docker-compose exec -T db pg_dump -U postgres tgmocks > "$OUT"
echo "Backup created: $OUT"
