// Trang THU TIỀN HÀNG LOẠT (#/thu-tien, menu ☰ Thêm) — liệt kê MỌI khách đang có
// đơn nợ, tick nhiều khách + số tiền mỗi khách → thu 1 lần. Mỗi khách là 1 giao
// dịch thu gộp độc lập (server fan-out vào lõi thu gộp cũ). Chỉ văn phòng.
// Số thu mỗi khách chặn trần theo "thu được qua đơn" (collectable). Nợ KiotViet chỉ
// tham chiếu. Nối: api.getDebtors/collectBatch, ui/SearchBar, ui/feedback, realtime.
import { useEffect, useMemo, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import { getDebtors, collectBatch, isOffice, type Debtor, type CollectResult } from "../api";
import { onRealtime } from "../realtime";
import { money, parseMoney, foldVN } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState, EmptyState } from "../ui/states";
import { SearchBar } from "../ui/SearchBar";
import { Icon } from "../ui/Icon";

type Data = { debtors: Debtor[]; total_collectable: number; count: number };
let cache: Data | null = null;
onRealtime((e) => {
  if (["order_changed", "orders_changed", "customer_changed", "resync"].includes(e.type)) cache = null;
});

export function CollectMoney() {
  const office = isOffice();
  const [data, setData] = useState<Data | null>(cache);
  const [err, setErr] = useState("");
  const [method, setMethod] = useState<"Cash" | "Transfer">("Cash");
  const [query, setQuery] = useState("");
  // key → số tiền (chuỗi) đang chọn thu. Không có key = chưa chọn.
  const [picked, setPicked] = useState<Map<string, string>>(() => new Map());
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<CollectResult[] | null>(null);

  const reload = async (soft = false) => {
    try {
      if (!soft) setData(cache);
      const next = await getDebtors();
      cache = next;
      setData(next);
      setErr("");
      // Bỏ chọn khách đã hết nợ (không còn trong danh sách).
      setPicked((prev) => {
        const alive = new Set(next.debtors.map((d) => d.key));
        const m = new Map<string, string>();
        for (const [k, v] of prev) if (alive.has(k)) m.set(k, v);
        return m;
      });
    } catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => { reload(); }, []);
  // Thu xong / khách đổi nợ → cập nhật danh sách nền (không nháy màn khi đang thao tác).
  useEffect(() => {
    const off = onRealtime((e) => {
      if (["order_changed", "orders_changed", "customer_changed", "resync"].includes(e.type)) {
        if (!busy) reload(true);
      }
    });
    return off;
  }, [busy]);

  const debtors = data?.debtors || [];
  const normalizedQuery = foldVN(query.trim());
  const shown = useMemo(
    () => normalizedQuery ? debtors.filter((d) => foldVN(d.name).includes(normalizedQuery)) : debtors,
    [debtors, normalizedQuery],
  );
  const selectable = useMemo(() => shown.filter((d) => !d.blocked && d.collectable > 0), [shown]);

  const toggle = (d: Debtor) => {
    if (d.blocked) { toast("Khách chưa liên kết KiotViet — không thu được", "err"); return; }
    setPicked((prev) => {
      const m = new Map(prev);
      if (m.has(d.key)) m.delete(d.key);
      else m.set(d.key, String(d.collectable));
      return m;
    });
  };
  const setAmt = (key: string, v: string) => {
    setPicked((prev) => { const m = new Map(prev); m.set(key, v); return m; });
  };
  const allPicked = selectable.length > 0 && selectable.every((d) => picked.has(d.key));
  const toggleAll = () => {
    setPicked((prev) => {
      const m = new Map(prev);
      if (allPicked) { for (const d of selectable) m.delete(d.key); }
      else { for (const d of selectable) if (!m.has(d.key)) m.set(d.key, String(d.collectable)); }
      return m;
    });
  };

  // Khoản thu hợp lệ: đã chọn, số > 0, ≤ collectable (chặn trần như server).
  const collections = useMemo(() => {
    const out: { customer_key: string; amount: number; over: boolean; name: string; cap: number }[] = [];
    const byKey = new Map(debtors.map((d) => [d.key, d]));
    for (const [key, str] of picked) {
      const d = byKey.get(key); if (!d) continue;
      const amount = parseMoney(str);
      out.push({ customer_key: key, amount, over: amount > d.collectable, name: d.name, cap: d.collectable });
    }
    return out;
  }, [picked, debtors]);
  const valid = collections.filter((c) => c.amount > 0 && !c.over);
  const totalPick = valid.reduce((s, c) => s + c.amount, 0);
  const anyOver = collections.some((c) => c.over);

  const submit = async () => {
    if (busy || !valid.length) return;
    if (anyOver) { toast("Có khách nhập vượt số thu được — sửa lại", "err"); return; }
    const label = method === "Cash" ? "tiền mặt" : "chuyển khoản";
    if (!(await confirmDialog(
      `Thu ${money(totalPick)} (${label}) từ ${valid.length} khách?`,
      { okLabel: "Thu tiền" }))) return;
    setBusy(true);
    setResults(null);
    try {
      const r = await collectBatch({
        method,
        collections: valid.map((c) => ({ customer_key: c.customer_key, amount: c.amount })),
      });
      setResults(r.results);
      // Bỏ chọn khách đã thu thành công.
      const okKeys = new Set(r.results.filter((x) => x.ok).map((x) => x.key));
      setPicked((prev) => { const m = new Map(prev); for (const k of okKeys) m.delete(k); return m; });
      if (r.fail_count === 0) toast(`✅ Đã thu ${money(r.total_collected)} từ ${r.ok_count} khách`, "ok");
      else toast(`Thu ${r.ok_count} khách (${money(r.total_collected)}) · ${r.fail_count} khách lỗi`, "err");
      cache = null;
      await reload(true);
    } catch (ex: any) {
      toast(`❌ ${ex.message}`, "err");
      await reload(true);
    } finally { setBusy(false); }
  };

  if (!office) {
    return (
      <div>
        <PageHead fallback="#/home" title="Thu tiền hàng loạt" />
        <div class="card muted small">🔒 Chỉ văn phòng mới được thu tiền.</div>
      </div>
    );
  }
  if (err) return <ErrorState msg={err} onRetry={() => reload()} />;
  if (!data) return <Loading />;

  return (
    <div class="collect">
      <PageHead fallback="#/home" title="Thu tiền hàng loạt"
        sub={<>{data.count} khách đang nợ · thu được {money(data.total_collectable)}</>} />

      {results && (
        <div class="card collect-results">
          <div class="row space"><b>Kết quả lần thu</b>
            <button class="btn small ghost" onClick={() => setResults(null)}><Icon name="close" size={14} /> Ẩn</button></div>
          <ul class="collect-res-list">
            {results.map((r) => (
              <li class={"collect-res " + (r.ok ? "ok" : "bad")} key={r.key}>
                <Icon name={r.ok ? "check" : "close"} size={15} />
                <span class="collect-res-name">{r.name}</span>
                <span class="collect-res-msg">
                  {r.ok
                    ? <>thu {money(r.collected)}{r.capped ? <> <span class="collect-cap">(tối đa qua đơn)</span></> : null}</>
                    : <span class="collect-err">{r.error || "lỗi"}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div class="collect-search"><SearchBar value={query} onInput={setQuery} placeholder="Tìm khách…" /></div>

      {selectable.length > 0 && (
        <button class="collect-all" onClick={toggleAll}>
          <Icon name="check" size={14} /> {allPicked ? "Bỏ chọn tất cả" : `Chọn tất cả (${selectable.length} khách) — thu đủ`}
        </button>
      )}

      {shown.length === 0 ? (
        <EmptyState>{query ? "Không có khách khớp tìm kiếm" : "Không có khách nào đang nợ."}</EmptyState>
      ) : (
        <ul class="collect-list">
          {shown.map((d) => {
            const sel = picked.has(d.key);
            const amtStr = picked.get(d.key) ?? "";
            const amt = parseMoney(amtStr);
            const over = amt > d.collectable;
            const kvDiff = d.kv_debt != null && Math.abs(Number(d.kv_debt) - d.collectable) > 1;
            return (
              <li class={"collect-row" + (sel ? " sel" : "") + (d.blocked ? " blocked" : "")} key={d.key}>
                <div class="collect-main" onClick={() => toggle(d)}>
                  <span class="collect-check" aria-hidden="true">
                    {sel ? <Icon name="check" size={15} /> : null}
                  </span>
                  <a class="collect-name" href={`#/khach/${encodeURIComponent(d.key)}`} onClick={(e: any) => e.stopPropagation()}>
                    {d.name}
                  </a>
                  <span class="collect-amt-col">
                    <b class="collect-collectable">{money(d.collectable)}</b>
                    <span class="muted small">{d.order_count} đơn{kvDiff ? ` · nợ KV ${money(Number(d.kv_debt))}` : ""}</span>
                  </span>
                </div>
                {d.blocked && <div class="collect-note">Chưa liên kết KiotViet — không thu được</div>}
                {sel && !d.blocked && (
                  <div class="collect-edit">
                    <span class="muted small">Thu:</span>
                    <input inputMode="numeric" value={amtStr} class={over ? "over" : ""}
                      onInput={(e: any) => setAmt(d.key, e.target.value)} />
                    <button type="button" class="collect-max" onClick={() => setAmt(d.key, String(d.collectable))}>
                      Đủ {money(d.collectable)}
                    </button>
                    {over && <span class="collect-err small">Vượt số thu được (tối đa {money(d.collectable)})</span>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {valid.length > 0 && (
        <div class="collect-bar">
          <div class="collect-bar-info">
            <div class="seg pay-method collect-method" role="tablist">
              <button class={method === "Cash" ? "seg-btn active" : "seg-btn"} onClick={() => setMethod("Cash")}>
                <Icon name="banknote" size={15} /> TM
              </button>
              <button class={method === "Transfer" ? "seg-btn active" : "seg-btn"} onClick={() => setMethod("Transfer")}>
                <Icon name="bank" size={15} /> CK
              </button>
            </div>
            <div class="collect-bar-sum"><b>{money(totalPick)}</b><span class="muted small">{valid.length} khách</span></div>
          </div>
          <button class={"btn primary block" + (busy || anyOver ? " faded" : "")} disabled={busy}
            onClick={submit}>
            {busy ? "Đang thu…" : `Thu ${money(totalPick)} (${method === "Cash" ? "TM" : "CK"})`}
          </button>
        </div>
      )}
    </div>
  );
}
