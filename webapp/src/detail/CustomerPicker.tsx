// Ô tìm + chọn khách hàng (autocomplete /api/customers). Dùng ở CreateOrder
// (tạo đơn) và OrderDetail (gán khách cho đơn chưa có). Gọi onPick khi chọn.
import { useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money } from "../format";

export function CustomerPicker({ onPick, placeholder }: {
  onPick: (c: { key: string; name: string } | null) => void;
  placeholder?: string;
}) {
  const [q, setQ] = useState("");
  const [sug, setSug] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const seq = useRef(0);
  // Tìm tức thời (không delay); seq chặn kết quả cũ ghi đè kết quả mới
  const input = async (v: string) => {
    setQ(v);
    onPick(null);
    if (!v.trim()) { setSug([]); setOpen(false); return; }
    const my = ++seq.current;
    const d = await getJSON(`/api/customers?search=${encodeURIComponent(v)}&limit=10`, { cache: false }).catch(() => ({ customers: [] }));
    if (my !== seq.current) return; // phản hồi cũ về muộn → bỏ
    setSug(d.customers || []);
    setOpen((d.customers || []).length > 0);
  };
  const pick = (c: any) => { setQ(c.name); setOpen(false); onPick({ key: c.key, name: c.name }); };
  return (
    <div class="ac">
      <input value={q} placeholder={placeholder || "Tìm khách hàng"} onInput={(e: any) => input(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && (
        <ul class="ac-list">
          {sug.map((c) => (
            <li key={c.key} onMouseDown={() => pick(c)}><b>{c.name}</b>{c.debt ? ` · nợ ${money(c.debt)}đ` : ""}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
