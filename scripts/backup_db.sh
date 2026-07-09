#!/bin/bash
# Backup an toàn các DB SQLite (dùng sqlite3 .backup — nhất quán kể cả khi server
# đang chạy). Dùng trước mỗi phase migration product-id. Giữ 15 bản gần nhất.
# Cách dùng: ./scripts/backup_db.sh <nhãn>   (vd: pre-phase0)
set -euo pipefail

LABEL="${1:-manual}"
TS="$(date +%Y%m%d-%H%M%S)"
DIR="$HOME/letrang-db/backup"
mkdir -p "$DIR"

backup_one() {
  local src="$1" name="$2"
  [ -f "$src" ] || { echo "skip $src (không có)"; return 0; }
  local dst="$DIR/${name}-${LABEL}-${TS}.db"
  sqlite3 "$src" ".backup '$dst'"
  echo "OK  $dst ($(du -h "$dst" | cut -f1))"
}

backup_one "$HOME/letrang-db/app.db" app
backup_one "$(cd "$(dirname "$0")/.." && pwd)/donhang.db" donhang
backup_one "$(cd "$(dirname "$0")/.." && pwd)/bot_sessions.db" bot_sessions

# Giữ 15 bản gần nhất mỗi loại
for prefix in app donhang bot_sessions; do
  ls -t "$DIR/${prefix}-"*.db 2>/dev/null | tail -n +16 | xargs rm -f 2>/dev/null || true
done
echo "Backup xong: $DIR"
