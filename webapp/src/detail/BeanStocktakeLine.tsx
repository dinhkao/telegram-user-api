// 1 DÒNG ĐẾM trong phiếu kiểm kho đậu (BeanStocktakeDetail) — tên đậu + sổ sách, ô
// nhập KÉP [N đơn vị quy đổi] + [M đơn vị gốc] (chỉ hiện ô kiện khi loại đậu có khai
// quy đổi) HOẶC chế độ TỔNG SỐ (`totalMode`, chọn ở đầu trang): 1 ô gõ thẳng số hiện
// có theo đơn vị gốc — lưu như "0 kiện + tổng" nên server/bản chỉ đọc không đổi.
// Chênh lệch tô màu, cờ "sổ đã đổi". Tự lưu khi rời ô (blur) nếu số đổi.
// Nối: api.countBeanStocktake qua prop onSave.
import { useEffect, useState } from "preact/hooks";
import { soVN, type BeanStocktakeItem } from "../api";
import { fmtQty, parseQty } from "../format";
import { SelectPopup } from "../ui/SelectPopup";

type Draft = { bulk: string; loose: string; unit_id: number | null };

function fromItem(it: BeanStocktakeItem, totalMode: boolean): Draft {
  const unit_id = it.unit_id ?? (it.units?.[0]?.id ?? null);
  // Tổng số: 1 ô = số đếm đã quy về gốc (kể cả dòng từng đếm kiểu kép), lưu lại
  // dạng "0 kiện + tổng" — mất phần tách kiện/lẻ của dòng đó, cố ý.
  if (totalMode) return { bulk: "", loose: it.counted_qty == null ? "" : fmtQty(it.counted_qty), unit_id };
  return {
    bulk: it.counted_bulk == null ? "" : fmtQty(it.counted_bulk),
    loose: it.counted_loose == null ? "" : fmtQty(it.counted_loose),
    unit_id,
  };
}

export function BeanStocktakeLine({ item, readonly, totalMode = false, onSave }: {
  item: BeanStocktakeItem;
  readonly: boolean;
  totalMode?: boolean;
  onSave: (bean_id: number, d: Draft) => Promise<void>;
}) {
  const [d, setD] = useState<Draft>(() => fromItem(item, totalMode));
  const [saving, setSaving] = useState(false);
  // Server trả bản mới (người khác đếm / realtime) hoặc đổi cách nhập → đồng bộ lại ô.
  useEffect(() => { setD(fromItem(item, totalMode)); },
    [item.counted_qty, item.unit_id, item.counted_bulk, item.counted_loose, totalMode]);

  const units = item.units || [];
  const unit = units.find((u) => u.id === d.unit_id) || null;
  const factor = unit?.factor || 1;
  const hasInput = d.bulk.trim() !== "" || d.loose.trim() !== "";
  // Số đếm xem trước (cùng công thức server): bulk×factor + loose; không có đơn vị → bulk cộng vào lẻ.
  const preview = hasInput
    ? (unit ? parseQty(d.bulk) * factor : parseQty(d.bulk)) + parseQty(d.loose) : null;
  // Chế độ tổng số: gợi ý quy ra kiện để đối chiếu với thực tế ngoài kho
  const asBulk = totalMode && unit && preview != null && factor > 1
    ? { n: Math.floor(preview / factor), rest: Math.round((preview - Math.floor(preview / factor) * factor) * 1000) / 1000 }
    : null;
  const diff = preview == null ? null : Math.round((preview - item.expected_qty) * 1000) / 1000;

  const commit = async () => {
    const cur = fromItem(item, totalMode);
    if (cur.bulk === d.bulk && cur.loose === d.loose && (cur.unit_id ?? null) === (d.unit_id ?? null)) return;
    setSaving(true);
    try { await onSave(item.bean_id, d); } finally { setSaving(false); }
  };

  const diffEl = diff == null ? <span class="muted">—</span>
    : <span class={diff > 0 ? "t-ok" : diff < 0 ? "t-danger" : "muted"}>
        {diff > 0 ? "+" : diff < 0 ? "−" : ""}{soVN(Math.abs(diff))}
      </span>;

  if (readonly) {
    return (
      <tr class={item.counted_qty == null ? "bst-skip" : ""}>
        <td>{item.bean_name}{item.note ? <div class="muted small">{item.note}</div> : null}</td>
        <td class="num muted">{soVN(item.expected_qty)} <span class="small">{item.unit}</span></td>
        <td class="num">
          {item.counted_qty == null ? <span class="muted small">chưa đếm</span> : (
            <>
              {soVN(item.counted_qty)} <span class="muted small">{item.unit}</span>
              {item.counted_bulk != null && item.unit_name ? (
                <div class="muted small">{soVN(item.counted_bulk)} {item.unit_name}
                  {item.counted_loose ? ` + ${soVN(item.counted_loose)} ${item.unit}` : ""}</div>
              ) : null}
            </>
          )}
        </td>
        <td class="num">{diffEl}</td>
      </tr>
    );
  }

  return (
    <div class={"bst-line" + (item.stale ? " stale" : "") + (item.counted_qty != null ? " counted" : "")}>
      <div class="bst-line-head">
        <div class="bst-line-name">{item.bean_name}</div>
        <div class="bst-line-book muted small">
          Sổ: <b>{soVN(item.expected_qty)}</b> {item.unit}
          {item.stale ? <span class="t-warn"> · tồn giờ {soVN(item.live_qty || 0)}</span> : null}
        </div>
      </div>
      <div class="bst-line-inputs">
        {units.length > 0 && !totalMode ? (
          <>
            <input class="bst-in" type="text" inputMode="decimal" placeholder="0" value={d.bulk}
              onFocus={(e: any) => e.target.select()}
              onInput={(e: any) => setD({ ...d, bulk: e.target.value })} onBlur={commit} />
            <div class="bst-unit">
              {units.length > 1 ? (
                <SelectPopup value={d.unit_id ?? ""} title="Đơn vị"
                  options={units.map((u) => ({ value: u.id, label: u.name,
                                                sub: `1 ${u.name} = ${soVN(u.factor)} ${item.unit}` }))}
                  onChange={(v) => { const nd = { ...d, unit_id: Number(v) }; setD(nd); onSave(item.bean_id, nd); }}
                  placeholder={unit?.name || ""} />
              ) : <span class="small">{unit?.name}</span>}
            </div>
            <span class="bst-plus">+</span>
          </>
        ) : null}
        <input class="bst-in" type="text" inputMode="decimal" placeholder="0" value={d.loose}
          onFocus={(e: any) => e.target.select()}
          onInput={(e: any) => setD({ ...d, loose: e.target.value })} onBlur={commit} />
        <span class="bst-base small">{item.unit}</span>
      </div>
      <div class="bst-line-foot small">
        {preview == null ? <span class="muted">Chưa đếm — chốt sẽ bỏ qua dòng này</span> : (
          <>
            {unit && d.bulk.trim() !== "" ? <span class="muted">= {soVN(preview)} {item.unit} · </span> : null}
            {asBulk ? <span class="muted">≈ {soVN(asBulk.n)} {unit!.name}{asBulk.rest ? ` + ${soVN(asBulk.rest)} ${item.unit}` : ""} · </span> : null}
            Chênh lệch: {diffEl}
            {saving ? <span class="muted"> · đang lưu…</span>
              : item.counted_by ? <span class="muted"> · {item.counted_by}</span> : null}
          </>
        )}
      </div>
    </div>
  );
}
