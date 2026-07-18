// NHẬP PHỤ CẤP (#/nhap-phu-cap) — CHỈ văn phòng. Ghi phụ cấp cho thợ theo tháng,
// xem toàn bộ khoản phụ cấp trong tháng và xoá từng khoản.
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAllowance, deletePayrollAllowance, isOffice, listAllAllowances, listPayrollAllowances, listWorkers, soVN,
  type SalaryAllowance, type Worker,
} from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { Loading, EmptyState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const money = (n: number) => soVN(Math.round(n || 0));
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const shiftYM = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const dt = new Date(y, m - 1 + d, 1); return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`; };
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };
const initialFilter = () => {
  const query = new URLSearchParams((window.location.hash.split("?")[1] || ""));
  const queryYM = query.get("ym") || "";
  const queryWid = Number(query.get("worker_id") || 0);
  return { ym: /^\d{4}-\d{2}$/.test(queryYM) ? queryYM : curYM(), wid: queryWid > 0 ? queryWid : null };
};

export function AllowanceEntry() {
  const initial = initialFilter();
  const [ym, setYm] = useState(initial.ym);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [allows, setAllows] = useState<SalaryAllowance[] | null>(null);
  const [wid, setWid] = useState<number | null>(initial.wid);
  const [filterWid, setFilterWid] = useState<number | null>(initial.wid);
  const [amt, setAmt] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    setAllows(null);
    const request = filterWid ? listPayrollAllowances(ym, filterWid) : listAllAllowances(ym);
    request.then(setAllows).catch(() => setAllows([]));
  };
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [ym, filterWid]);

  const nameOf = (id: number) => workers.find((w) => w.id === id)?.name || `#${id}`;

  const submit = async () => {
    if (busy) return;
    if (!wid) { toast("Chọn thợ", "err"); return; }
    if (num(amt) <= 0) { toast("Nhập số tiền phụ cấp", "err"); return; }
    setBusy(true);
    try {
      await addPayrollAllowance(ym, wid, num(amt), note);
      toast(`Đã ghi phụ cấp ${money(num(amt))} cho ${nameOf(wid)}`, "ok");
      setAmt("");
      setNote("");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi ghi phụ cấp", "err"); }
    finally { setBusy(false); }
  };

  const del = async (id: number) => {
    if (!(await confirmDialog("Xoá khoản phụ cấp này?"))) return;
    try { await deletePayrollAllowance(ym, id); load(); }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); }
  };

  const list = (allows || []).slice().sort((a, b) => b.id - a.id);
  const total = list.reduce((sum, item) => sum + item.amount, 0);
  const wopts = workers.map((w) => ({ value: w.id, label: w.name }));

  const head = <PageHead fallback="#/home" title={<><Icon name="banknote" size={18} /> Nhập phụ cấp</>} sub="ghi phụ cấp cho thợ theo tháng" />;
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="🔒">Chỉ văn phòng.</EmptyState></div>;

  return (
    <div class="pr-page">
      {head}
      <div class="pr-monthbar">
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
        <b>{ymLabel(ym)}</b>
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
      </div>

      <section class="card ua-create">
        <label class="card-label">Ghi phụ cấp</label>
        <SelectPopup value={wid} options={wopts} onChange={(v) => setWid(Number(v))}
          searchable placeholder="Chọn thợ…" title="Chọn thợ" />
        <div class="ua-form">
          <input class="pw-input ua-amt-in" inputMode="numeric" placeholder="Số tiền phụ cấp" value={amt} onInput={(e: any) => setAmt(e.target.value)} />
          <input class="pw-input ua-note-in" placeholder="Nội dung phụ cấp" value={note} onInput={(e: any) => setNote(e.target.value)} />
        </div>
        <button class="btn primary block" disabled={busy} onClick={submit}>{busy ? "Đang ghi…" : "Ghi phụ cấp"}</button>
      </section>

      {allows === null ? <Loading /> : (
        <>
          {filterWid ? (
            <div class="ua-filter">
              <span>Đang lọc: <b>{nameOf(filterWid)}</b></span>
              <button class="btn small" onClick={() => setFilterWid(null)}>Xem tất cả</button>
            </div>
          ) : null}
          <div class="card pr-totals">
            <span>Tổng phụ cấp {ymLabel(ym).toLowerCase()} <b>{money(total)}</b> · {list.length} khoản</span>
          </div>
          {list.length === 0 ? <EmptyState icon="💵">Chưa có khoản phụ cấp nào trong tháng.</EmptyState> : (
            list.map((item) => (
              <div class="card ua-row" key={item.id}>
                <div class="ua-row-main">
                  <b>{nameOf(item.worker_id)}</b>
                  {item.note ? <div class="muted small">{item.note}</div> : null}
                </div>
                <b class="ua-amt">{money(item.amount)}</b>
                <button class="pr-adv-del" onClick={() => del(item.id)} aria-label="Xoá">✕</button>
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}
