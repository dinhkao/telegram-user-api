// Chi tiết 1 bảng giá chung (#/bang-gia/:id) — xem/sửa giá từng SP, THÊM SP mới
// (chọn mã SP + giá), xem khách đang dùng + lịch sử đổi giá. API: getPriceList /
// savePriceOne / getPriceHistory / searchProducts.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { PageHead } from "../ui/PageHead";
import { getPriceList, savePriceOne, getPriceHistory, searchProducts,
  type PriceListFull, type PriceHistoryRow } from "../api";
import { money, parseMoney, fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { Loading, ErrorState } from "../ui/states";
import { SearchBar } from "../ui/SearchBar";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

const priceLabel = (p: number | null) => (p == null ? "—" : money(p));

export function PriceListDetail({ listId }: { listId: string }) {
  const [list, setList] = useState<PriceListFull | null>(null);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");
  const [editSp, setEditSp] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<PriceHistoryRow[] | null>(null);
  const [histSp, setHistSp] = useState<string | null>(null);
  // thêm SP mới
  const [adding, setAdding] = useState(false);
  const [addSp, setAddSp] = useState("");
  const [addPrice, setAddPrice] = useState("");

  const reload = () => getPriceList(listId).then(setList).catch((e) => setErr(e.message));
  useEffect(() => { reload(); }, [listId]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "price_lists_changed" || e.type === "customer_changed") {
        clearTimeout(t); t = setTimeout(reload, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [listId]);

  const mergeSaved = (updated: PriceListFull) => setList((l) => ({ ...updated, customers: l?.customers || [] }));

  const startEdit = (sp: string, price: number) => { setEditSp(sp); setEditVal(String(price)); setErr(""); };
  const saveEdit = async (sp: string) => {
    setSaving(true); setErr("");
    try {
      mergeSaved(await savePriceOne(listId, sp, parseMoney(editVal)));
      setEditSp(null);
      if (history !== null) loadHistory(histSp);
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  };

  const doAdd = async () => {
    const price = parseMoney(addPrice);
    const sp = addSp.trim().toUpperCase();
    if (!sp) { toast("Chọn mã SP", "err"); return; }
    if (!price || price <= 0) { toast("Nhập giá hợp lệ", "err"); return; }
    setSaving(true); setErr("");
    try {
      mergeSaved(await savePriceOne(listId, sp, price));
      setAddSp(""); setAddPrice(""); setAdding(false);
      toast(`✅ Đã thêm ${sp}`, "ok");
      if (history !== null) loadHistory(histSp);
    } catch (e: any) { setErr(e.message); toast(e.message || "Lỗi", "err"); } finally { setSaving(false); }
  };

  const loadHistory = (sp: string | null) => {
    setHistSp(sp); setHistory(null);
    getPriceHistory(listId, sp || undefined).then(setHistory).catch(() => setHistory([]));
  };

  if (err && !list) return <div class="prod-detail"><BackLink fallback="#/bang-gia" /><ErrorState msg={err} onRetry={reload} /></div>;
  if (!list) return <div class="prod-detail"><Loading /></div>;

  const q = filter.trim().toLowerCase();
  const items = q ? list.items.filter((it) => it.sp.toLowerCase().includes(q)) : list.items;
  const searchSp = async (s: string): Promise<PickOpt[]> =>
    (await searchProducts(s).catch(() => [])).map((p) => ({ key: p.code, label: p.code, sub: p.name || undefined }));

  return (
    <div class="prod-detail pl-page">
      <PageHead fallback="#/bang-gia"
        title={<><Icon name="receipt" size={18} /> {list.name}</>}
        sub={<>#{list.id} · {list.items.length} SP · {list.customers.length} khách</>} />

      {err && <p class="error">{err}</p>}

      <section class="card pl-toolbar">
        <div class="pl-toolbar-row">
          <span class="fill"><SearchBar value={filter} onInput={setFilter} placeholder="Tìm mã SP…" /></span>
          <button class={"btn primary pl-add-toggle" + (adding ? " on" : "")} onClick={() => setAdding((v) => !v)}>
            <Icon name={adding ? "close" : "plus"} size={16} /> {adding ? "Đóng" : "Thêm SP"}
          </button>
        </div>
        {adding && (
          <div class="pl-add">
            <div class="pl-add-sp">
              <PickerPopup value={addSp} placeholder="Chọn / gõ mã SP" allowFreeText
                onSearch={searchSp} onPick={(o) => setAddSp(o.key)} />
            </div>
            <input class="pl-add-price" type="text" inputMode="numeric" placeholder="Giá (đ)"
              value={addPrice} onFocus={(e: any) => e.target.select()} onInput={(e: any) => setAddPrice(e.target.value)} />
            <button class="btn primary" disabled={saving || !addSp || !addPrice} onClick={doAdd}>
              {saving ? "…" : <><Icon name="check" size={15} /> Thêm</>}
            </button>
          </div>
        )}
      </section>

      <section class="card pl-list">
        {items.map((it) => (
          <div class={"pl-row" + (editSp === it.sp ? " editing" : "")} key={it.sp}>
            <span class="pl-sp"><code>{it.sp}</code></span>
            {editSp === it.sp ? (
              <div class="pl-actions">
                <input class="pl-edit-inp" type="text" inputMode="numeric" value={editVal} autofocus
                  onFocus={(e: any) => e.target.select()} onInput={(e: any) => setEditVal(e.target.value)} />
                <button class="btn small primary" disabled={saving} onClick={() => saveEdit(it.sp)}>{saving ? "…" : <Icon name="save" size={15} />}</button>
                <button class="btn small" onClick={() => setEditSp(null)}><Icon name="close" size={15} /></button>
              </div>
            ) : (
              <div class="pl-actions">
                <span class="pl-price">{money(it.price)}</span>
                <button class="icon-btn" title="Sửa giá" onClick={() => startEdit(it.sp, it.price)}><Icon name="edit" size={16} /></button>
                <button class="icon-btn" title="Lịch sử SP này" onClick={() => loadHistory(it.sp)}><Icon name="clock" size={16} /></button>
              </div>
            )}
          </div>
        ))}
        {!items.length && <div class="muted small pl-empty">{q ? "Không thấy SP khớp." : "Bảng giá trống — bấm Thêm SP."}</div>}
      </section>

      <section class="card">
        <div class="row space">
          <label class="card-label"><Icon name="clock" size={15} /> Lịch sử đổi giá {histSp ? `— ${histSp}` : ""}</label>
          {history !== null && <button class="btn small" onClick={() => loadHistory(null)}>Toàn bộ</button>}
        </div>
        {history === null ? (
          <button class="btn small block" onClick={() => loadHistory(null)}>Xem lịch sử</button>
        ) : !history.length ? (
          <p class="muted small">Chưa có thay đổi nào.</p>
        ) : (
          <ul class="hist">
            {history.map((h, i) => (
              <li key={i}>
                <div><b>{h.sp}</b>: {priceLabel(h.old_price)} → <b>{priceLabel(h.new_price)}</b>
                  {h.new_price == null && <span class="owe"> (xoá)</span>}{h.old_price == null && <span class="pl-new"> (mới)</span>}</div>
                <div class="muted small">{h.changed_by || "?"} · {fmtDateTimeVN(h.changed_at)}</div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section class="card">
        <label class="card-label"><Icon name="users" size={15} /> Khách đang dùng ({list.customers.length})</label>
        {!list.customers.length ? (
          <p class="muted small">Chưa có khách nào gắn bảng giá này.</p>
        ) : (
          <div class="pl-cust">
            {list.customers.map((c) => (
              <a class="pl-cust-chip" href={`#/khach/${encodeURIComponent(c.key)}`} key={c.key}>
                <Icon name="user" size={14} /> {c.name}
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
