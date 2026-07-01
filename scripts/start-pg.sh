#!/usr/bin/env bash
# Khởi động server.py trên PostgreSQL (dùng thay `python server.py` sau khi cutover).
# Export env TRƯỚC khi launch để chắc chắn utils.db nhận (không phụ thuộc thứ tự load_dotenv).
# PG chạy trong docker `letrang-pg` (volume bền + restart unless-stopped) — xem
# docs/postgres-migration.md.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export DB_ENGINE=postgres
# PG native (homebrew postgresql@16) qua UNIX SOCKET — 0.05ms/query (docker TCP ~0.7ms).
# brew services quản (tự start khi reboot). Docker container 'letrang-pg' là backup (đã stop).
export DATABASE_URL="${DATABASE_URL:-postgresql://duydinh0225@/app?host=/tmp}"

echo "server.py -> PostgreSQL ($DATABASE_URL)"
exec "$ROOT/.venv/bin/python" -u server.py
