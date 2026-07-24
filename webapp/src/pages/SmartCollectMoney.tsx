// Trang THU TIỀN NHANH (#/thu-tien-nhanh).
// Dùng cùng API thu gộp với CollectMoney nhưng tối ưu cho một phiên thu:
// đặt mục tiêu → hệ thống tự xếp khách ưu tiên → điền số tiền hợp lệ → thu một lần.
import { useEffect, useMemo, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getDebtors, getCustomerOrders, collectBatch, isOffice, type Debtor, type CollectResult } from "../api";
import { onRealtime } from "../realtime";
import { money, parseMoney, foldVN } from "../format";
import { confirmDialog, toast } from "../ui/feedback";
import { ErrorState, EmptyState, Loading } from "../ui/states";
import { SearchBar } from "../ui/SearchBar";
import { Icon } from "../ui/Icon";

type Data = { debtors: Debtor[]; total_collectable: number; count: number };
type Filter = "smart" | "largest" | "one-order" | "selected" | "blocked";
const MAX_BATCH = 60;
const TARGETS = [1_000_000, 3_000_000, 5_000_000];

let cache: Data | null = null;
onRealtime((e) => {
  if (["order_changed", "orders_changed", "customer_changed", "resync"].includes(e.type)) cache = null;
});

function priorityScore(d: Debtor): number {
  // Ưu tiên khoản lớn nhưng thưởng khách chỉ có 1 đơn: ít lượt thao tác hơn.
  return d.collectable + (d.order_count === 1 ? 250_000 : 0);
}

function sortSmart(debtors: Debtor[]): Debtor[] {
  return [...debtors].sort((a, b) => priorityScore(b) - priorityScore(a));
}

