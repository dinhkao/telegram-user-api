// Chi tiết 1 phiếu sản xuất — GET /api/production/:id. Sửa SP / mục tiêu SX,
// nhập số lượng (ProductionNumbers), báo cáo theo thợ (ProductionReport), xoá.
// Realtime: production_changed đúng thread / resync → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  getProduction,
  productionCatalog,
  setProductionProduct,
  setProductionTarget,
  deleteProduction,
  soVN,
  prodCreated,
  type ProdSlip,
  type ProdCatalogItem,
} from "../api";
import { onRealtime } from "../realtime";
import { ProductionNumbers } from "../detail/ProductionNumbers";
import { ProductionReport } from "../detail/ProductionReport";

export function ProductionDetail({ threadId }: { threadId: string }) {
  const [slip, setSlip] = useState<ProdSlip | null>(null);
  const [catalog, setCatalog] = useState<ProdCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [targetInput, setTargetInput] = useState("");
  const reloadTimer = useRef<any>(null);

  const reload = async () => {
    try {
      const s = await getProduction(threadId);
      setSlip(s);
      if (s?.sx_target != null) setTargetInput(String(s.sx_target));
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải phiếu");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    reload();
    productionCatalog().then(setCatalog).catch(() => {});
  }, [threadId]);

  // Realtime: đổi đúng phiếu này → tải lại (debounce nhẹ)
  useEffect(() => {
    return onRealtime((e) => {
      const hit =
        e.type === "resync" ||
        ((e.type === "production_changed") && e.thread_id === String(threadId));
      if (!hit) return;
      clearTimeout(reloadTimer.current);
      reloadTimer.current = setTimeout(reload, 250);
    });
  }, [threadId]);

  const changeProduct = async (code: string) => {
    if (!code) return;
    setErr("");
    try {
      await setProductionProduct(threadId, code);
      reload();
    } catch (e: any) {
      setErr(e?.message || "Lỗi cập nhật SP");
    }
  };

  const saveTarget = async () => {
    const n = parseInt(targetInput, 10);
    if (!isFinite(n)) {
      setErr("Mục tiêu SX không hợp lệ");
      return;
    }
    setErr("");
    try {
      await setProductionTarget(threadId, n);
      reload();
    } catch (e: any) {
      setErr(e?.message || "Lỗi cập nhật mục tiêu");
    }
  };

  const doDelete = async () => {
    if (!confirm("Xoá phiếu sản xuất này?")) return;
    try {
      await deleteProduction(threadId);
      window.location.hash = "#/san_xuat";
    } catch (e: any) {
      setErr(e?.message || "Lỗi xoá phiếu");
    }
  };

  if (loading) return <div class="muted">Đang tải…</div>;
  if (!slip) return <div class="muted">Không tìm thấy phiếu. <a href="#/san_xuat">← Danh sách</a></div>;

  const total = slip.total || 0;
  const target = slip.sx_target ?? null;
  const pct = target ? Math.min(Math.round((total / target) * 100), 100) : null;
  const done = target != null && total >= target;

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <a class="back" href="#/san_xuat">←</a>
        <div>
          <div class="prod-sp big">{slip.sp_name || "Chưa có SP"}</div>
          <div class="prod-date muted">📅 Tạo: {prodCreated(slip)}</div>
        </div>
      </div>

      {err && <div class="error-banner">{err}</div>}

      <div class="prod-summary">
        <span class={done ? "prod-total done" : "prod-total"}>✅ Nhận: {soVN(total)}</span>
        <span class="prod-target">🎯 SX: {target != null ? soVN(target) : "—"}</span>
        {pct != null && <span class="prod-pct">{pct}%</span>}
      </div>
      {pct != null && (
        <div class="prod-bar">
          <div class={done ? "prod-bar-fill done" : "prod-bar-fill"} style={{ width: `${pct}%` }} />
        </div>
      )}

      <section class="card">
        <label class="card-label">Sản phẩm</label>
        <select value={slip.sp_name || ""} onChange={(e) => changeProduct((e.target as HTMLSelectElement).value)}>
          <option value="">— Chọn SP —</option>
          {catalog.map((c) => (
            <option value={c.code}>
              {c.code}
              {c.mam != null ? ` (mâm ${c.mam})` : ""}
            </option>
          ))}
        </select>
        {slip.sp_mam != null && <div class="muted small">🌿 Số cây 1 mâm: {slip.sp_mam}</div>}
      </section>

      <section class="card">
        <label class="card-label">Mục tiêu SX</label>
        <div class="row">
          <input
            type="number"
            inputMode="numeric"
            value={targetInput}
            onInput={(e) => setTargetInput((e.target as HTMLInputElement).value)}
            placeholder="Số lượng mục tiêu"
          />
          <button class="btn" onClick={saveTarget}>Lưu</button>
        </div>
      </section>

      <ProductionNumbers threadId={threadId} slip={slip} onChanged={reload} />

      <ProductionReport threadId={threadId} slip={slip} />

      <button class="btn danger block" onClick={doDelete}>🗑 Xoá phiếu</button>
    </div>
  );
}
