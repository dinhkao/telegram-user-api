// TRANG LƯƠNG THÁNG CỦA 1 THỢ (#/luong-thang/:worker_id?ym=YYYY-MM) — CHỈ văn phòng.
// Trước là popup khi bấm ô TÊN ở bảng lương; giờ là trang riêng (nội dung dài, cuộn
// thoải mái, chia sẻ được link, back về đúng bảng). Nội dung = detail/PayrollWorkerSheet
// (thực lãnh + thanh tỉ lệ, nguồn lương SP/TG, từng khoản phụ cấp/ứng).
// Bấm 1 khối → mở PayrollCellPopup đúng tab để XEM CÁCH TÍNH / THÊM-VÔ HIỆU khoản
// (giữ 1 chỗ thao tác duy nhất — xem luật ĐỒNG BỘ 2 CHỖ ở PayrollCellPopup).
// Thanh tháng ‹ › đổi tháng ngay trên trang (ghi vào URL để back/chia sẻ đúng kỳ).
import { useEffect, useState } from "preact/hooks";
import { getMonthlyPayroll, isOffice, payslipMonthHtmlUrl, type PayrollMonth } from "../api";
import { curYM, shiftYM, ymLabel } from "../format";
import { PayrollWorkerSheet } from "../detail/PayrollWorkerSheet";
import { PayrollCellPopup, type PayrollCol } from "../detail/PayrollCellPopup";
import { payrollActions } from "../detail/payrollActions";
import { wageLabel } from "../detail/wageType";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";

const queryYM = () => {
  const q = new URLSearchParams(window.location.hash.split("?")[1] || "").get("ym") || "";
  return /^\d{4}-\d{2}$/.test(q) ? q : curYM();
};

export function PayrollWorker({ wid }: { wid: number }) {
  const [ym, setYmState] = useState(queryYM);
  const [data, setData] = useState<PayrollMonth | null>(null);
  const [err, setErr] = useState("");
  const [pop, setPop] = useState<PayrollCol | null>(null);

  // đổi tháng = thay ?ym trên URL (replace: không rác lịch sử back)
  const setYm = (next: string) => {
    setYmState(next);
    const base = window.location.hash.split("?")[0];
    history.replaceState(null, "", `${base}?ym=${encodeURIComponent(next)}`);
  };
  const load = () => {
    setErr("");
    getMonthlyPayroll(ym).then(setData).catch((e: any) => setErr(e?.message || "Lỗi tải bảng lương"));
  };
  useEffect(() => { setData(null); load(); }, [ym]);

  const r = data?.workers.find((w) => w.worker_id === wid) || null;
  const { toggleType, editMoc, editBhxh, toggleWeekly } = payrollActions(ym, setData, load);

  const head = (
    <PageHead fallback={`#/luong-thang`}
      title={<><Icon name="wallet" size={18} /> {r ? r.name : "Lương tháng"}</>}
      sub={r ? `lương ${wageLabel(r.wage_type).toLowerCase()}` : "lương tháng của thợ"}
      right={r ? (
        <button class="pws-popup-print" title="In phiếu lương tháng"
          onClick={() => window.open(payslipMonthHtmlUrl(r.worker_id, ym), "_blank")}>
          <Icon name="printer" size={16} /> In phiếu
        </button>
      ) : undefined} />
  );
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="🔒">Chỉ văn phòng.</EmptyState></div>;

  return (
    <div class="pr-page pws-page">
      {head}
      <div class="pr-monthbar">
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
        <b>{ymLabel(ym)}</b>
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
      </div>

      {err && !data ? <ErrorState msg={err} onRetry={load} />
        : !data ? <Loading />
        : !r ? <EmptyState icon="🔍">Tháng này không có thợ nào mang mã #{wid}.</EmptyState>
        : (
          <section class="card pws-card">
            <PayrollWorkerSheet ym={ym} r={r} onCol={setPop}
              toggleType={toggleType} toggleWeekly={toggleWeekly} />
          </section>
        )}

      {pop && r && (
        <PayrollCellPopup ym={ym} r={r} col={pop}
          onClose={() => setPop(null)} onCol={setPop}
          apply={setData} editMoc={editMoc} editBhxh={editBhxh} />
      )}
    </div>
  );
}
