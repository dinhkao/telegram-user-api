// Xuất kho cho đơn: mỗi mã SP trong hoá đơn → nút "Chọn thùng" mở popup chọn thùng
// (lấy 1 phần được, nhiều thùng — thùng KHÔNG tách, chỉ giảm phần còn lại). Hiện các
// phần đã xuất + thu hồi. Tap mã thùng → chi tiết thùng.
// CHỐT xuất kho: xuất đủ mọi mã → bấm Chốt → KHOÁ sửa/thu hồi VỚI TẤT CẢ (server
// cũng chặn); admin muốn sửa phải bấm Huỷ chốt. Nút bị khoá = mờ + toast lý do.
import { useEffect, useMemo, useState } from "preact/hooks";
import { orderAllocations, allocatePicks, releaseAllocations, stockConfirmOrder, currentUser, soVN, lockStockPick, unlockStockPick, stockPickStatus, type Allocation } from "../api";
import { StockPickerModal } from "./StockPickerModal";
import { confirmDialog, toast } from "../ui/feedback";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { BoxTileGrid, type BoxTileData } from "./BoxTileGrid";

type Line = { sp: string; sl: number | string };
type Confirmed = { at?: string; by?: string } | null;

function fmtAt(at?: string): string {
  if (!at || at.length < 16) return at || "";
  return `${at.slice(8, 10)}/${at.slice(5, 7)} ${at.slice(11, 16)}`;
}

