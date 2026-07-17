// Chip chọn THỢ (multi-select) — dùng ở form tạo + sửa phiếu báo cáo SX.
// value = null nghĩa là MỌI THỢ (kể cả thợ thêm sau này); Set = chỉ các id đó.
// Preset: "Tất cả" (→ null) + "Lương tuần" (thợ bật weekly_salary, badge ·T).
import type { Worker } from "../api";

export function WorkerChips({ workers, value, onChange }: {
  workers: Worker[];
  value: Set<number> | null;
  onChange: (v: Set<number> | null) => void;
}) {
  if (!workers.length) return null;
  const isOn = (id: number) => value === null || value.has(id);
  const toggle = (id: number) => {
    const base = value === null ? new Set(workers.map((w) => w.id)) : new Set(value);
    base.has(id) ? base.delete(id) : base.add(id);
    onChange(base.size === workers.length ? null : base);
  };
  const weeklyIds = workers.filter((w) => w.weekly_salary).map((w) => w.id);
  return (
    <div class="rs-workers">
      <div class="rs-workers-head">
        <span class="muted small">Thợ tính trong báo cáo{value === null ? " (tất cả)" : ` (${value.size}/${workers.length})`}</span>
        <button type="button" class="chip" onClick={() => onChange(null)}>Tất cả</button>
        {weeklyIds.length > 0 && (
          <button type="button" class="chip" onClick={() => onChange(new Set(weeklyIds))}>Lương tuần ({weeklyIds.length})</button>
        )}
      </div>
      <div class="rs-worker-chips">
        {workers.map((w) => (
          <button type="button" key={w.id} class={isOn(w.id) ? "chip active" : "chip"} onClick={() => toggle(w.id)}>
            {w.name}{w.weekly_salary ? <span class="chip-n">T</span> : null}
          </button>
        ))}
      </div>
    </div>
  );
}
