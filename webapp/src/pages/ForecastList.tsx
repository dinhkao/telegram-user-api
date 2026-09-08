// Danh sách DỰ BÁO HÀNG HOÁ (#/du-bao) — mỗi ngày 1 ô: ngày dương + âm lịch, số
// dự báo hôm nay/tuần, nhận định ngắn. Bản chưa xem có chấm "Chưa xem". Tải thêm
// bản cũ bằng nút "Xem cũ hơn" (?before=). Data: listForecasts.
// Realtime forecast_changed → tải lại từ đầu.
import { useEffect, useRef, useState } from "preact/hooks";
import { listForecasts, soVN, type ForecastRow } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { EmptyState, ErrorState, Loading, LoadingInline } from "../ui/states";

/** Số lượng hàng — tách nghìn kiểu vi-VN, KHÔNG có "đ" (đây là số hàng, không phải tiền). */
export const fmtN = (n: number | null | undefined) => soVN(Math.round(Number(n) || 0));

let cache: ForecastRow[] | null = null;
let cacheMore = false;
onRealtime((e) => { if (e.type === "forecast_changed" || e.type === "resync") cache = null; });

/** "2026-09-08" → "8/9" (ngày dương gọn, khớp cách nói của xưởng). */
function dm(ymd: string): string {
  const p = String(ymd || "").split("-");
  return p.length === 3 ? `${Number(p[2])}/${Number(p[1])}` : ymd || "";
}

export function ForecastList() {
  const [rows, setRows] = useState<ForecastRow[] | null>(cache);
  const [hasMore, setHasMore] = useState(cacheMore);
  const [err, setErr] = useState("");
  const [more, setMore] = useState(false);

  const load = async () => {
    try {
      const r = await listForecasts();
      setRows(r.items); setHasMore(r.has_more);
      cache = r.items; cacheMore = r.has_more;
      setErr("");
    } catch (e: any) { setErr(e?.message || "Lỗi tải dự báo"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "forecast_changed" || e.type === "resync") load();
  }), []);
  // Giữ cache khi rời trang → quay lại hiện ngay, không nháy "Đang tải".
  const rowsRef = useRef<ForecastRow[]>([]);
  rowsRef.current = rows || [];
  useEffect(() => () => { if (rowsRef.current.length) { cache = rowsRef.current; } }, []);

  const loadMore = async () => {
    if (!rows || !rows.length || more) return;
    setMore(true);
    try {
      const r = await listForecasts(rows[rows.length - 1].id);
      const merged = [...rows, ...r.items];
      setRows(merged); setHasMore(r.has_more);
      cache = merged; cacheMore = r.has_more;
    } catch (e: any) { setErr(e?.message || "Lỗi tải thêm"); }
    finally { setMore(false); }
  };

  if (err && !rows) return <ErrorState msg={err} onRetry={load} />;
  if (!rows) return <Loading />;

  return (
    <div class="inv-dash">
      <PageHead fallback="#/home"
        title={<span><Icon name="chart" size={18} /> Dự báo hàng hoá</span>}
        sub="Mỗi sáng 7h · hôm nay + tuần này" />

      {rows.length === 0 ? (
        <EmptyState>Chưa có bản dự báo nào — bản đầu tiên sẽ có lúc 7h sáng.</EmptyState>
      ) : (
        <div class="fc-list">
          {rows.map((f) => (
            <a class={"fc-card" + (f.viewed ? "" : " unseen")} href={`#/du-bao/${f.id}`} key={f.id}>
              <div class="fc-card-top">
                <span class="fc-card-date">{f.dow_label} {dm(f.ymd)}</span>
                <span class="muted small">· {f.lunar_label}</span>
                {f.viewed ? null : <span class="fc-new">Chưa xem</span>}
              </div>
              <div class="fc-nums">
                <div class="fc-num">
                  <span class="fc-num-lbl">Hôm nay</span>
                  <b class="fc-num-v">~{fmtN(f.day_total)}</b>
                </div>
                <div class="fc-num">
                  <span class="fc-num-lbl">Tuần này</span>
                  <b class="fc-num-v">~{fmtN(f.week_total)}</b>
                </div>
              </div>
              {f.summary ? <p class="fc-sum">{f.summary}</p> : null}
              <Icon name="chevronRight" size={18} class="fc-card-arrow" />
            </a>
          ))}
        </div>
      )}

      {err && rows.length ? <p class="error small">{err}</p> : null}

      {hasMore && (
        <button class="btn block fc-more" disabled={more} onClick={loadMore}>
          {more ? <LoadingInline label="Đang tải…" /> : "Xem cũ hơn"}
        </button>
      )}
    </div>
  );
}
