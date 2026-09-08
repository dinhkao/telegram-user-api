// POPUP NHẮC bản dự báo hàng hoá HÔM NAY — mount TOÀN CỤC ở main.tsx (chỉ khi đã
// đăng nhập, không phải vai chat_luong, không đang ở #/login hay #/du-bao…).
// Hiện tối đa 1 LẦN MỖI NGÀY trên MỖI MÁY: nhớ ymd đã nhắc ở localStorage
// (forecast_popup_ymd) — cờ này theo máy, còn `viewed` là theo NGƯỜI (server).
// Kiểm tra lúc mount + mỗi lần app quay lại foreground (throttle 60s) + khi có
// realtime forecast_changed. Data: getTodayForecast.
import { useEffect, useState } from "preact/hooks";
import { getTodayForecast, type ForecastRow } from "../api";
import { onRealtime } from "../realtime";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { fmtN } from "../pages/ForecastList";

const SEEN_KEY = "forecast_popup_ymd";
const MIN_GAP_MS = 60_000;   // không gọi API dồn dập khi bật/tắt màn liên tục

let lastFetchAt = 0;

function seenYmd(): string {
  try { return localStorage.getItem(SEEN_KEY) || ""; } catch { return ""; }
}
function markSeen(ymd: string) {
  try { localStorage.setItem(SEEN_KEY, ymd); } catch { /* localStorage bị chặn → cùng lắm nhắc lại */ }
}

export function ForecastPopup() {
  const [row, setRow] = useState<ForecastRow | null>(null);

  const check = async (force: boolean) => {
    const now = Date.now();
    if (!force && now - lastFetchAt < MIN_GAP_MS) return;
    lastFetchAt = now;
    try {
      const t = await getTodayForecast();
      const f = t.forecast;
      // Chưa có bản / user đã mở chi tiết / máy này đã nhắc hôm nay → im lặng.
      if (!f || t.viewed || seenYmd() === f.ymd) return;
      setRow(f);
    } catch { /* lỗi mạng → thôi, lần sau nhắc */ }
  };

  useEffect(() => { check(true); }, []);
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === "visible") check(false); };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);
  useEffect(() => onRealtime((e) => { if (e.type === "forecast_changed") check(true); }), []);

  const close = () => { if (row) markSeen(row.ymd); setRow(null); };
  const open = () => {
    if (!row) return;
    markSeen(row.ymd);
    const id = row.id;
    setRow(null);
    window.location.hash = `#/du-bao/${id}`;
  };

  usePopupBack(!!row, close);
  useScrollLock(!!row);
  if (!row) return null;

  return (
    <div class="fc-pop-backdrop" onClick={close}>
      <div class="fc-pop" onClick={(e: any) => e.stopPropagation()}>
        <div class="fc-pop-h"><Icon name="chart" size={18} /> Dự báo hàng hoá hôm nay</div>
        <div class="muted small">{row.dow_label} · {row.lunar_label}</div>
        <div class="fc-nums fc-pop-nums">
          <div class="fc-num">
            <span class="fc-num-lbl">Hôm nay</span>
            <b class="fc-num-v">~{fmtN(row.day_total)}</b>
          </div>
          <div class="fc-num">
            <span class="fc-num-lbl">Tuần này</span>
            <b class="fc-num-v">~{fmtN(row.week_total)}</b>
          </div>
        </div>
        {row.summary ? <p class="fc-pop-sum">{row.summary}</p> : null}
        <div class="fc-pop-actions">
          <button class="btn" onClick={close}>Để sau</button>
          <button class="btn primary" onClick={open}>Xem chi tiết</button>
        </div>
      </div>
    </div>
  );
}
