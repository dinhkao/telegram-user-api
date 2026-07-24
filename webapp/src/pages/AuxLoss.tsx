// Dashboard "Hao hụt nguyên liệu phụ" (#/hao-hut-nl, office-only) — so NL phụ
// DÙNG theo công thức với sụt giảm THỰC (đo qua 2 lần kiểm kho liên tiếp của
// "kho nguyên liệu đang dùng"). Mỗi kỳ = 1 card gồm 2 BẢNG KỀ BÊN (định mức ↔
// thực tế) để dễ so sánh; MỚI → CŨ. gap>0 = hao hụt thật. API: getAuxLoss.
import { useEffect, useState } from "preact/hooks";
import { getAuxLoss, ApiError, type AuxLossResp, type AuxLossPeriod, type AuxLossRow } from "../api";
import { onRealtime } from "../realtime";
import { fmtDateTimeVN, fmtQty } from "../format";
import { PageHead } from "../ui/PageHead";
import { EmptyState, ErrorState, Loading } from "../ui/states";

// prev_ts/cur_ts là EPOCH GIÂY (UTC) → chỉ dùng epoch, ĐỪNG parse chuỗi ngày

// Màu chênh lệch: gap>0 → mất nhiều hơn định mức (.t-danger), gap<0 → còn dư
// (.t-ok), gap=0/null → thường.
const gapCls = (gap: number | null): string =>
  gap == null || gap === 0 ? "" : gap > 0 ? " t-danger" : " t-ok";

const num = (v: number | null): string => (v == null ? "—" : fmtQty(v));
const Dash = () => <span class="muted">—</span>;
// Ô nhãn NL phụ (mã + đơn vị) — 1 dòng để 2 bảng canh hàng khớp nhau.
const NlCell = ({ r }: { r: AuxLossRow }) => (
  <td class="al-nl"><b>{r.code}</b>{r.unit ? <span class="muted small"> · {r.unit}</span> : null}</td>
);

// 2 BẢNG KỀ BÊN: TRÁI = nên dùng theo công thức; PHẢI = thực tế đo qua kiểm kho
// (đếm trước → +châm → −đếm sau = tiêu thụ) + LỆCH so định mức. Cùng thứ tự NL
// phụ (backend sắp theo gap) nên đọc ngang từng hàng là so được.
function PeriodCard({ p }: { p: AuxLossPeriod }) {
  const showCham = p.rows.some((r) => r.cham !== 0);   // ẩn cột Châm nếu cả kỳ = 0
  const t = p.totals;
  return (
    <section class="card">
      <div class="al-head">
        {p.open ? (
          <span>
            <b>Đang diễn ra</b>{" "}
            <span class="al-badge">chưa kiểm kho</span>{" "}
            <span class="muted small">từ {fmtDateTimeVN(p.prev_ts)}</span>
          </span>
        ) : (
          <b>{fmtDateTimeVN(p.prev_ts)} → {p.cur_ts != null ? fmtDateTimeVN(p.cur_ts) : "—"}</b>
        )}
      </div>
      <div class="al-cmp-wrap">
        <div class="al-cmp">
          {/* BẢNG TRÁI — nên dùng theo công thức */}
          <table class="al-tbl al-plan">
            <thead>
              <tr><th class="al-cap" colSpan={2}>📐 Theo công thức</th></tr>
              <tr><th>NL phụ</th><th class="al-r">Nên dùng</th></tr>
            </thead>
            <tbody>
              {p.rows.map((r) => (
                <tr key={r.code}><NlCell r={r} /><td class="al-r">{num(r.used)}</td></tr>
              ))}
              <tr class="al-total"><td><b>TỔNG</b></td><td class="al-r"><b>{num(t.used)}</b></td></tr>
            </tbody>
          </table>
          {/* BẢNG PHẢI — thực tế qua kiểm kho */}
          <table class="al-tbl al-real">
            <thead>
              <tr><th class="al-cap" colSpan={showCham ? 6 : 5}>📦 Thực tế (kiểm kho)</th></tr>
              <tr>
                <th>NL phụ</th>
                <th class="al-r">Đếm trước</th>
                {showCham && <th class="al-r">Châm</th>}
                <th class="al-r">Đếm sau</th>
                <th class="al-r">Tiêu thụ</th>
                <th class="al-r" title="Tiêu thụ thực − Nên dùng (dương = mất nhiều hơn định mức)">Lệch</th>
              </tr>
            </thead>
            <tbody>
              {p.rows.map((r) => (
                <tr key={r.code}>
                  <NlCell r={r} />
                  <td class="al-r">{num(r.prev)}</td>
                  {showCham && <td class="al-r">{num(r.cham)}</td>}
                  <td class="al-r">{p.open ? <Dash /> : num(r.now)}</td>
                  <td class="al-r"><b>{p.open ? <Dash /> : num(r.consumed)}</b></td>
                  <td class={"al-r" + gapCls(r.gap)}>
                    <b>{p.open ? <Dash /> : num(r.gap)}</b>
                  </td>
                </tr>
              ))}
              <tr class="al-total">
                <td><b>TỔNG</b></td>
                <td class="al-r" />
                {showCham && <td class="al-r"><b>{num(t.cham)}</b></td>}
                <td class="al-r" />
                <td class="al-r"><b>{p.open ? "—" : num(t.consumed)}</b></td>
                <td class={"al-r" + gapCls(t.gap)}>
                  <b>{p.open ? "—" : num(t.gap)}</b>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
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
      <PageHead fallback="#/home" title="Hao hụt NL phụ" />
      {place && (
        <p class="muted small al-sub">
          Kho: <b>{place.name}</b> · So NL phụ dùng theo công thức với sụt giảm thực đo qua kiểm kho.
        </p>
      )}

      {loading && !data ? (
        <Loading />
      ) : forbidden ? (
        <EmptyState icon="🔒">Trang chỉ dành cho văn phòng.</EmptyState>
      ) : err ? (
        <ErrorState msg="Lỗi tải dữ liệu." onRetry={load} />
      ) : !place ? (
        <EmptyState>
          Chưa chỉ định "kho nguyên liệu đang dùng". Vào <a href="#/vi-tri">Vị trí</a> → chọn kho →
          bật ⭐ nguồn NL phụ.
        </EmptyState>
      ) : !data || data.periods.length === 0 ? (
        <EmptyState>Cần ít nhất 2 lần kiểm kho để so sánh.</EmptyState>
      ) : (
        data.periods.map((p, i) => <PeriodCard key={`${p.prev_ts}-${i}`} p={p} />)
      )}
    </div>
  );
}
