// Chi tiết kho 1 product — danh sách mọi thùng + tình trạng (Trong kho / Đã xuất
// đơn #x / Đã giao). GET /api/inventory/:code (all_boxes). Nhóm tồn theo size ở đầu.
// Thùng đã xuất link tới đơn. Realtime production_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { inventoryDetail, productOrders, searchKiotvietProducts, linkProductKiotviet, unlinkProductKiotviet, currentUser, soVN, type InvDetail, type InvBox, type InvOrderRef, type KvProduct } from "../api";
import { confirmDialog, toast } from "../ui/feedback";
import { useScrollLock } from "../useScrollLock";
import { money } from "../format";
import { onRealtime } from "../realtime";
import { Loading, ErrorState } from "../ui/states";

function fmtWhen(iso?: string): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return "";
  const [, , mo, d, hh, mi] = m;
  return `${d}/${mo} ${hh}:${mi}`;
}

export function InventoryDetail({ code }: { code: string }) {
  const [inv, setInv] = useState<InvDetail | null>(null);
  const [err, setErr] = useState("");
  const isAdmin = currentUser()?.role === "admin";
  // Liên kết KiotViet từng cái (modal tìm + chọn)
  const [linkOpen, setLinkOpen] = useState(false);
  const [kvQ, setKvQ] = useState("");
  const [kvRes, setKvRes] = useState<KvProduct[]>([]);
  const [kvLoading, setKvLoading] = useState(false);
  useScrollLock(linkOpen);
  useEffect(() => {
    if (!linkOpen) return;
    const q = kvQ.trim();
    if (q.length < 2) { setKvRes([]); return; }
    let alive = true;
    setKvLoading(true);
    const t = setTimeout(() => {
      searchKiotvietProducts(q)
        .then((r) => { if (alive) setKvRes(r); })
        .catch(() => { if (alive) setKvRes([]); })
        .finally(() => { if (alive) setKvLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [kvQ, linkOpen]);

  // Đơn có SP này — LAZY: chỉ tải khi cuộn tới khối, phân trang "Xem thêm"
  const [ords, setOrds] = useState<InvOrderRef[]>([]);
  const [ordTotal, setOrdTotal] = useState(0);
  const [ordMore, setOrdMore] = useState(false);
  const [ordLoading, setOrdLoading] = useState(false);
  const ordStarted = useRef(false);
  const ordSecRef = useRef<HTMLElement>(null);

  const loadOrders = async (reset: boolean) => {
    setOrdLoading(true);
    const offset = reset ? 0 : ords.length;
    try {
      const r = await productOrders(code, offset, 20);
      setOrds((prev) => (reset ? r.orders : [...prev, ...r.orders]));
      setOrdTotal(r.total);
      setOrdMore(r.has_more);
    } catch { /* im */ } finally {
      setOrdLoading(false);
    }
  };

  // Đổi mã SP → reset khối đơn.
  useEffect(() => {
    ordStarted.current = false;
    setOrds([]); setOrdTotal(0); setOrdMore(false);
  }, [code]);

  // Gắn IntersectionObserver SAU khi khối render (inv đã tải) → tự tải lần đầu khi lộ.
  useEffect(() => {
    const el = ordSecRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !ordStarted.current) {
        ordStarted.current = true;
        loadOrders(true);
      }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [inv, code]);

  const openLink = () => { setKvQ(inv?.product?.name || code); setLinkOpen(true); };
  const doLink = async (kv: KvProduct) => {
    try {
      await linkProductKiotviet(code, kv.id, kv.full_name);
      toast(`✅ Liên kết ${code} → ${kv.full_name}`, "ok");
      setLinkOpen(false);
      await load();
    } catch (e: any) {
      toast(e?.message || "Liên kết lỗi", "err");
    }
  };
  const doUnlink = async () => {
    if (!(await confirmDialog("Bỏ liên kết KiotViet của mã này?"))) return;
    try {
      await unlinkProductKiotviet(code);
      toast("Đã bỏ liên kết", "ok");
      await load();
    } catch (e: any) {
      toast(e?.message || "Lỗi", "err");
    }
  };

  const load = async () => {
    try {
      setInv(await inventoryDetail(code));
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải");
    }
  };
  useEffect(() => {
    load();
  }, [code]);
  useEffect(
    () =>
      onRealtime((e) => {
        if (e.type === "resync" || e.type === "production_changed" || e.type === "inventory_changed" || e.type === "box_changed" || e.type === "order_changed") {
          load();
          if (ordStarted.current) loadOrders(true);   // đơn có SP có thể đổi
        }
      }),
    [code]
  );

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!inv) return <Loading />;
  const all: InvBox[] = inv.all_boxes;

  return (
    <div class="inv-detail">
      <div class="prod-detail-head inv-head">
        <BackLink fallback="#/kho" />
        <div class="inv-head-title">
          <div class="prod-sp big">{inv.product_code}</div>
          <div class="prod-date muted">{inv.box_count} thùng</div>
        </div>
        <div class="inv-stock-big">
          <span class="inv-stock-num">{soVN(inv.total)}</span>
          <span class="inv-stock-lbl">tồn kho</span>
        </div>
      </div>

      {/* Tên danh mục + liên kết KiotViet */}
      <section class="card prod-link">
        {inv.product?.name && <div class="prod-link-name">{inv.product.name}</div>}
        <div class="row space">
          {inv.product?.linked ? (
            <span class="kv-badge on" title={inv.product.kv_full_name || undefined}>
              🔗 Đã liên kết KiotViet{inv.product.kv_id ? ` #${inv.product.kv_id}` : ""}
            </span>
          ) : (
            <span class="kv-badge off">⚠️ Chưa liên kết KiotViet</span>
          )}
          {isAdmin && (
            inv.product?.linked
              ? <button class="btn small" onClick={doUnlink}>Bỏ liên kết</button>
              : <button class="btn small primary" onClick={openLink}>🔗 Liên kết KiotViet</button>
          )}
        </div>
      </section>

      {linkOpen && (
        <div class="modal-overlay" onClick={() => setLinkOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head">🔗 Liên kết {code} với KiotViet</div>
            <input class="inv-search" type="search" autofocus placeholder="🔎 Tìm SP KiotViet (tên/mã)…"
              value={kvQ} onInput={(e: any) => setKvQ(e.target.value)} />
            {kvLoading ? (
              <p class="muted small">Đang tìm…</p>
            ) : kvRes.length === 0 ? (
              <p class="muted small">{kvQ.trim().length < 2 ? "Gõ ≥2 ký tự để tìm." : "Không thấy SP KiotViet."}</p>
            ) : (
              <div class="inv-detail-list kv-list">
                {kvRes.map((kv) => (
                  <button class="inv-detail-row link kv-row" key={kv.id} onClick={() => doLink(kv)}>
                    <code class="inv-bc">{kv.code}</code>
                    <span class="prod-ord-text">{kv.full_name}</span>
                    <span class="muted small">#{kv.id}</span>
                  </button>
                ))}
              </div>
            )}
            <button class="btn block" style={{ marginTop: "8px" }} onClick={() => setLinkOpen(false)}>Đóng</button>
          </div>
        </div>
      )}

      {inv.groups.length > 0 && (
        <div class="inv-groups" style={{ margin: "6px 0 12px" }}>
          {inv.groups.map((g) => (
            <span class="inv-chip" key={g.quantity}>
              {g.count} thùng × {soVN(g.quantity)}
            </span>
          ))}
        </div>
      )}

      <section class="card">
        <label class="card-label">Danh sách thùng ({all.length})</label>
        {all.length === 0 ? (
          <div class="muted small">Chưa có thùng nào.</div>
        ) : (
          <div class="inv-detail-list">
            {all.map((b) => {
              const rem = b.remaining ?? b.quantity;
              const used = b.allocated ?? 0;
              // Tap thùng → trang chi tiết thùng (phiếu nguồn + đơn phân bổ)
              return (
                <a
                  key={b.id}
                  class={b.disabled ? "inv-detail-row link box-off" : "inv-detail-row link"}
                  href={`#/thung/${b.id}`}
                >
                  <code class="inv-bc">{b.box_code}</code>
                  <span class="inv-q">
                    {soVN(rem)}
                    {used > 0 ? <span class="muted">/{soVN(b.quantity)}</span> : ""}
                  </span>
                  {b.note && <span class="inv-note muted small">📝 {b.note}</span>}
                  {b.disabled ? (
                    <span class="inv-status disabled" title={b.disabled_reason || undefined}>
                      Vô hiệu
                    </span>
                  ) : used > 0 ? (
                    <span class="inv-status alloc">đã xuất {soVN(used)}</span>
                  ) : (
                    <span class="inv-status in">Trong kho</span>
                  )}
                  <span class="inv-when muted small">{fmtWhen(b.created_at)}</span>
                </a>
              );
            })}
          </div>
        )}
      </section>

      <section class="card" ref={ordSecRef}>
        <label class="card-label">Đơn có sản phẩm này{ordStarted.current ? ` (${ordTotal})` : ""}</label>
        {!ordStarted.current || (ordLoading && ords.length === 0) ? (
          <div class="muted small">Đang tải…</div>
        ) : ords.length === 0 ? (
          <div class="muted small">Chưa có đơn nào chứa mã này.</div>
        ) : (
          <>
            <div class="inv-detail-list">
              {ords.map((o) => (
                <a key={o.thread_id} class="inv-detail-row link" href={`#/order/${o.thread_id}`}>
                  <code class="inv-bc">#{o.thread_id}</code>
                  <span class="prod-ord-text">{o.text || "(trống)"}</span>
                  {o.sl != null && <span class="inv-q">×{soVN(o.sl)}</span>}
                  {o.price != null && o.price > 0 && <span class="muted small">{money(o.price)}đ</span>}
                </a>
              ))}
            </div>
            {ordMore && (
              <button class="btn small block" style={{ marginTop: "8px" }} disabled={ordLoading} onClick={() => loadOrders(false)}>
                {ordLoading ? "⏳ Đang tải…" : `Xem thêm (${ordTotal - ords.length})`}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
