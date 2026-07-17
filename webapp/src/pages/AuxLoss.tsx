// Dashboard "Hao hụt nguyên liệu phụ" (#/hao-hut-nl, office-only) — so NL phụ
// DÙNG theo công thức với sụt giảm THỰC (đo qua 2 lần kiểm kho liên tiếp của
// "kho nguyên liệu đang dùng"). Mỗi kỳ = 1 card, MỚI → CŨ. gap>0 = hao hụt thật.
// API: getAuxLoss. Realtime inventory_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { getAuxLoss, ApiError, type AuxLossResp, type AuxLossPeriod, type AuxLossRow } from "../api";
import { onRealtime } from "../realtime";
import { fmtQty } from "../format";
import { Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

// prev_ts/cur_ts là EPOCH GIÂY (UTC) → chỉ dùng epoch, ĐỪNG parse chuỗi ngày
// (tránh lệch 7 giờ). Hiện ngày+giờ theo giờ VN.
function dtVN(epochSec: number): string {
  return new Date(epochSec * 1000).toLocaleString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// Màu chênh lệch: gap>0 → mất nhiều hơn định mức (đỏ), gap<0 → còn dư (xanh),
// gap=0/null → thường. Dùng inline color (không phụ thuộc class có sẵn).
function gapColor(gap: number | null): string | undefined {
  if (gap == null) return undefined;
  if (gap > 0) return "#c0392b";
  if (gap < 0) return "#1a7f37";
  return undefined;
}

const num = (v: number | null): string => (v == null ? "—" : fmtQty(v));

function PeriodCard({ p }: { p: AuxLossPeriod }) {
  // Ẩn cột "Châm" nếu mọi dòng cham==0 trong kỳ này (đỡ rối).
  const showCham = p.rows.some((r) => r.cham !== 0);
  const t = p.totals;
  return (
    <section class="card">
      <div class="al-head">
        {p.open ? (
          <span>
            <b>Đang diễn ra</b>{" "}
            <span class="al-badge">chưa kiểm kho</span>{" "}
            <span class="muted small">từ {dtVN(p.prev_ts)}</span>
          </span>
        ) : (
          <b>{dtVN(p.prev_ts)} → {p.cur_ts != null ? dtVN(p.cur_ts) : "—"}</b>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table class="al-tbl">
          <thead>
            <tr>
              <th>NL phụ</th>
              <th class="al-r">Dùng SX</th>
              {showCham && <th class="al-r">Châm</th>}
              <th class="al-r">Đếm trước</th>
              <th class="al-r">Đếm sau</th>
              <th class="al-r">Tiêu thụ</th>
              <th class="al-r">Chênh lệch</th>
            </tr>
          </thead>
          <tbody>
            {p.rows.map((r: AuxLossRow) => (
              <tr key={r.code}>
                <td>
                  <b>{r.code}</b>
                  <div class="muted small">{r.name}{r.unit ? ` · ${r.unit}` : ""}</div>
                </td>
                <td class="al-r">{num(r.used)}</td>
                {showCham && <td class="al-r">{num(r.cham)}</td>}
                <td class="al-r">{num(r.prev)}</td>
                <td class="al-r">{p.open ? <span class="muted">—</span> : num(r.now)}</td>
                <td class="al-r">{p.open ? <span class="muted">—</span> : num(r.consumed)}</td>
                <td class="al-r" style={{ color: gapColor(r.gap), fontWeight: 600 }}>
                  {p.open ? <span class="muted">—</span> : num(r.gap)}
                </td>
              </tr>
            ))}
            <tr class="al-total">
              <td><b>TỔNG</b></td>
              <td class="al-r"><b>{num(t.used)}</b></td>
              {showCham && <td class="al-r"><b>{num(t.cham)}</b></td>}
              <td class="al-r" />
              <td class="al-r" />
              <td class="al-r"><b>{p.open ? "—" : num(t.consumed)}</b></td>
              <td class="al-r" style={{ color: gapColor(t.gap) }}>
                <b>{p.open ? "—" : num(t.gap)}</b>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function AuxLoss() {
  const [data, setData] = useState<AuxLossResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [err, setErr] = useState(false);

  const load = () => {
    setLoading(true);
    getAuxLoss(30)
      .then((d) => { setData(d); setForbidden(false); setErr(false); })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setForbidden(true);
        else setErr(true);
      })
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "inventory_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 500);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const place = data?.place || null;

  return (
    <div class="al-page">
      <h2 class="page-h"><Icon name="chart" size={18} /> Hao hụt nguyên liệu phụ</h2>
      {place && (
        <p class="muted small al-sub">
          Kho: <b>{place.name}</b> · So NL phụ dùng theo công thức với sụt giảm thực đo qua kiểm kho.
        </p>
      )}

      {loading && !data ? (
        <Loading />
      ) : forbidden ? (
        <p class="muted">Trang chỉ dành cho văn phòng.</p>
      ) : err ? (
        <p class="muted small">Lỗi tải dữ liệu.</p>
      ) : !place ? (
        <div class="card">
          <p class="muted">
            Chưa chỉ định "kho nguyên liệu đang dùng". Vào <a href="#/vi-tri">Vị trí</a> → chọn kho →
            bật ⭐ nguồn NL phụ.
          </p>
        </div>
      ) : !data || data.periods.length === 0 ? (
        <div class="card"><p class="muted">Cần ít nhất 2 lần kiểm kho để so sánh.</p></div>
      ) : (
        data.periods.map((p, i) => <PeriodCard key={`${p.prev_ts}-${i}`} p={p} />)
      )}
    </div>
  );
}
