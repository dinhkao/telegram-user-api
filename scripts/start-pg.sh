#!/usr/bin/env bash
# Khởi động server.py trên PostgreSQL (dùng thay `python server.py` sau khi cutover).
# Export env TRƯỚC khi launch để chắc chắn utils.db nhận (không phụ thuộc thứ tự load_dotenv).
# PG chạy trong docker `letrang-pg` (volume bền + restart unless-stopped) — xem
# docs/postgres-migration.md.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export DB_ENGINE=postgres
export DATABASE_URL="${DATABASE_URL:-postgresql://letrang:letrang@localhost:5433/app}"

# Đảm bảo container PG đang chạy
if ! docker exec letrang-pg pg_isready -U letrang -d app >/dev/null 2>&1; then
    echo "PG container 'letrang-pg' chưa sẵn sàng. Khởi động: docker start letrang-pg" >&2
    exit 1
fi

echo "server.py -> PostgreSQL ($DATABASE_URL)"
exec "$ROOT/.venv/bin/python" -u server.py
