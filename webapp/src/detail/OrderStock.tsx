// Xuất kho cho đơn: mỗi mã SP trong hoá đơn → nút "Chọn thùng" mở popup chọn thùng
// (lấy 1 phần được, nhiều thùng — thùng KHÔNG tách, chỉ giảm phần còn lại). Hiện các
// phần đã xuất + thu hồi. Tap mã thùng → chi tiết thùng.
// CHỐT xuất kho: xuất đủ mọi mã → bấm Chốt → KHOÁ sửa/thu hồi (server cũng chặn);
// chỉ admin còn sửa được + huỷ chốt. Nút bị khoá = mờ + toast lý do.
import { useEffect, useState } from "preact/hooks";
import { orderAllocations, allocatePicks, releaseAllocations, stockConfirmOrder, currentUser, soVN, type Allocation } from "../api";
import { StockPickerModal } from "./StockPickerModal";
import { confirmDialog, toast } from "../ui/feedback";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: number | string };
type Confirmed = { at?: string; by?: string } | null;

function fmtAt(at?: string): string {
  if (!at || at.length < 16) return at || "";
  return `${at.slice(8, 10)}/${at.slice(5, 7)} ${at.slice(11, 16)}`;
}

export function OrderStock({ threadId, invoice, stockConfirmed }: {
  threadId: string;
  invoice: Line[];
  stockConfirmed?: Confirmed;
}) {
  const [allocs, setAllocs] = useState<Allocation[]>([]);
  const [pickCode, setPickCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  // Ghi đè cục bộ sau khi chốt/huỷ (prop cha chỉ đổi khi realtime tải lại đơn)
  const [localSt, setLocalSt] = useState<Confirmed | "cleared" | null>(null);
  useEffect(() => { setLocalSt(null); }, [stockConfirmed]);
  const confirmed: Confirmed = localSt === "cleared" ? null : (localSt as Confirmed) || stockConfirmed || null;
  const isAdmin = currentUser()?.role === "admin";
  const locked = !!confirmed && !isAdmin;

  const load = async () => {
    try {
      setAllocs(await orderAllocations(threadId));
    } catch {
      /* im lặng */
    }
  };
  useEffect(() => {
    load();
  }, [threadId]);

  // Realtime: xuất/thu hồi thùng cho đơn này (từ máy khác) hoặc kho đổi → tải lại phần đã xuất
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const rel = e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed" ||
        (e.type === "order_changed" && e.thread_id === String(threadId));
      if (rel) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  // gộp nhu cầu theo mã SP (SL cộng dồn)
  const needs = new Map<string, number>();
  for (const it of invoice || []) {
    const code = String(it.sp || "").trim().toUpperCase();
    if (!code) continue;
    needs.set(code, (needs.get(code) || 0) + (Number(it.sl) || 0));
  }
  const products = [...needs.entries()].map(([code, need]) => ({ code, need }));
  if (!products.length) return null;

  const gotOf = (code: string) => allocs.filter((a) => a.product_code === code).reduce((s, a) => s + a.quantity, 0);
  const allEnough = allocs.length > 0 && products.every((p) => gotOf(p.code) + 1e-6 >= p.need);

  const lockedToast = () => toast("Đã chốt xuất kho — chỉ admin sửa/thu hồi được", "info");

  const doRelease = async (a: Allocation) => {
    if (locked) return lockedToast();
    if (!(await confirmDialog(`Thu hồi ${soVN(a.quantity)} từ thùng ${a.box_code} khỏi đơn về kho?`, { danger: true }))) return;
    setBusy(true);
    setMsg("");
    try {
      await releaseAllocations(threadId, [a.allocation_id]);
      await load();
    } catch (e: any) {
      setMsg(e?.message || "Lỗi thu hồi");
    } finally {
      setBusy(false);
    }
  };

  const doConfirm = async () => {
    if (!allEnough) return toast("Xuất đủ mọi mã SP mới chốt được", "info");
    if (!(await confirmDialog("Chốt xuất kho cho đơn này? Sau khi chốt sẽ KHOÁ — không sửa hay thu hồi được nữa (chỉ admin)."))) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await stockConfirmOrder(threadId, true);
      setLocalSt(r.stock_confirmed || {});
    } catch (e: any) {
      setMsg(e?.message || "Lỗi chốt xuất kho");
    } finally {
      setBusy(false);
    }
  };

  const doUnconfirm = async () => {
    if (!(await confirmDialog("Huỷ chốt xuất kho (admin)? Đơn sẽ sửa/thu hồi lại được.", { danger: true }))) return;
    setBusy(true);
    setMsg("");
    try {
      await stockConfirmOrder(threadId, false);
      setLocalSt("cleared");
    } catch (e: any) {
      setMsg(e?.message || "Lỗi huỷ chốt");
    } finally {
      setBusy(false);
    }
  };

  const current = pickCode ? products.find((p) => p.code === pickCode) : null;
  const pickGot = pickCode ? gotOf(pickCode) : 0;

  return (
    <section class="card">
      <label class="card-label"><Icon name="box" size={16} /> Xuất kho cho đơn</label>

      {confirmed && (
        <div class="stock-locked">
          <Icon name="lock" size={14} /> Đã chốt xuất kho{confirmed.by ? ` — ${confirmed.by}` : ""}{confirmed.at ? ` · ${fmtAt(confirmed.at)}` : ""}
          {isAdmin && (
            <button class="btn small stock-unlock" disabled={busy} onClick={doUnconfirm}>Huỷ chốt</button>
          )}
        </div>
      )}

      {products.map(({ code, need }) => {
        const mine = allocs.filter((a) => a.product_code === code);
        const got = mine.reduce((s, a) => s + a.quantity, 0);
        const enough = got >= need;
        return (
          <div class="stock-line" key={code}>
            <div class="stock-head">
              <b>{code}</b>
              <span class={enough ? "inv-pick-sum ok" : "inv-pick-sum"}>
                Đã xuất {soVN(got)}/{soVN(need)}
              </span>
              <button class={"btn small" + (locked ? " faded" : "")}
                onClick={() => (locked ? lockedToast() : setPickCode(code))}>
                Chọn thùng
              </button>
            </div>

            {mine.length > 0 && (
              <div class="box-grid lbl-grid">
                {mine.map((a) => {
                  const num = (a.box_code || "").split("-").pop() || a.box_code;
                  return (
                    <a key={a.allocation_id} id={`box-${a.box_id}`} class="box-lbl in" href={`#/thung/${a.box_id}`}
                      title={`${a.box_code} · lấy ${soVN(a.quantity)}${a.box_quantity ? `/${soVN(a.box_quantity)}` : ""}`}>
                      <button class={"bl-x" + (locked ? " faded" : "")} disabled={busy} title="Thu hồi"
                        onClick={(e: any) => { e.preventDefault(); e.stopPropagation(); doRelease(a); }}>
                        <Icon name="close" size={12} />
                      </button>
                      <span class="bl-code">{code}</span>
                      <span class="bl-q">{soVN(a.quantity)}</span>
                      <span class="bl-num">{num}</span>
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      {msg && <div class="muted small">{msg}</div>}

      {!confirmed && (
        <button class={"btn primary block stock-confirm" + (allEnough ? "" : " faded")} disabled={busy} onClick={doConfirm}
          title={!allEnough ? "Xuất đủ mọi mã SP mới chốt được" : undefined}>
          <Icon name="check" size={16} /> Chốt xuất kho
        </button>
      )}

      {current && (
        <StockPickerModal
          productCode={current.code}
          need={current.need}
          got={pickGot}
          onClose={() => setPickCode("")}
          onPick={async (picks) => {
            await allocatePicks(threadId, picks);
            await load();
          }}
        />
      )}
    </section>
  );
}