export function SmartCollectMoney() {
  const office = isOffice();
  const [data, setData] = useState<Data | null>(cache);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("smart");
  const [method, setMethod] = useState<"Cash" | "Transfer">("Cash");
  const [targetText, setTargetText] = useState("");
  const [picked, setPicked] = useState<Map<string, string>>(() => new Map());
  const [busy, setBusy] = useState(false);
  const [openingKey, setOpeningKey] = useState<string | null>(null);
  const [results, setResults] = useState<CollectResult[] | null>(null);

  const reload = async (soft = false) => {
    try {
      if (!soft) setData(cache);
      const next = await getDebtors();
      cache = next;
      setData(next);
      setErr("");
      setPicked((prev) => {
        const alive = new Set(next.debtors.map((d) => d.key));
        const nextPicked = new Map<string, string>();
        for (const [key, value] of prev) if (alive.has(key)) nextPicked.set(key, value);
        return nextPicked;
      });
    } catch (ex: any) {
      setErr(ex?.message || "Không tải được danh sách khách đang nợ");
    }
  };

  useEffect(() => { void reload(); }, []);
  useEffect(() => {
    const off = onRealtime((e) => {
      if (["order_changed", "orders_changed", "customer_changed", "resync"].includes(e.type) && !busy) {
        void reload(true);
      }
    });
    return off;
  }, [busy]);

  const debtors = data?.debtors || [];
  const byKey = useMemo(() => new Map(debtors.map((d) => [d.key, d])), [debtors]);
  const eligible = useMemo(() => sortSmart(debtors.filter((d) => !d.blocked && d.collectable > 0)), [debtors]);
  const normalized = foldVN(query.trim());
  const selectedCount = picked.size;

  const visible = useMemo(() => {
    let list = debtors;
    if (filter === "smart") list = sortSmart(list.filter((d) => !d.blocked));
    else if (filter === "largest") list = [...list].sort((a, b) => b.collectable - a.collectable);
    else if (filter === "one-order") list = list.filter((d) => !d.blocked && d.order_count === 1);
    else if (filter === "selected") list = list.filter((d) => picked.has(d.key));
    else if (filter === "blocked") list = list.filter((d) => d.blocked);
    if (normalized) list = list.filter((d) => foldVN(d.name).includes(normalized));
    return list;
  }, [debtors, filter, normalized, picked]);

  const collections = useMemo(() => {
    return [...picked].flatMap(([key, amountText]) => {
      const d = byKey.get(key);
      if (!d) return [];
      const amount = parseMoney(amountText);
      return [{ key, name: d.name, amount, cap: d.collectable, over: amount > d.collectable }];
    });
  }, [byKey, picked]);
  const valid = collections.filter((c) => c.amount > 0 && !c.over);
  const totalPick = valid.reduce((sum, c) => sum + c.amount, 0);
  const anyOver = collections.some((c) => c.over);
  const selectedCap = collections.reduce((sum, c) => sum + c.cap, 0);

  const setAmount = (key: string, value: string) => {
    setPicked((prev) => {
      const next = new Map(prev);
      next.set(key, value);
      return next;
    });
  };

  const pickCustomer = (d: Debtor) => {
    if (d.blocked) {
      toast("Khách chưa liên kết KiotViet — không thể thu", "err");
      return;
    }
    setPicked((prev) => {
      const next = new Map(prev);
      if (next.has(d.key)) next.delete(d.key);
      else if (next.size < MAX_BATCH) next.set(d.key, String(d.collectable));
      else toast(`Một phiên thu tối đa ${MAX_BATCH} khách`, "err");
      return next;
    });
  };

  const applyTarget = (target: number) => {
    const next = new Map<string, string>();
    let remaining = Math.max(0, target);
    for (const d of eligible) {
      if (remaining <= 0 || next.size >= MAX_BATCH) break;
      const amount = Math.min(d.collectable, remaining);
      next.set(d.key, String(amount));
      remaining -= amount;
    }
    setTargetText(target ? String(target) : "");
    setPicked(next);
    if (!next.size) toast("Chưa có khách đủ điều kiện để thu", "err");
    else toast(`Đã xếp ${next.size} khách theo mục tiêu ${money(target)} đ`, "ok");
  };

  const clearPicked = () => setPicked(new Map());

  const openCustomerPayment = async (d: Debtor) => {
    if (d.blocked) return;
    const directSource = Number(d.source_thread_id);
    if (Number.isFinite(directSource) && directSource > 0) {
      window.location.hash = `#/order/${directSource}/thanh-toan`;
      return;
    }
    // Tương thích với server đang chạy bundle cũ chưa trả source_thread_id:
    // lấy một đơn của khách rồi để payment-context tải toàn bộ đơn nợ.
    setOpeningKey(d.key);
    try {
      const response = await getCustomerOrders(d.key, 1);
      const source = (response.orders || []).find((o: any) => Number(o.remaining || 0) > 0) || response.orders?.[0];
      if (!source?.thread_id) throw new Error("Không tìm thấy đơn của khách để mở trang thu tiền");
      window.location.hash = `#/order/${source.thread_id}/thanh-toan`;
    } catch (ex: any) {
      toast(ex?.message || "Không mở được trang thu tiền của khách", "err");
    } finally {
      setOpeningKey(null);
    }
  };

  const submit = async () => {
    if (busy || !valid.length) return;
    if (valid.length > MAX_BATCH) {
      toast(`Một phiên thu tối đa ${MAX_BATCH} khách`, "err");
      return;
    }
    if (anyOver) {
      toast("Có khách nhập vượt số thu được — sửa lại", "err");
      return;
    }
    const label = method === "Cash" ? "tiền mặt" : "chuyển khoản";
    if (!(await confirmDialog(`Thu ${money(totalPick)} đ (${label}) từ ${valid.length} khách?`, { okLabel: "Thu ngay" }))) return;
    setBusy(true);
    setResults(null);
    try {
      const response = await collectBatch({
        method,
        collections: valid.map((c) => ({ customer_key: c.key, amount: c.amount })),
      });
      setResults(response.results);
      const okKeys = new Set(response.results.filter((r) => r.ok).map((r) => r.key));
      setPicked((prev) => {
        const next = new Map(prev);
        for (const key of okKeys) next.delete(key);
        return next;
      });
      toast(response.fail_count === 0
        ? `✅ Đã thu ${money(response.total_collected)} đ từ ${response.ok_count} khách`
        : `Thu được ${response.ok_count} khách · ${response.fail_count} khách lỗi`, response.fail_count === 0 ? "ok" : "err");
      cache = null;
      await reload(true);
    } catch (ex: any) {
      toast(`❌ ${ex?.message || "Thu tiền thất bại"}`, "err");
      await reload(true);
    } finally {
      setBusy(false);
    }
  };

  if (!office) {
    return <div class="smart-collect-denied"><BackLink fallback="#/home" /><div class="card muted small">🔒 Chỉ văn phòng mới được thu tiền.</div></div>;
  }
  if (err && !data) return <ErrorState msg={err} onRetry={() => reload()} />;
  if (!data) return <Loading />;

  const filterCounts: Record<Filter, number> = {
    smart: eligible.length,
    largest: eligible.length,
    "one-order": eligible.filter((d) => d.order_count === 1).length,
    selected: selectedCount,
    blocked: debtors.filter((d) => d.blocked).length,
  };

  return (
    <div class="smart-collect">
      <section class="smart-collect-hero">
        <div class="smart-collect-kicker"><Icon name="zap" size={14} /> TRẠM THU TIỀN · THAO TÁC NHANH</div>
        <div class="smart-collect-head">
          <div>
            <h1>Thu tiền nhanh</h1>
            <p>Đặt mục tiêu, để hệ thống xếp khách và gom thành một phiên thu.</p>
          </div>
          <div class="smart-collect-total"><strong>{money(data.total_collectable)}</strong><span>đang có thể thu</span></div>
        </div>
        <div class="smart-collect-stats">
          <span><b>{data.count}</b> khách đang nợ</span>
          <span><b>{eligible.length}</b> khách sẵn sàng</span>
          <span><b>{selectedCount}</b> đã xếp phiên</span>
        </div>
      </section>

      <section class="smart-collect-planner">
        <div class="smart-planner-copy"><span class="smart-step">01</span><div><b>Chọn mục tiêu phiên thu</b><small>Hệ thống tự đi từ khoản ưu tiên cao xuống thấp.</small></div></div>
        <div class="smart-target-row">
          <div class="smart-target-input"><input inputMode="numeric" value={targetText} placeholder="Ví dụ 3.000.000" onInput={(e: any) => setTargetText(e.target.value)} /><span>đ</span></div>
          <button class="smart-auto" disabled={!parseMoney(targetText) || !eligible.length} onClick={() => applyTarget(parseMoney(targetText))}><Icon name="zap" size={15} /> Xếp tự động</button>
        </div>
        <div class="smart-presets"><span>Gợi ý:</span>{TARGETS.map((amount) => <button key={amount} onClick={() => applyTarget(amount)}>{money(amount)} đ</button>)}<button onClick={clearPicked}>Xoá phiên</button></div>
        {selectedCount > 0 && <div class="smart-plan-note"><Icon name="check" size={14} /> Đã xếp {selectedCount} khách · {money(totalPick)} đ <span>trần {money(selectedCap)} đ</span></div>}
      </section>

      {results && (
        <section class="smart-collect-results">
          <div class="smart-section-head"><div><span class="smart-step">✓</span><b>Kết quả phiên vừa thu</b></div><button class="smart-icon-btn" onClick={() => setResults(null)}><Icon name="close" size={15} /></button></div>
          <div class="smart-results-grid">{results.map((result) => <div class={`smart-result ${result.ok ? "ok" : "bad"}`} key={result.key}><Icon name={result.ok ? "check" : "close"} size={14} /><b>{result.name}</b><span>{result.ok ? `${money(result.collected)} đ` : (result.error || "Lỗi")}</span></div>)}</div>
        </section>
      )}

      <div class="smart-collect-toolbar">
        <SearchBar value={query} onInput={setQuery} placeholder="Tìm tên khách…" />
        <div class="smart-filters" role="tablist" aria-label="Lọc khách đang nợ">
          <button class={filter === "smart" ? "active" : ""} onClick={() => setFilter("smart")}><Icon name="zap" size={13} /> Gợi ý <b>{filterCounts.smart}</b></button>
          <button class={filter === "largest" ? "active" : ""} onClick={() => setFilter("largest")}>Nợ lớn <b>{filterCounts.largest}</b></button>
          <button class={filter === "one-order" ? "active" : ""} onClick={() => setFilter("one-order")}>1 đơn <b>{filterCounts["one-order"]}</b></button>
          <button class={filter === "selected" ? "active" : ""} onClick={() => setFilter("selected")}>Đã chọn <b>{filterCounts.selected}</b></button>
          {filterCounts.blocked > 0 && <button class={filter === "blocked" ? "active" : ""} onClick={() => setFilter("blocked")}>Chưa nối <b>{filterCounts.blocked}</b></button>}
        </div>
      </div>

      {err && <p class="smart-collect-stale">⚠️ {err}</p>}
      {visible.length === 0 ? <EmptyState>{query ? "Không có khách khớp tìm kiếm" : filter === "selected" ? "Chưa có khách trong phiên thu" : "Không có khách phù hợp."}</EmptyState> : (
        <div class="smart-customer-list">
          {visible.map((d, index) => {
            const selected = picked.has(d.key);
            const amountText = picked.get(d.key) || "";
            const amount = parseMoney(amountText);
            const over = amount > d.collectable;
            const kvDiff = d.kv_debt != null && Math.abs(Number(d.kv_debt) - d.collectable) > 1;
            return <article class={`smart-customer ${selected ? "selected" : ""} ${d.blocked ? "blocked" : "is-link"} ${openingKey === d.key ? "opening" : ""}`} key={d.key} style={{ animationDelay: `${Math.min(index, 10) * 28}ms` }} role={d.blocked ? undefined : "link"} tabIndex={d.blocked ? undefined : 0}
              onClick={(e: any) => { if (!e.target.closest("button, input, a")) openCustomerPayment(d); }}
              onKeyDown={(e: any) => { if ((e.key === "Enter" || e.key === " ") && !d.blocked) { e.preventDefault(); openCustomerPayment(d); } }}>
              <div class="smart-customer-main">
                <button class="smart-check" aria-label={selected ? `Bỏ chọn ${d.name}` : `Chọn ${d.name}`} disabled={d.blocked} onClick={() => pickCustomer(d)}>{selected && <Icon name="check" size={15} />}</button>
                <div class="smart-customer-copy"><div class="smart-customer-label"><span>{filter === "smart" && !d.blocked ? `ƯU TIÊN ${String(index + 1).padStart(2, "0")}` : d.blocked ? "CHƯA LIÊN KẾT" : `${d.order_count} ĐƠN ĐANG NỢ`}</span></div><a href={d.blocked ? undefined : (d.source_thread_id ? `#/order/${d.source_thread_id}/thanh-toan` : undefined)} onClick={(e: any) => { e.stopPropagation(); if (!d.source_thread_id) { e.preventDefault(); void openCustomerPayment(d); } }}>{openingKey === d.key ? "Đang mở…" : d.name}</a><small>{d.order_count} đơn · {kvDiff ? `nợ KV ${money(Number(d.kv_debt))} đ` : "bấm card để mở thu tiền"}</small></div>
                <div class="smart-customer-money"><strong>{money(d.collectable)}</strong><span>đ</span></div>
                {!d.blocked && <button class="smart-add" onClick={() => pickCustomer(d)}>{selected ? "Bỏ" : "+ Đủ"}</button>}
              </div>
              {d.blocked && <div class="smart-blocked-note"><Icon name="lock" size={13} /> Cần liên kết KiotViet trước khi thu</div>}
              {selected && !d.blocked && <div class="smart-customer-edit"><label>Thu</label><input inputMode="numeric" value={amountText} class={over ? "over" : ""} onInput={(e: any) => setAmount(d.key, e.target.value)} /><button onClick={() => setAmount(d.key, String(d.collectable))}>Đủ</button><button onClick={() => setAmount(d.key, String(Math.max(1, Math.floor(d.collectable / 2))))}>1/2</button>{over && <small>Vượt trần {money(d.collectable)} đ</small>}</div>}
            </article>;
          })}
        </div>
      )}

      {valid.length > 0 && <div class="smart-collect-bar"><div class="smart-bar-summary"><div><b>{money(totalPick)} đ</b><span>{valid.length} khách · {method === "Cash" ? "tiền mặt" : "chuyển khoản"}</span></div><div class="smart-method"><button class={method === "Cash" ? "active" : ""} onClick={() => setMethod("Cash")}><Icon name="banknote" size={14} /> TM</button><button class={method === "Transfer" ? "active" : ""} onClick={() => setMethod("Transfer")}><Icon name="bank" size={14} /> CK</button></div></div><button class="smart-submit" disabled={busy || anyOver} onClick={submit}>{busy ? "Đang ghi nhận…" : <><Icon name="zap" size={16} /> Thu {money(totalPick)} đ</>}</button></div>}
    </div>
  );
}
