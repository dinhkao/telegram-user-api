// VIEW BẢNG (có SẮP XẾP) cho 2 trang nhập khoản tiền theo tháng: ứng lương
// (#/nhap-ung) và phụ cấp (#/nhap-phu-cap). Cùng 1 bảng để 2 trang không lệch nhau
// (luật ĐỒNG BỘ 2 CHỖ ghi ở đầu AdvanceEntry/AllowanceEntry + CLAUDE.md).
//
// Cha map dữ liệu của mình về EntryRow rồi truyền vào — bảng KHÔNG biết gì về
// ứng/phụ cấp, chỉ lo hiển thị + sắp xếp. Dòng đã VÔ HIỆU vẫn hiện (gạch ngang,
// kèm ai/lúc nào/lý do) và KHÔNG vào tổng — giống view Thẻ.
// Bấm tiêu đề cột: lần 1 sắp, lần 2 đảo chiều, lần 3 bỏ sắp (giống bảng lương
// tháng — detail/payrollSort.ts). Lựa chọn nhớ trong localStorage theo `sortKey`.
import { useState } from "preact/hooks";
import { moneyR as money, dmy, tsLabel } from "../format";
import { Icon } from "../ui/Icon";

export type EntryRow = {
  key: string;
  worker: string;
  ymd: string;              // ngày của khoản ("" = không có, vd phụ cấp/lương tuần)
  amount: number;
  note: string;
  created?: string;         // ISO/DB timestamp — cột "Tạo"
  createdBy?: string;
  voidedAt?: string;
  voidedBy?: string;
  voidReason?: string;
  auto?: boolean;           // dòng TỰ ĐỘNG (lương tuần) — không sửa/vô hiệu được
  onNote?: () => void;
  onVoid?: () => void;
};

type Col = "worker" | "ymd" | "amount" | "note" | "created";
type Sort = { key: Col; dir: 1 | -1 };
const COLS: { key: Col; label: string; num: boolean }[] = [
  { key: "worker", label: "Thợ", num: false },
  { key: "ymd", label: "Ngày", num: false },
  { key: "amount", label: "Số tiền", num: true },
  { key: "note", label: "Nội dung", num: false },
  { key: "created", label: "Tạo", num: false },
];

const val = (r: EntryRow, k: Col): string | number =>
  k === "amount" ? r.amount
  : k === "worker" ? r.worker || ""
  : k === "ymd" ? r.ymd || ""
  : k === "note" ? r.note || ""
  : r.created || "";

/** sắp → đảo chiều → bỏ sắp (cột số: LỚN trước; cột chữ: A→Z). */
function nextSort(cur: Sort | null, key: Col, num: boolean): Sort | null {
  const first: 1 | -1 = num ? -1 : 1;
  if (!cur || cur.key !== key) return { key, dir: first };
  if (cur.dir === first) return { key, dir: (first === 1 ? -1 : 1) };
  return null;
}

export function EntryTable({ rows, sortKey, emptyNote }: {
  rows: EntryRow[];
  sortKey: string;            // khoá localStorage riêng cho từng trang
  emptyNote: string;          // chữ hiện ở ô Nội dung khi chưa ghi gì
}) {
  const [sort, setSortState] = useState<Sort | null>(() => {
    try {
      const s = JSON.parse(localStorage.getItem(sortKey) || "null");
      return s && COLS.some((c) => c.key === s.key) && (s.dir === 1 || s.dir === -1) ? s : null;
    } catch { return null; }
  });
  const setSort = (s: Sort | null) => {
    setSortState(s);
    try { if (s) localStorage.setItem(sortKey, JSON.stringify(s)); else localStorage.removeItem(sortKey); }
    catch { /**/ }
  };

  const shown = (() => {
    if (!sort) return rows;
    const out = rows.slice();
    out.sort((a, b) => {
      const x = val(a, sort.key), y = val(b, sort.key);
      const c = typeof x === "number" ? (x as number) - (y as number)
                                      : String(x).localeCompare(String(y), "vi");
      // hoà thì xếp theo TÊN để thứ tự ổn định, khỏi nhảy mỗi lần render
      return c ? c * sort.dir : a.worker.localeCompare(b.worker, "vi");
    });
    return out;
  })();
  const total = rows.filter((r) => !r.voidedAt).reduce((s, r) => s + r.amount, 0);

  return (
    <div class="et-wrap">
      <table class="et-table">
        <thead>
          <tr>
            {COLS.map((c) => {
              const on = sort?.key === c.key;
              return (
                <th key={c.key} class={`et-th${c.num ? " et-num" : ""}`} role="button" tabIndex={0}
                  aria-sort={on ? (sort!.dir === 1 ? "ascending" : "descending") : "none"}
                  title={`${c.label} — bấm để sắp xếp${on ? " (bấm nữa: đảo chiều / bỏ sắp)" : ""}`}
                  onClick={() => setSort(nextSort(sort, c.key, c.num))}
                  onKeyDown={(e: any) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSort(nextSort(sort, c.key, c.num)); } }}>
                  {c.label}{on ? <span class="pr-sort-ar">{sort!.dir === 1 ? "▲" : "▼"}</span> : null}
                </th>
              );
            })}
            <th class="et-th et-act" />
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.key} class={r.voidedAt ? "et-voided" : ""}>
              <td class="et-w">{r.worker}</td>
              <td>{r.ymd ? dmy(r.ymd) : <span class="muted">—</span>}</td>
              <td class="et-num et-amt">{money(r.amount)}</td>
              <td class="et-note">
                {r.note || <span class="muted">{r.voidedAt ? "" : emptyNote}</span>}
                {r.voidedAt ? (
                  <div class="small ua-void-info">vô hiệu {tsLabel(r.voidedAt)}
                    {r.voidedBy ? ` · ${r.voidedBy}` : ""}{r.voidReason ? ` — ${r.voidReason}` : ""}</div>
                ) : null}
              </td>
              <td class="et-ts muted small">
                {r.auto ? "tự động" : tsLabel(r.created) || "—"}
                {r.createdBy ? <div>{r.createdBy}</div> : null}
              </td>
              <td class="et-act">
                {!r.voidedAt && !r.auto ? (
                  <>
                    {r.onNote ? <button class="ua-note-edit" onClick={r.onNote} title="Sửa nội dung"
                      aria-label="Sửa nội dung"><Icon name="edit" size={14} /></button> : null}
                    {r.onVoid ? <button class="pr-adv-del" onClick={r.onVoid} aria-label="Vô hiệu">✕</button> : null}
                  </>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td class="et-w">Tổng</td><td />
            <td class="et-num et-amt">{money(total)}</td>
            <td colSpan={3} class="muted small">{shown.filter((r) => !r.voidedAt).length} khoản còn hiệu lực</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