export function OrderStock({ threadId, invoice, stockConfirmed, onCompleteSoanHang }: {
  threadId: string;
  invoice: Line[];
  stockConfirmed?: Confirmed;
  /** Sau khi chốt kho, mở đúng luồng hoàn thành task Soạn hàng hiện có. */
  onCompleteSoanHang?: () => void;
}) {
  const [allocs, setAllocs] = useState<Allocation[]>([]);
  const [stock, setStock] = useState<Record<string, number>>({});   // tồn hiện tại theo mã SP
  const [pickCode, setPickCode] = useState("");
  const pickSid = useMemo(() => Math.random().toString(36).slice(2) + Date.now().toString(36), []);
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
      const r = await orderAllocations(threadId);
      setAllocs(r.allocations);
      setStock(r.stock);
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
        const r = await lockStockPick(threadId, pickCode, pickSid);
        if (alive && r && r.mine === false) {
          toast(`Đang được ${r.holder} chọn thùng — chờ họ xong`, "info");
          setPickCode("");
          return;
        }
      } catch { /* im lặng — thử lại nhịp sau */ }
      if (alive) t = setTimeout(beat, 20000);
    };
    beat();
    return () => { alive = false; clearTimeout(t); unlockStockPick(threadId, pickCode, pickSid).catch(() => {}); };
  }, [pickCode, pickSid, threadId]);

  // gộp nhu cầu theo mã SP (SL cộng dồn)
  const needs = new Map<string, number>();
  for (const it of invoice || []) {
    const code = String(it.sp || "").trim().toUpperCase();
    if (!code) continue;
    needs.set(code, (needs.get(code) || 0) + (Number(it.sl) || 0));
  }
  const gotOf = (code: string) => allocs.filter((a) => a.product_code === code).reduce((s, a) => s + a.quantity, 0);
  // Gộp mã = mã trong hoá đơn ∪ mã ĐÃ XUẤT. Mã bị xoá/đổi khỏi HĐ mà còn phần đã
  // xuất vẫn phải hiện (need=0) để thu hồi — nếu không phần dư ẩn mất, trừ tồn oan.
  const allocCodes = [...new Set(allocs.map((a) => a.product_code))];
  const codes = [...new Set([...needs.keys(), ...allocCodes])];
  const products = codes.map((code) => {
    const need = needs.get(code) || 0;
    const got = gotOf(code);
    return { code, need, got, over: got - need > 1e-6, short: need - got > 1e-6 };
  });
  if (!products.length) return null;

  // Lệch = ĐÃ xuất (got>0) nhưng KHÔNG khớp SL hoá đơn → hầu hết do vừa sửa hoá đơn.
  //  • Dư (over): giảm SL / xoá SP sau khi đã xuất → phải thu hồi phần dư.
  //  • Thiếu-đã-xuất: tăng SL sau khi đã xuất → phải xuất thêm cho đủ.
  const overList = products.filter((p) => p.over);
  const shortAllocated = products.filter((p) => p.short && p.got > 1e-6);
  const mismatch = overList.length > 0 || shortAllocated.length > 0;
  // Chốt được: đã có xuất & MỌI mã KHỚP CHÍNH XÁC (không thiếu, không dư). Xuất dư
  // giờ CHẶN chốt (trước đây got≥need lọt qua → trừ tồn oan). Server cũng chặn.
  const canConfirm = allocs.length > 0 && products.every((p) => !p.over && !p.short);

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
    if (!canConfirm) return toast(
      overList.length > 0 ? "Có mã xuất DƯ — thu hồi phần dư về kho trước khi chốt" : "Xuất đủ mọi mã SP mới chốt được",
      "info");
    if (!(await confirmDialog("Chốt xuất kho cho đơn này? Sau khi chốt sẽ KHOÁ — không sửa hay thu hồi được nữa (chỉ admin)."))) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await stockConfirmOrder(threadId, true);
      setLocalSt(r.stock_confirmed || {});
      if (onCompleteSoanHang && await confirmDialog("Bạn có muốn hoàn thành task Soạn hàng luôn không?", {
        okLabel: "Có",
        cancelLabel: "Không",
      })) {
        onCompleteSoanHang();
      }
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

      {!confirmed && mismatch && (
        <div class="stock-mismatch">
          <span class="sm-ic">⚠️</span>
          <div>
            <b>Phân bổ kho không khớp hoá đơn</b> — có thể do hoá đơn vừa đổi số lượng.
            {overList.length > 0 && (
              <div class="small">• Xuất DƯ: {overList.map((p) => `${p.code} (dư ${soVN(p.got - p.need)})`).join(", ")} — <b>thu hồi phần dư</b> về kho.</div>
            )}
            {shortAllocated.length > 0 && (
              <div class="small">• Xuất THIẾU: {shortAllocated.map((p) => `${p.code} (thiếu ${soVN(p.need - p.got)})`).join(", ")} — <b>xuất thêm</b> cho đủ.</div>
            )}
          </div>
        </div>
      )}

      {products.map(({ code, need, got, over, short }) => {
        const mine = allocs.filter((a) => a.product_code === code);
        const inInvoice = need > 0;
        const enough = inInvoice && !over && !short;          // xuất đúng đủ
        const onhand = stock[code] ?? 0;                      // tồn hiện tại của kho
        const lowStock = short && onhand < (need - got);      // kho không đủ xuất nốt phần còn thiếu
        const pickBy = pickLocks[code];                       // ai đang chọn thùng mã này
        const heldByOther = !!pickBy && pickBy !== myName;    // NGƯỜI KHÁC đang chọn → khoá nút
        return (
          <div class="stock-line" key={code}>
            <div class="stock-head">
              <b>{code}</b>
              {!inInvoice && <span class="stock-orphan">không còn trong hoá đơn</span>}
              {inInvoice && short && (
              <span class={"stock-onhand" + (lowStock ? " low" : "")} title={lowStock ? "Tồn kho không đủ để xuất nốt phần còn thiếu" : "Tồn hiện tại trong kho"}>
                Tồn {soVN(onhand)}
              </span>
            )}
              <span class={over ? "inv-pick-sum over" : enough ? "inv-pick-sum ok" : "inv-pick-sum"}>
                Đã xuất {soVN(got)}{inInvoice ? `/${soVN(need)}` : ""}{over ? ` · dư ${soVN(got - need)}` : ""}
              </span>
              {inInvoice && !over && (
                <button class={"btn small" + (locked || heldByOther ? " faded" : "")}
                  onClick={() => (locked ? lockedToast()
                    : heldByOther ? toast(`Đang được ${pickBy} chọn thùng — chờ họ xong`, "info")
                    : setPickCode(code))}>
                  {heldByOther ? `${pickBy} đang chọn…` : "Chọn thùng"}
                </button>
              )}
            </div>

            {mine.length > 0 && (
              <BoxTileGrid
                size="dense"
                mode="allocated"
                productCodeMode="auto"
                className="sk-grid"
                boxes={mine.map((a): BoxTileData & { allocation: Allocation } => {
                  // Bấm → chi tiết thùng + cuộn/nháy đúng event xuất-kho này trong Lịch sử
                  const hts = a.allocated_at ? Math.floor(Date.parse(a.allocated_at) / 1000) : 0;
                  const bq = a.box_quantity || 0;
                  return {
                    id: a.allocation_id,
                    productCode: a.product_code,
                    boxCode: a.box_code,
                    quantity: bq,
                    remaining: a.quantity,
                    allocated: a.quantity,
                    placeName: a.place_name,
                    href: `#/thung/${a.box_id}${hts ? `?focus=hist:${hts}` : ""}`,
                    domId: `box-${a.box_id}`,
                    title: `${a.box_code} · lấy ${soVN(a.quantity)}${bq ? `/${soVN(bq)}` : ""}${a.place_name ? ` · ${a.place_name}` : ""}`,
                    allocation: a,
                  };
                })}
                getAction={(box) => ({
                  label: "Thu hồi",
                  content: <Icon name="close" size={12} />,
                  disabled: busy,
                  className: locked ? "faded" : "",
                  onClick: () => doRelease(box.allocation),
                })}
              />
            )}
          </div>
        );
      })}
      {msg && <div class="muted small">{msg}</div>}

      {!confirmed && (
        <button class={"btn primary block stock-confirm" + (canConfirm ? "" : " faded")} disabled={busy} onClick={doConfirm}
          title={!canConfirm ? (overList.length > 0 ? "Thu hồi phần dư về kho trước khi chốt" : "Xuất đủ mọi mã SP mới chốt được") : undefined}>
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
