// Xuất kho cho đơn: mỗi mã SP trong hoá đơn → chọn thùng in_stock (mã + số cây)
// tổng đủ SL cần, xuất cho đơn này. Hiện thùng đã xuất + thu hồi. GET/POST
// /api/order/:id/allocations|allocate|release + /api/inventory/:code.
import { useEffect, useState } from "preact/hooks";
import {
  orderAllocations,
  inventoryDetail,
  allocateBoxes,
  releaseBoxes,
  soVN,
  type InvBox,
  type InvDetail,
} from "../api";

type Line = { sp: string; sl: number | string };

export function OrderStock({ threadId, invoice }: { threadId: string; invoice: Line[] }) {
  const [alloc, setAlloc] = useState<InvBox[]>([]);
  const [openCode, setOpenCode] = useState("");
  const [inv, setInv] = useState<InvDetail | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try {
      setAlloc(await orderAllocations(threadId));
    } catch {
      /* im lặng */
    }
  };
  useEffect(() => {
    load();
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

  const openPicker = async (code: string) => {
    if (openCode === code) {
      setOpenCode("");
      return;
    }
    setOpenCode(code);
    setPicked(new Set());
    setInv(null);
    setMsg("");
    try {
      setInv(await inventoryDetail(code));
    } catch {
      setInv(null);
    }
  };

  const toggle = (id: number) => {
    const s = new Set(picked);
    s.has(id) ? s.delete(id) : s.add(id);
    setPicked(s);
  };

  const pickedSum = inv ? inv.boxes.filter((b) => picked.has(b.id)).reduce((s, b) => s + b.quantity, 0) : 0;

  const doAllocate = async () => {
    if (!picked.size) return;
    setBusy(true);
    setMsg("");
    try {
      await allocateBoxes(threadId, [...picked]);
      setOpenCode("");
      setPicked(new Set());
      await load();
    } catch (e: any) {
      setMsg(e?.message || "Lỗi xuất kho");
    } finally {
      setBusy(false);
    }
  };

  const doRelease = async (id: number) => {
    setBusy(true);
    setMsg("");
    try {
      await releaseBoxes(threadId, [id]);
      await load();
    } catch (e: any) {
      setMsg(e?.message || "Lỗi thu hồi");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section class="card">
      <label class="card-label">📦 Xuất kho cho đơn</label>
      {products.map(({ code, need }) => {
        const mine = alloc.filter((b) => b.product_code === code);
        const got = mine.reduce((s, b) => s + b.quantity, 0);
        const enough = got >= need;
        return (
          <div class="stock-line" key={code}>
            <div class="stock-head">
              <b>{code}</b>
              <span class={enough ? "inv-pick-sum ok" : "inv-pick-sum"}>
                Đã xuất {soVN(got)}/{soVN(need)}
              </span>
              <button class="btn small" onClick={() => openPicker(code)}>
                {openCode === code ? "Đóng" : "Chọn thùng"}
              </button>
            </div>

            {mine.length > 0 && (
              <ul class="inv-box-list">
                {mine.map((b) => (
                  <li key={b.id}>
                    <code>{b.box_code}</code> · {soVN(b.quantity)}
                    <button class="link-btn" disabled={busy} onClick={() => doRelease(b.id)} title="Thu hồi">
                      {" "}
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {openCode === code && (
              <div class="stock-picker">
                {!inv || inv.boxes.length === 0 ? (
                  <div class="muted small">Kho hết thùng {code}.</div>
                ) : (
                  <>
                    <ul class="inv-box-list">
                      {inv.boxes.map((b) => (
                        <li key={b.id} class={picked.has(b.id) ? "picked" : ""} onClick={() => toggle(b.id)}>
                          <code>{b.box_code}</code> · {soVN(b.quantity)}
                        </li>
                      ))}
                    </ul>
                    <div class="inv-pick-bar">
                      <span
                        class={
                          pickedSum + got > need
                            ? "inv-pick-sum over"
                            : pickedSum + got >= need
                              ? "inv-pick-sum ok"
                              : "inv-pick-sum"
                        }
                      >
                        Chọn {soVN(pickedSum)} · còn thiếu {soVN(Math.max(need - got - pickedSum, 0))}
                      </span>
                      <button class="btn primary small" disabled={busy || !picked.size} onClick={doAllocate}>
                        Xuất {picked.size || ""} thùng
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
      {msg && <div class="muted small">{msg}</div>}
    </section>
  );
}
