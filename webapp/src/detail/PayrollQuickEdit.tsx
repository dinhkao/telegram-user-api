// 2 Ô NHẬP NHANH trong popup ô bảng lương tháng (detail/PayrollCellPopup):
// - CongOverride: gõ THẲNG số ngày công để ĐÈ số quy từ máy chấm công (máy hỏng /
//   quên chấm / công thoả thuận). Có nút bỏ ghi đè để quay về số máy.
// - TruAn: SỐ TRỪ ẨN khỏi lương sản phẩm — phiếu lương in cho thợ KHÔNG hiện dòng
//   nào về khoản này, chỉ thấy lương SP đã trừ. Chỉ văn phòng thấy ở bảng lương.
// Tách khỏi PayrollCellPopup vì file đó đã chạm trần 400 dòng.
// Ghi qua setPayrollAdjust (cong_override / tru_an) — xem server_app/payroll_routes.
import { useEffect, useState } from "preact/hooks";
import { setPayrollAdjust, type PayrollMonth, type PayrollRow } from "../api";
import { digitsOnly, docTien, moneyR as money } from "../format";
import { toast } from "../ui/feedback";

const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
/** "3,5" → 3.5; rỗng → null (chưa gõ gì). Nhận cả dấu phẩy kiểu Việt. */
const congNum = (s: string): number | null => {
  const t = String(s || "").replace(",", ".").replace(/[^\d.]/g, "");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

/** Ô nhập NGÀY CÔNG gõ tay (đè máy chấm công). */
export function CongOverride({ ym, r, apply }: {
  ym: string; r: PayrollRow; apply: (d: PayrollMonth) => void;
}) {
  // API cũ / dữ liệu thiếu → cong_auto vắng: lùi về chính số đang dùng, KHÔNG để
  // congVN(undefined) in ra "NaN" ngay giữa ô nhập lương.
  const auto = r.cong_auto ?? r.cong ?? 0;
  const [v, setV] = useState(() => (r.cong_manual ? congVN(r.cong) : ""));
  const [busy, setBusy] = useState(false);
  // đổi thợ / đổi tháng thì nạp lại số đang có, khỏi giữ số của người trước
  useEffect(() => { setV(r.cong_manual ? congVN(r.cong) : ""); }, [r.worker_id, ym, r.cong_manual]);

  const save = async (value: number | null) => {
    setBusy(true);
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { cong_override: value }));
      toast(value === null ? `Bỏ ghi đè — dùng lại số máy chấm (${congVN(auto)})`
                           : `Ngày công ${ym}: ${congVN(value)}`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu ngày công", "err"); }
    finally { setBusy(false); }
  };
  const n = congNum(v);
  return (
    <div class="pq-box">
      <div class="pq-lb">Nhập thẳng số ngày công (đè số máy chấm)</div>
      <div class="pq-row">
        <input class="pq-in" type="text" inputMode="decimal" placeholder={congVN(auto)}
          value={v} onInput={(e: any) => setV(e.currentTarget.value)} />
        <button class="btn primary pq-ok" disabled={busy || n === null || n < 0 || n > 62}
          onClick={() => n !== null && save(n)}>Lưu</button>
      </div>
      {r.cong_manual ? (
        <div class="pq-note">
          Đang dùng số gõ tay <b>{congVN(r.cong)}</b> — máy chấm quy ra {congVN(auto)}.
          <button class="pq-link" disabled={busy} onClick={() => { setV(""); save(null); }}>
            Bỏ ghi đè
          </button>
        </div>
      ) : (
        <div class="pq-note muted">Để trống = dùng số máy chấm công ({congVN(auto)}).</div>
      )}
    </div>
  );
}

/** Ô nhập SỐ TRỪ ẨN khỏi lương sản phẩm (phiếu in không hiện lý do). */
export function TruAn({ ym, r, apply }: {
  ym: string; r: PayrollRow; apply: (d: PayrollMonth) => void;
}) {
  const [v, setV] = useState(() => (r.tru_an ? String(r.tru_an) : ""));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setV(r.tru_an ? String(r.tru_an) : ""); }, [r.worker_id, ym, r.tru_an]);

  const n = Number(v || 0);
  const save = async (amount: number) => {
    setBusy(true);
    try {
      apply(await setPayrollAdjust(ym, r.worker_id, { tru_an: amount }));
      toast(amount > 0 ? `Đã trừ ẩn ${money(amount)}đ khỏi lương SP` : "Đã bỏ số trừ ẩn", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu số trừ ẩn", "err"); }
    finally { setBusy(false); }
  };
  return (
    <div class="pq-box">
      <div class="pq-lb">Số trừ ẩn khỏi lương sản phẩm</div>
      <div class="pq-row">
        <input class="pq-in money" type="text" inputMode="numeric" placeholder="0"
          value={v ? money(n) : ""} onInput={(e: any) => setV(digitsOnly(e.currentTarget.value))} />
        <button class="btn primary pq-ok" disabled={busy} onClick={() => save(n)}>Lưu</button>
      </div>
      {n > 0 ? <div class="pq-note">{docTien(n)}</div> : null}
      {n > (r.luong_goc || 0) && n > 0 ? (
        <div class="pq-note t-danger">
          Trừ nhiều hơn lương SP ({money(r.luong_goc || 0)}đ) — lương SP sẽ về 0, phần dôi
          KHÔNG tự chuyển sang khoản khác. Muốn trừ tiếp thì ghi vào Ứng lương.
        </div>
      ) : null}
      <div class="pq-note muted">
        Phiếu lương in cho thợ <b>không hiện</b> khoản này — chỉ thấy lương sản phẩm đã trừ.
      </div>
    </div>
  );
}
