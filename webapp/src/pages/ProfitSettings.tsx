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
      mw[String(m)] = isNaN(v) || v < 0 ? 1 : v;
    }
    setBusy(true);
    try {
      await postJSON("/api/profit/settings", { yearly_loan_payment: yearly, monthly_weights: mw });
      toast("Đã lưu cấu hình", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };

  const freeze = async () => {
    if (!(await confirmDialog(
      "ĐÓNG BĂNG giá vốn hiện tại vào MỌI đơn còn thiếu? Đơn đã có giá vốn giữ nguyên.",
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
      <PageHead fallback="#/loi-nhuan" title="Cấu hình lợi nhuận" sub="Tiền vay + trọng số tháng + đóng băng giá vốn" />
      <div class="card">
        <div class="ie-head">Tiền vay phải trả / NĂM</div>
        <input class="note-inp" style="max-width:200px" inputMode="numeric"
          value={yearly ? money(yearly) : ""} placeholder="0"
          onInput={(e: any) => setYearly(parseMoney(e.target.value))} />
        <div class="muted small mt-1">Lãi thực = lãi gộp − tiền vay phân bổ theo kỳ (chia 12 tháng × trọng số dưới).</div>
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
        <div class="muted small">Ghi giá vốn HIỆN TẠI vào mọi đơn chưa có cost_price — sau đó đổi giá vốn không làm lệch lãi của đơn cũ.</div>
        <button class="btn block mt-2" disabled={busy} onClick={freeze}>🧊 Đóng băng giá vốn vào đơn cũ</button>
      </div>
    </div>
  );
}
