// Xuất kho cho đơn: mỗi mã SP trong hoá đơn → nút "Chọn thùng" mở popup chọn thùng
// (lấy 1 phần được, nhiều thùng — thùng KHÔNG tách, chỉ giảm phần còn lại). Hiện các
// phần đã xuất + thu hồi. Tap mã thùng → chi tiết thùng.
import { useEffect, useState } from "preact/hooks";
import { orderAllocations, allocatePicks, releaseAllocations, soVN, type Allocation } from "../api";
import { StockPickerModal } from "./StockPickerModal";

type Line = { sp: string; sl: number | string };

export function OrderStock({ threadId, invoice }: { threadId: string; invoice: Line[] }) {
  const [allocs, setAllocs] = useState<Allocation[]>([]);
  const [pickCode, setPickCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

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

  // gộp nhu cầu theo mã SP (SL cộng dồn)
  const needs = new Map<string, number>();
  for (const it of invoice || []) {
    const code = String(it.sp || "").trim().toUpperCase();
    if (!code) continue;
    needs.set(code, (needs.get(code) || 0) + (Number(it.sl) || 0));
  }
  const products = [...needs.entries()].map(([code, need]) => ({ code, need }));
  if (!products.length) return null;

  const doRelease = async (a: Allocation) => {
    if (!confirm(`Thu hồi ${soVN(a.quantity)} từ thùng ${a.box_code} khỏi đơn về kho?`)) return;
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

  const current = pickCode ? products.find((p) => p.code === pickCode) : null;
  const pickGot = pickCode
    ? allocs.filter((a) => a.product_code === pickCode).reduce((s, a) => s + a.quantity, 0)
    : 0;

  return (
    <section class="card">
      <label class="card-label">📦 Xuất kho cho đơn</label>
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
              <button class="btn small" onClick={() => setPickCode(code)}>
                Chọn thùng
              </button>
            </div>

            {mine.length > 0 && (
              <ul class="inv-box-list">
                {mine.map((a) => (
                  <li key={a.allocation_id} id={`box-${a.box_id}`}>
                    <a class="box-link" href={`#/thung/${a.box_id}`} title="Chi tiết thùng">
                      <code>{a.box_code}</code>
                    </a>{" "}
                    · lấy {soVN(a.quantity)}
                    {a.box_quantity ? <span class="muted small"> /{soVN(a.box_quantity)}</span> : null}
                    <button class="link-btn" disabled={busy} onClick={() => doRelease(a)} title="Thu hồi">
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
