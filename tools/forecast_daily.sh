#!/usr/bin/env bash
# Job 7h SÁNG: dự báo hàng hoá hôm nay + tuần này → agent Claude (Opus) viết nhận định →
# đăng vào app (#/du-bao, chuông, popup). Agent lỗi/hết hạn mức → đăng bản tự động.
# Cron:  0 7 * * *  /Volumes/samwinchester/letrang/telegram-user-api/tools/forecast_daily.sh >> ~/letrang-db/logs/forecast.log 2>&1
# Chạy tay: tools/forecast_daily.sh [YYYY-MM-DD] [--auto]   (--auto = bỏ qua agent)
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export HOME="${HOME:-/Users/duydinh0225}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DIR/.venv/bin/python"
YMD="${1:-$(TZ=Asia/Ho_Chi_Minh date +%F)}"
MODE="${2:-}"
WORK="$HOME/letrang-db/forecast"
mkdir -p "$WORK" "$HOME/letrang-db/logs"
DATA="$WORK/$YMD.json"; DRAFT="$WORK/$YMD.draft.json"
MODEL="${FORECAST_MODEL:-claude-opus-5}"
echo "[$(date '+%F %T')] forecast start ymd=$YMD"
cd "$DIR" || exit 1

"$PY" tools/forecast_compute.py --ymd "$YMD" --out "$DATA" || { echo "compute FAIL"; exit 1; }
rm -f "$DRAFT"

if [[ "$MODE" != "--auto" ]] && command -v claude >/dev/null; then
    PUBLISH_CMD="$PY tools/forecast_publish.py --data $DATA --draft $DRAFT --model $MODEL"
    PROMPT="$(sed -e "s|__DATA__|$DATA|g" -e "s|__DRAFT__|$DRAFT|g" -e "s|__PUBLISH__|$PUBLISH_CMD|g" tools/forecast_agent_prompt.md)"
    # macOS không có `timeout` — dùng gtimeout (coreutils) nếu có, không thì chạy trần
    TO="$(command -v timeout || command -v gtimeout || true)"
    ${TO:+$TO 900} claude -p "$PROMPT" \
        --model "$MODEL" --max-turns 12 --permission-mode acceptEdits \
        --allowedTools "Read" "Write" "Bash($PY tools/forecast_publish.py:*)" \
        --output-format text 2>&1 | tail -20
    echo "agent exit=${PIPESTATUS[0]}"
fi

# Agent không đăng được (không có draft / đăng lỗi) → bản tự động, để ô hôm nay vẫn có.
if ! "$PY" tools/forecast_publish.py --check "$YMD" >/dev/null 2>&1; then
    echo "chưa có bản $YMD → đăng bản tự động"
    "$PY" tools/forecast_publish.py --data "$DATA" --auto
fi
echo "[$(date '+%F %T')] forecast done"
