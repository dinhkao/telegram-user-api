// Dropdown GỢI Ý dưới ô tìm dashboard Đơn — đang gõ thì hiện khách hàng + sản phẩm
// (tên/mã) khớp, từ GET /api/orders/suggest (không dấu, xếp hạng ở server). Chọn 1 dòng
// → onPick(tên khách | MÃ SP) → trang đặt ô tìm = giá trị đó (FTS đơn sẵn có lo phần
// lọc; mã SP tự mở rộng mã cũ). Gắn listener vào input của SearchBar qua inputRef nên
// SearchBar không phải đổi. Đặt trong 1 phần tử cha position:relative (.osug-row).
import { useEffect, useRef, useState } from "preact/hooks";
import type { RefObject } from "preact";
import { getJSON } from "../api";
import { Icon } from "../ui/Icon";
import { Highlight } from "./OrderCards";

type Sug = { kind: "cust" | "prod"; value: string; label: string; sub?: string };

export function OrderSearchSuggest({ q, inputRef, onPick }: {
  q: string;
  inputRef: RefObject<HTMLInputElement>;
  onPick: (value: string) => void;
}) {
  const [items, setItems] = useState<Sug[]>([]);
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(-1);
  const [picked, setPicked] = useState<string | null>(null);   // vừa chọn → không mở lại cho đúng chữ đó
  const seq = useRef(0);
  const st = useRef({ open: false, items: [] as Sug[], active: -1 });

  const term = q.trim();
  const open = focused && !!term && term !== picked && items.length > 0;
  st.current = { open, items, active };

  // Tải gợi ý: trễ 150ms + bỏ phản hồi lỗi thời (seq) — gõ nhanh không bắn 1 request/phím.
  useEffect(() => {
    const my = ++seq.current;
    setActive(-1);
    if (!term || term === picked) { setItems([]); return; }
    const t = setTimeout(async () => {
      try {
        const d = await getJSON(`/api/orders/suggest?q=${encodeURIComponent(term)}`, { cache: false });
        if (my !== seq.current) return;
        setItems([
          ...(d.customers || []).map((c: any): Sug => ({ kind: "cust", value: c.name, label: c.name })),
          ...(d.products || []).map((p: any): Sug => ({ kind: "prod", value: p.code, label: p.code, sub: p.name })),
        ]);
      } catch {
        if (my === seq.current) setItems([]);   // gợi ý là phụ — lỗi thì im, ô tìm vẫn chạy
      }
    }, 150);
    return () => clearTimeout(t);
  }, [term, picked]);

  const pick = (s: Sug) => {
    setPicked(s.value);
    setItems([]);
    onPick(s.value);
    inputRef.current?.blur();   // cụp bàn phím để thấy danh sách đơn
  };

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    const onFocus = () => setFocused(true);
    const onBlur = () => setFocused(false);
    const onInput = () => setPicked(null);   // gõ tiếp sau khi chọn → gợi ý lại
    const onKey = (e: KeyboardEvent) => {
      const { open: o, items: its, active: a } = st.current;
      if (!o) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const n = its.length;
        setActive(e.key === "ArrowDown" ? (a + 1) % n : (a <= 0 ? n - 1 : a - 1));
      } else if (e.key === "Enter" && a >= 0) {
        e.preventDefault();
        pick(its[a]);
      } else if (e.key === "Escape") {
        e.stopPropagation();   // Esc đầu chỉ đóng gợi ý, chưa bỏ lọc (listener window của trang)
        setPicked(inputRef.current?.value.trim() || "");
      }
    };
    el.addEventListener("focus", onFocus);
    el.addEventListener("blur", onBlur);
    el.addEventListener("input", onInput);
    el.addEventListener("keydown", onKey);
    if (document.activeElement === el) setFocused(true);
    return () => {
      el.removeEventListener("focus", onFocus);
      el.removeEventListener("blur", onBlur);
      el.removeEventListener("input", onInput);
      el.removeEventListener("keydown", onKey);
    };
  }, [inputRef.current]);

  if (!open) return null;
  const custs = items.filter((s) => s.kind === "cust");
  const prods = items.filter((s) => s.kind === "prod");
  const row = (s: Sug) => {
    const i = items.indexOf(s);
    return (
      <button key={`${s.kind}:${s.value}`} type="button" class={i === active ? "osug-it on" : "osug-it"}
        onMouseDown={(e) => e.preventDefault()}   // giữ focus ô tìm tới lúc click xong
        onMouseEnter={() => setActive(i)} onClick={() => pick(s)}>
        <Icon name={s.kind === "cust" ? "user" : "tag"} size={14} class="osug-ic" />
        <span class="osug-main"><Highlight text={s.label} q={term} /></span>
        {s.sub ? <span class="osug-sub"><Highlight text={s.sub} q={term} /></span> : null}
      </button>
    );
  };
  return (
    <div class="osug" role="listbox">
      {custs.length > 0 && <div class="osug-h">Khách hàng</div>}
      {custs.map(row)}
      {prods.length > 0 && <div class="osug-h">Sản phẩm</div>}
      {prods.map(row)}
    </div>
  );
}
