// Xuất kho cho đơn: mỗi mã SP trong hoá đơn → nút "Chọn thùng" mở popup chọn thùng
// (lấy 1 phần được, nhiều thùng — thùng KHÔNG tách, chỉ giảm phần còn lại). Hiện các
// phần đã xuất + thu hồi. Tap mã thùng → chi tiết thùng.
// CHỐT xuất kho: xuất đủ mọi mã → bấm Chốt → KHOÁ sửa/thu hồi VỚI TẤT CẢ (server
// cũng chặn); admin muốn sửa phải bấm Huỷ chốt. Nút bị khoá = mờ + toast lý do.
import { useEffect, useState } from "preact/hooks";
import { orderAllocations, allocatePicks, releaseAllocations, stockConfirmOrder, currentUser, soVN, lockStockPick, unlockStockPick, stockPickStatus, type Allocation } from "../api";
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
  const locked = !!confirmed;   // chốt = khoá VỚI TẤT CẢ — admin phải Huỷ chốt mới sửa
  const myName = currentUser()?.display_name || currentUser()?.username || "";
  // {CODE: holder} mã đang có NGƯỜI KHÁC mở popup chọn thùng → làm mờ nút "Chọn thùng" mã đó
  const [pickLocks, setPickLocks] = useState<Record<string, string>>({});

  const load = async () => {
    try {
      setAllocs(await orderAllocations(threadId));
    } catch {
      /* im lặng */
    }
  };
  useEffect(() => {
    load();
    stockPickStatus(threadId).then(setPickLocks).catch(() => {});   // ai đang chọn thùng lúc mở
  }, [threadId]);

  // Realtime: xuất/thu hồi thùng cho đơn này (từ máy khác) hoặc kho đổi → tải lại phần đã xuất.
  // stock_pick_lock = có người mở/đóng popup chọn thùng mã nào đó → mờ/bỏ mờ nút mã đó.
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "stock_pick_lock" && e.thread_id === String(threadId)) {
        setPickLocks((m) => {
          const n = { ...m };
          if (e.holder) n[e.code] = e.holder; else delete n[e.code];
          return n;
        });
        return;
      }
      const rel = e.type === "resync" || e.type === "inventory_changed" || e.type === "box_changed" ||
        (e.type === "order_changed" && e.thread_id === String(threadId));
      if (rel) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  // Đang mở popup chọn thùng cho mã nào → GIỮ khoá mã đó (heartbeat 20s), nhả khi đóng.
  // Nếu người khác giành trước (mine=false) → đóng popup + báo.
  useEffect(() => {
    if (!pickCode) return;
    let alive = true;
    let t: any;
    const beat = async () => {
      try {
        const r = await lockStockPick(threadId, pickCode);
        if (alive && r && r.mine === false) {
          toast(`Đang được ${r.holder} chọn thùng — chờ họ xong`, "info");
          setPickCode("");
          return;
        }
      } catch { /* im lặng — thử lại nhịp sau */ }
      if (alive) t = setTimeout(beat, 20000);
    };
    beat();
    return () => { alive = false; clearTimeout(t); unlockStockPick(threadId, pickCode).catch(() => {}); };
  }, [pickCode, threadId]);

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

  const lockedToast = () => toast(isAdmin ? "Đã chốt xuất kho — bấm Huỷ chốt để sửa" : "Đã chốt xuất kho — chỉ admin mở khoá được", "info");

  const doRelease = async (a: Allocation) => {
    if (locked) return lockedToast();
    const place = a.place_name || "kho Chưa xếp vị trí";
    const num = (a.box_code || "").split("-").pop() || a.box_code;
    // chip thùng + vị trí = LINK (bấm để kiểm tra trước; sẽ đóng hộp rồi điều hướng)
    const content = (
      <span>
        Thu hồi thùng{" "}
        <a class="rl-chip" href={`#/thung/${a.box_id}`}>
          <span class="rl-cn">{num}</span><span class="rl-cq">{soVN(a.quantity)}</span>
        </a>{" "}
        sẽ được trả về{" "}
        {a.place_id
          ? <a class="rl-place" href={`#/vi-tri/${a.place_id}`}>{place}</a>
          : <b>{place}</b>}.
        <div class="muted small" style={{ marginTop: "8px" }}>⚠️ Hãy đảm bảo thùng này CHƯA được giao cho khách.</div>
      </span>
    );
    if (!(await confirmDialog("", { danger: true, okLabel: "Thu hồi", content }))) return;
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
        const pickBy = pickLocks[code];                       // ai đang chọn thùng mã này
        const heldByOther = !!pickBy && pickBy !== myName;    // NGƯỜI KHÁC đang chọn → khoá nút
        return (
          <div class="stock-line" key={code}>
            <div class="stock-head">
              <b>{code}</b>
              <span class={enough ? "inv-pick-sum ok" : "inv-pick-sum"}>
                Đã xuất {soVN(got)}/{soVN(need)}
              </span>
              <button class={"btn small" + (locked || heldByOther ? " faded" : "")}
                onClick={() => (locked ? lockedToast()
                  : heldByOther ? toast(`Đang được ${pickBy} chọn thùng — chờ họ xong`, "info")
                  : setPickCode(code))}>
                {heldByOther ? `${pickBy} đang chọn…` : "Chọn thùng"}
              </button>
            </div>

            {mine.length > 0 && (
              <div class="box-grid lbl-grid dense no-code sk-grid">
                {mine.map((a) => {
                  const num = (a.box_code || "").split("-").pop() || a.box_code;
                  // Bấm → chi tiết thùng + cuộn/nháy đúng event xuất-kho này trong Lịch sử
                  const hts = a.allocated_at ? Math.floor(Date.parse(a.allocated_at) / 1000) : 0;
                  const bq = a.box_quantity || 0;
                  const fill = bq > 0 ? Math.max(0, Math.min(100, (a.quantity / bq) * 100)) : 100;
                  return (
                    // Đơn CHƯA chốt xuất kho → ô NÂU (tạm chiếm chỗ); chốt rồi → XANH (đã cố định)
                    <a class={"box-lbl " + (confirmed ? "in" : "resv")} id={`box-${a.box_id}`} key={a.allocation_id}
                      href={`#/thung/${a.box_id}${hts ? `?focus=hist:${hts}` : ""}`} style={{ "--fill": `${fill}%` } as any}
                      title={`${a.box_code} · lấy ${soVN(a.quantity)}${bq ? `/${soVN(bq)}` : ""}${a.place_name ? ` · ${a.place_name}` : ""}`}>
                      <button class={"bl-x" + (locked ? " faded" : "")} disabled={busy} title="Thu hồi"
                        onClick={(e: any) => { e.preventDefault(); e.stopPropagation(); doRelease(a); }}>
                        <Icon name="close" size={12} />
                      </button>
                      <span class="bl-q">{soVN(a.quantity)}{bq ? <span class="bl-q-tot">/{soVN(bq)}</span> : ""}</span>
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
