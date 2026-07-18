// Trang IN PHIẾU LƯƠNG (#/in-luong) — CHỈ văn phòng. Chọn thợ (chip, mặc định mọi thợ;
// preset "Lương tuần") + khoảng ngày → mở 1 trang HTML nhiều phiếu, ngăn cách bằng đường
// cắt để máy in tự cắt giữa từng người. ?w=Tên (từ nút ở chi tiết thợ) → chọn sẵn 1 thợ.
// Data: listWorkers + payslipsHtmlUrl (GET /api/production/payslips-html).
import { useEffect, useState } from "preact/hooks";
import { isOffice, listWorkers, payslipsHtmlUrl, type Worker } from "../api";
import { WorkerChips } from "../detail/WorkerChips";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { EmptyState } from "../ui/states";
import { toast } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
// Thứ Hai của tuần chứa d
function monday(d: Date): Date { const m = new Date(d); m.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return m; }

export function PayslipPrint() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [sel, setSel] = useState<Set<number> | null>(null);   // null = mọi thợ
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    const now = new Date();
    setFrom(iso(monday(now)));   // mặc định = tuần này
    setTo(iso(now));
    listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {});
  }, []);

  // Chọn sẵn 1 thợ khi vào từ nút "In phiếu lương" ở chi tiết thợ (#/in-luong?w=Tên)
  useEffect(() => {
    const m = location.hash.match(/[?&]w=([^&]+)/);
    if (m && workers.length) {
      const nm = decodeURIComponent(m[1]).trim().toLowerCase();
      const w = workers.find((x) => x.name.trim().toLowerCase() === nm);
      if (w) setSel(new Set([w.id]));
    }
  }, [workers]);

  const preset = (which: "this" | "last") => {
    const now = new Date(); const mon = monday(now);
    if (which === "this") { setFrom(iso(mon)); setTo(iso(now)); }
    else {
      const lm = new Date(mon); lm.setDate(mon.getDate() - 7);
      const ls = new Date(mon); ls.setDate(mon.getDate() - 1);
      setFrom(iso(lm)); setTo(iso(ls));
    }
  };

  const doPrint = () => {
    if (!from || !to) { toast("Chọn khoảng ngày", "err"); return; }
    if (from > to) { toast("Ngày bắt đầu phải trước ngày kết thúc", "err"); return; }
    if (sel !== null && sel.size === 0) { toast("Chọn ít nhất 1 thợ", "err"); return; }
    const names = sel === null ? [] : workers.filter((w) => sel.has(w.id)).map((w) => w.name);
    window.open(payslipsHtmlUrl(names, from, to), "_blank");
  };

  const head = (
    <PageHead fallback="#/home"
      title={<><Icon name="printer" size={18} /> In phiếu lương</>}
      sub="chọn thợ + khoảng ngày → in 1 lần, tự cắt giữa từng người" />
  );
  if (!isOffice()) return <div class="rs-page">{head}<EmptyState icon="lock">Chỉ văn phòng.</EmptyState></div>;

  const count = sel === null ? workers.length : sel.size;
  return (
    <div class="rs-page">
      {head}
      <section class="card rs-create">
        <div class="rs-dates">
          <label class="rs-date-f">
            <span class="muted small">Từ ngày</span>
            <input type="date" value={from} max={to || undefined} onChange={(e: any) => setFrom(e.currentTarget.value)} />
          </label>
          <label class="rs-date-f">
            <span class="muted small">Đến ngày</span>
            <input type="date" value={to} min={from || undefined} onChange={(e: any) => setTo(e.currentTarget.value)} />
          </label>
        </div>
        <div class="rs-presets">
          <button class="rs-preset" onClick={() => preset("this")}>Tuần này</button>
          <button class="rs-preset" onClick={() => preset("last")}>Tuần trước</button>
        </div>
        <WorkerChips workers={workers} value={sel} onChange={setSel} />
        <button class="btn primary block" disabled={!from || !to} onClick={doPrint}>
          <Icon name="printer" size={16} /> Tạo &amp; In ({count} thợ)
        </button>
      </section>
      <p class="muted small" style={{ padding: "2px 6px" }}>
        Mỗi thợ 1 phiếu, có đường cắt "- - -" ngăn cách để máy in tự cắt giữa từng người.
      </p>
    </div>
  );
}
