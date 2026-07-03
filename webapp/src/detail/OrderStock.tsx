// Xuất kho cho đơn: mỗi mã SP trong hoá đơn → nút "Chọn thùng" mở popup chọn thùng
// (có thể lấy 1 phần, nhiều thùng). Hiện thùng đã xuất + thu hồi. Tap mã thùng →
// chi tiết thùng. GET/POST /api/order/:id/allocations|allocate|release.
import { useEffect, useState } from "preact/hooks";
import { orderAllocations, allocatePicks, releaseBoxes, soVN, type InvBox } from "../api";
import { StockPickerModal } from "./StockPickerModal";

type Line = { sp: string; sl: number | string };

export function OrderStock({ threadId, invoice }: { threadId: string; invoice: Line[] }) {
  const [alloc, setAlloc] = useState<InvBox[]>([]);
  const [pickCode, setPickCode] = useState("");
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

  const doRelease = async (b: InvBox) => {
    if (!confirm(`Thu hồi thùng ${b.box_code} (${soVN(b.quantity)}) khỏi đơn về kho?`)) return;
    setBusy(true);
    setMsg("");
    try {
      await releaseBoxes(threadId, [b.id]);
      await load();
    } catch (e: any) {
      setMsg(e?.message || "Lỗi thu hồi");
    } finally {
      setBusy(false);
    }
  };

  const current = pickCode ? products.find((p) => p.code === pickCode) : null;
  const pickGot = pickCode
    ? alloc.filter((b) => b.product_code === pickCode).reduce((s, b) => s + b.quantity, 0)
    : 0;

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
              <button class="btn small" onClick={() => setPickCode(code)}>
                Chọn thùng
              </button>
            </div>

            {mine.length > 0 && (
              <ul class="inv-box-list">
                {mine.map((b) => (
                  <li key={b.id} id={`box-${b.id}`}>
                    <a class="box-link" href={`#/thung/${b.id}`} title="Chi tiết thùng">
                      <code>{b.box_code}</code>
                    </a>{" "}
                    · {soVN(b.quantity)}
                    <button class="link-btn" disabled={busy} onClick={() => doRelease(b)} title="Thu hồi">
                      {" "}
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {msg && <div class="muted small">{msg}</div>}

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
