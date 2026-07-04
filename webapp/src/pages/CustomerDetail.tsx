// Chi tiết 1 khách (#/khach/:key) — sửa bảng giá riêng (personal_price_list) +
// pattern nhận diện (detectPatterns) + list đơn của khách (compact, bấm → đơn).
// API: getCustomer / updateCustomer / getCustomerOrders / refreshCustomerDebt.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getCustomer, updateCustomer, getCustomerOrders, refreshCustomerDebt,
  getCustomerPriceList, type CustomerPriceList,
  getPriceLists, type PriceListSummary,
  type CustomerDetail as Cust,
} from "../api";
import { money, parseMoney } from "../format";
import { CompactOrderCard } from "../detail/CompactOrderCard";
import { onRealtime } from "../realtime";
import { Loading, ErrorState } from "../ui/states";

type Row = { sp: string; price: string };

export function CustomerDetail({ ckey }: { ckey: string }) {
  const [cust, setCust] = useState<Cust | null>(null);
  const [err, setErr] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [patterns, setPatterns] = useState("");
  const [savingP, setSavingP] = useState(false);
  const [savingPat, setSavingPat] = useState(false);
  const [msg, setMsg] = useState("");
  const [debtBusy, setDebtBusy] = useState(false);
  const [effective, setEffective] = useState<CustomerPriceList | null>(null);
  const [priceLists, setPriceLists] = useState<PriceListSummary[]>([]);
  const [savingPl, setSavingPl] = useState(false);

  const [orders, setOrders] = useState<any[]>([]);
  const [oPage, setOPage] = useState(1);
  const [oTotalPages, setOTotalPages] = useState(1);
  const [oTotal, setOTotal] = useState(0);
  const [oLoading, setOLoading] = useState(false);
  const seq = useRef(0);

  const hydrate = (c: Cust) => {
    setCust(c);
    const ppl = c.personal_price_list || {};
    setRows(Object.keys(ppl).map((sp) => ({ sp, price: String(ppl[sp]) })));
    setPatterns((c.detectPatterns || []).join(", "));
  };

  const loadOrders = async (page: number) => {
    const my = ++seq.current;
    setOLoading(true);
    try {
      const r = await getCustomerOrders(ckey, page);
      if (my !== seq.current) return;
      setOTotalPages(r.total_pages || 1);
      setOTotal(r.total || 0);
      setOrders((prev) => (page === 1 ? r.orders : [...prev, ...r.orders]));
      setOPage(r.page || page);
    } finally {
      if (my === seq.current) setOLoading(false);
    }
  };

  const loadEffective = () => getCustomerPriceList(ckey).then(setEffective).catch(() => setEffective(null));

  const reload = () => {
    getCustomer(ckey).then(hydrate).catch((e) => setErr(e.message));
    loadOrders(1);
    loadEffective();
  };

  useEffect(() => { getPriceLists().then(setPriceLists).catch(() => {}); }, []);

  // Gán khách vào 1 bảng giá chung (hoặc bỏ gán) → lưu + tải lại giá hiệu lực
  const changePriceList = async (id: string) => {
    setSavingPl(true); setErr(""); setMsg("");
    try {
      hydrate(await updateCustomer(ckey, { price_list: id || null }));
      loadEffective();
      setMsg("✅ Đã đổi bảng giá chung");
    } catch (e: any) { setErr(e.message); } finally { setSavingPl(false); }
  };

  useEffect(() => {
    reload();
  }, [ckey]);

  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "order_changed") {
        clearTimeout(t);
        t = setTimeout(reload, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [ckey]);

  const setRow = (i: number, k: keyof Row, v: string) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const addRow = () => setRows((rs) => [...rs, { sp: "", price: "" }]);
  const delRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));

  const savePrices = async () => {
    setSavingP(true); setErr(""); setMsg("");
    const ppl: Record<string, number> = {};
    for (const r of rows) {
      const sp = r.sp.trim();
      const p = parseMoney(r.price);
      if (sp && p > 0) ppl[sp] = p;
    }
    try {
      hydrate(await updateCustomer(ckey, { personal_price_list: ppl }));
      loadEffective();
      setMsg("✅ Đã lưu bảng giá");
    } catch (e: any) { setErr(e.message); } finally { setSavingP(false); }
  };

  const savePatterns = async () => {
    setSavingPat(true); setErr(""); setMsg("");
    const list = patterns.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    try {
      hydrate(await updateCustomer(ckey, { detectPatterns: list }));
      setMsg("✅ Đã lưu pattern nhận diện");
    } catch (e: any) { setErr(e.message); } finally { setSavingPat(false); }
  };

  const doRefreshDebt = async () => {
    setDebtBusy(true);
    try {
      const { debt } = await refreshCustomerDebt(ckey);
      setCust((c) => (c ? { ...c, debt } : c));
    } catch { /* ignore */ } finally { setDebtBusy(false); }
  };

  if (err && !cust) return <div class="prod-detail"><BackLink fallback="#/customers" /><ErrorState msg={err} onRetry={reload} /></div>;
  if (!cust) return <div class="prod-detail"><Loading /></div>;

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/customers" />
        <div>
          <div class="prod-sp">{cust.name}</div>
          <div class="muted small">{cust.kh_id ? `KV: ${cust.kh_id} · ` : ""}{cust.key}</div>
        </div>
      </div>

      {cust.note ? (
        <section class="card cust-note">
          <label class="card-label">📝 Ghi chú</label>
          <p class="cust-note-text">{cust.note}</p>
        </section>
      ) : null}

      <section class="card">
        <div class="row space">
          <b>Công nợ</b>
          <span class={Number(cust.debt) > 0 ? "owe" : "muted"}>
            {cust.debt != null ? `${money(Number(cust.debt) || 0)}đ` : "—"}
          </span>
        </div>
        <button class="btn small" disabled={debtBusy} onClick={doRefreshDebt}>
          {debtBusy ? "Đang lấy…" : "🔄 Cập nhật nợ KiotViet"}
        </button>
      </section>

      {msg && <p class="muted small">{msg}</p>}
      {err && <p class="error">{err}</p>}

      <section class="card">
        <label class="card-label">Bảng giá riêng (đè bảng giá chung)</label>
        <table class="invoice-table">
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><input value={r.sp} placeholder="Mã SP" onInput={(e: any) => setRow(i, "sp", e.target.value)} /></td>
                <td class="num"><input class="num-inp" type="text" inputMode="numeric" value={r.price} placeholder="Giá" onFocus={(e: any) => e.target.select()} onInput={(e: any) => setRow(i, "price", e.target.value)} /></td>
                <td><button class="btn small" onClick={() => delRow(i)}>✕</button></td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={3} class="muted small">Chưa có giá riêng — thêm dòng bên dưới.</td></tr>}
          </tbody>
        </table>
        <div class="row">
          <button class="btn small" onClick={addRow}>➕ Thêm SP</button>
          <button class="btn primary" disabled={savingP} onClick={savePrices}>{savingP ? "Đang lưu…" : "💾 Lưu bảng giá"}</button>
        </div>
      </section>

      <section class="card">
        <label class="card-label">Bảng giá chung (gán cho khách)</label>
        <select class="pl-select" disabled={savingPl} value={String(cust.price_list ?? "")}
          onChange={(e: any) => changePriceList(e.target.value)}>
          <option value="">— Không gắn —</option>
          {priceLists.map((pl) => (
            <option key={pl.id} value={pl.id}>{pl.name} ({pl.product_count} SP)</option>
          ))}
        </select>
        {savingPl && <p class="muted small">Đang lưu…</p>}
      </section>

      <details class="card collapse-card">
        <summary class="card-label collapse-sum">
          Bảng giá hiệu lực{effective?.name ? ` — ${effective.name}` : ""}
          {effective?.items?.length ? <span class="muted small"> ({effective.items.length} SP)</span> : null}
        </summary>
        {!effective ? (
          <p class="muted small">Đang tải…</p>
        ) : effective.items.length ? (
          <table class="invoice-table">
            <tbody>
              {effective.items.map((it) => {
                const rieng = !!(cust.personal_price_list && it.sp in cust.personal_price_list);
                return (
                  <tr key={it.sp}>
                    <td>{it.sp} {rieng ? <span class="tag-new">riêng</span> : <span class="muted small">chung</span>}</td>
                    <td class="num">{money(it.price)}đ</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p class="muted small">Khách chưa gắn bảng giá chung nào.</p>
        )}
      </details>

      <section class="card">
        <label class="card-label">Pattern nhận diện (cách nhau dấu phẩy)</label>
        <textarea rows={3} value={patterns} placeholder="vd: loan phu, chị loàn, lp" onInput={(e: any) => setPatterns(e.target.value)} />
        <button class="btn primary" disabled={savingPat} onClick={savePatterns}>{savingPat ? "Đang lưu…" : "💾 Lưu pattern"}</button>
      </section>

      <section class="card">
        <label class="card-label">Đơn của khách {oTotal > 0 ? `(${oTotal})` : ""}</label>
        <ul class="order-list">
          {orders.map((o) => <li key={o.thread_id}><CompactOrderCard o={o} /></li>)}
        </ul>
        {!oLoading && !orders.length && <p class="muted small">Chưa có đơn nào của khách này.</p>}
        {oLoading && <p class="muted center small">Đang tải…</p>}
        {!oLoading && oPage < oTotalPages && (
          <button class="btn small wide" onClick={() => loadOrders(oPage + 1)}>Tải thêm đơn</button>
        )}
      </section>
    </div>
  );
}
