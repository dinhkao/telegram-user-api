// Cấu hình dashboard LỢI NHUẬN (#/loi-nhuan/cai-dat, office): tiền vay NĂM +
// trọng số 12 tháng (phân bổ tiền vay theo mùa vụ) + nút ĐÓNG BĂNG giá vốn vào
// mọi đơn chưa có. ← GET/POST /api/profit/settings, POST /api/profit/freeze-costs.
import { useEffect, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { money, parseMoney } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState } from "../ui/states";

export function ProfitSettings() {
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");
  const [yearly, setYearly] = useState(0);
  const [weights, setWeights] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const load = () => {
    setErr("");
    getJSON("/api/profit/settings", { cache: false })
      .then((j) => {
        setYearly(Number(j.settings?.yearly_loan_payment) || 0);
        const w: Record<string, string> = {};
        for (let m = 1; m <= 12; m++) w[String(m)] = String(j.settings?.monthly_weights?.[String(m)] ?? 1);
        setWeights(w);
        setLoaded(true);
      }).catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, []);

  const save = async () => {
    const mw: Record<string, number> = {};
    for (let m = 1; m <= 12; m++) {
      const v = parseFloat(String(weights[String(m)]).replace(",", "."));
      if (!Number.isFinite(v) || v < 0) { toast(`Trọng số tháng ${m} không hợp lệ`, "err"); return; }
      mw[String(m)] = v;
    }
    if (Object.values(mw).every(v => v === 0)) { toast("Cần ít nhất một tháng có trọng số lớn hơn 0", "err"); return; }
    setBusy(true);
    try {
      await postJSON("/api/profit/settings", { yearly_loan_payment: yearly, monthly_weights: mw });
      toast("Đã lưu cấu hình", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };

  const freeze = async () => {
    if (!(await confirmDialog(
      "Ghi vốn hiện tại làm ƯỚC TÍNH vào các đơn từ mốc 460000 còn thiếu? Đây không phải xác nhận vốn lịch sử; báo cáo vẫn cảnh báo thiếu căn cứ. Đơn đã có vốn giữ nguyên.",
      { okLabel: "Đóng băng" }))) return;
    setBusy(true);
    try {
      const j = await postJSON("/api/profit/freeze-costs", {});
      toast(`Đã đóng băng giá vốn vào ${j.updated} đơn`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };

  if (err && !loaded) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan" title="Cấu hình lợi nhuận" /><ErrorState msg={err} onRetry={load} /></div>;
  if (!loaded) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan" title="Cấu hình lợi nhuận" /><Loading /></div>;
  return (
    <div class="prod-detail">
      <PageHead fallback="#/loi-nhuan" title="Cấu hình lợi nhuận" sub="Lãi vay + trọng số tháng + giá vốn" />
      <div class="card"><div class="ie-head">Quy ước giá vốn và VAT</div>
        <p class="small">Giá vốn đã tính sẵn VAT bán ra phải chịu. Lãi đơn = tổng tiền khách thanh toán gồm VAT − giá vốn đã lưu − chi phí giao hàng đã ghi. Không trừ thêm khoản VAT dự tính lần nữa. Giá vốn phải được nhập nhất quán theo quy ước này.</p>
      </div>
      <div class="card">
        <div class="ie-head">Tiền lãi vay / NĂM</div>
        <input class="note-inp" style="max-width:200px" inputMode="numeric"
          value={yearly ? money(yearly) : ""} placeholder="0"
          onInput={(e: any) => setYearly(parseMoney(e.target.value))} />
        <div class="muted small mt-1">Chỉ nhập lãi vay, không gồm tiền gốc. Lãi sau lãi vay = lãi gộp − lãi vay phân bổ; chưa trừ các chi phí vận hành khác.</div>
      </div>
      <div class="card">
        <div class="row space">
          <div class="ie-head">Trọng số từng tháng</div>
          <button class="btn small" onClick={() => {
            const w: Record<string, string> = {};
            for (let m = 1; m <= 12; m++) w[String(m)] = "1";
            setWeights(w);
          }}>↺ Reset về 1.0</button>
        </div>
        {/* XEM TRƯỚC như bản gốc: số tiền phân bổ từng tháng cập nhật sống khi gõ */}
        {(() => {
          const w: Record<string, number> = {};
          for (let m = 1; m <= 12; m++) {
            const v = parseFloat(String(weights[String(m)] ?? "1").replace(",", "."));
            w[String(m)] = isNaN(v) || v < 0 ? 0 : v;
          }
          const avg = Object.values(w).reduce((a, b) => a + b, 0) / 12;
          const monthly = yearly / 12;
          const alloc = (m: string) => (avg > 0 ? Math.round((monthly * w[m]) / avg) : 0);
          return (
            <>
              <div class="pf-weights">
                {Array.from({ length: 12 }, (_, i) => String(i + 1)).map((m) => (
                  <label key={m} class="pf-weight">
                    <span class="muted small">Th{m}</span>
                    <input inputMode="decimal" value={weights[m] ?? "1"}
                      onInput={(e: any) => setWeights((prev) => ({ ...prev, [m]: e.target.value }))} />
                    <span class="pf-alloc">{yearly > 0 ? money(alloc(m)) : ""}</span>
                  </label>
                ))}
              </div>
              {yearly > 0 && (
                <div class="muted small mt-1">
                  Tổng lãi vay/năm: <b>{money(yearly)}</b> · trung bình/tháng: <b>{money(Math.round(monthly))}</b>
                </div>
              )}
            </>
          );
        })()}
        <div class="muted small mt-1">Tháng cao điểm đặt số lớn hơn (vd Tết = 2) — tiền vay dồn vào tháng đó nhiều hơn.</div>
        <button class="btn block primary mt-2" disabled={busy} onClick={save}>
          <Icon name="save" size={16} /> Lưu cấu hình
        </button>
      </div>
      <div class="card">
        <div class="ie-head">Đóng băng giá vốn</div>
        <div class="muted small">Ghi vốn hiện tại làm ước tính cho đơn từ mốc 460000 còn thiếu. Báo cáo không dùng giá ước tính này làm vốn lịch sử đã xác nhận.</div>
        <button class="btn block mt-2" disabled={busy} onClick={freeze}>Ghi giá vốn ước tính vào đơn thiếu</button>
      </div>
    </div>
  );
}
