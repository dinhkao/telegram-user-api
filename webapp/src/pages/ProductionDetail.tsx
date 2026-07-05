// Chi tiết 1 phiếu sản xuất — GET /api/production/:id. Sửa SP, ghi chú,
// nhập thùng (ProductionBoxes), báo cáo theo thợ (ProductionReport), xoá.
// Realtime: production_changed đúng thread / resync → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getProduction,
  productionCatalog,
  setProductionProduct,
  setProductionNote,
  deleteProduction,
  soVN,
  prodCreated,
  type ProdSlip,
  type ProdCatalogItem,
} from "../api";
import { onRealtime } from "../realtime";
import { ProductionBoxes } from "../detail/ProductionBoxes";
import { ProductionReport } from "../detail/ProductionReport";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { ProductPicker } from "../detail/ProductPicker";
import { confirmDialog } from "../ui/feedback";
import { Loading } from "../ui/states";

export function ProductionDetail({ threadId, focus }: { threadId: string; focus?: string }) {
  const [slip, setSlip] = useState<ProdSlip | null>(null);
  const [catalog, setCatalog] = useState<ProdCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [noteInput, setNoteInput] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);
  const reloadTimer = useRef<any>(null);

  const reload = async () => {
    try {
      const s = await getProduction(threadId);
      setSlip(s);
      setNoteInput(s?.ghi_chu || "");
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
        // nhập/sửa/vô hiệu/xuất thùng ở nơi khác đổi tổng SP + list thùng của phiếu này
        e.type === "inventory_changed" || e.type === "box_changed" ||
        ((e.type === "production_changed") && e.thread_id === String(threadId));
      if (!hit) return;
      clearTimeout(reloadTimer.current);
      reloadTimer.current = setTimeout(reload, 250);
    });
  }, [threadId]);

  // Deep-link từ chi tiết thùng (?focus=box:id): đợi thùng render rồi cuộn tới + nháy
  useEffect(() => {
    if (!focus) return;
    let tries = 0;
    let flashT: any;
    const iv = setInterval(() => {
      const el = document.getElementById(focus);
      if (el) {
        clearInterval(iv);
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("flash-target");
        flashT = setTimeout(() => el.classList.remove("flash-target"), 2400);
        history.replaceState(null, "", `#/san_xuat/${threadId}`);
      } else if (++tries > 50) {
        clearInterval(iv);
      }
    }, 100);
    return () => {
      clearInterval(iv);
      clearTimeout(flashT);
    };
  }, [focus, threadId]);

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

  const saveNote = async () => {
    setErr("");
    try {
      await setProductionNote(threadId, noteInput.trim());
      setNoteSaved(true);
      setTimeout(() => setNoteSaved(false), 1500);
      reload();
    } catch (e: any) {
      setErr(e?.message || "Lỗi lưu ghi chú");
    }
  };

  const doDelete = async () => {
    if (!(await confirmDialog("Xoá phiếu sản xuất này?", { danger: true }))) return;
    try {
      await deleteProduction(threadId);
      window.location.hash = "#/san_xuat";
    } catch (e: any) {
      setErr(e?.message || "Lỗi xoá phiếu");
    }
  };

  if (loading) return <Loading />;
  if (!slip) return <div class="muted">Không tìm thấy phiếu. <a href="#/san_xuat">← Danh sách</a></div>;

  const boxed = slip.total || 0;                          // tổng nhập thùng
  const reported = Number(slip.bang?.grand_total || 0);   // tổng báo cáo theo thợ
  const diff = Math.round((boxed - reported) * 100) / 100;
  const pctOff = reported > 0 ? Math.abs(diff) / reported * 100 : (diff === 0 ? 0 : 100);
  const match = pctOff <= 0.5;                             // cho phép lệch ≤ 0.5%
  const hasReport = reported > 0 || (slip.bang?.rows?.length || 0) > 0;

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/san_xuat" />
        <div>
          <div class="prod-sp big">{slip.sp_name || "Chưa có SP"}</div>
          <div class="prod-date muted">📅 Tạo: {prodCreated(slip)}</div>
        </div>
      </div>

      {err && <div class="error-banner">{err}</div>}

      {/* So sánh: tổng nhập thùng vs tổng báo cáo theo thợ (khớp/lệch) */}
      <div class={"prod-compare" + (!hasReport ? " none" : match ? " ok" : " warn")}>
        <div class="pc-cell">
          <div class="pc-lb">📦 Nhập thùng</div>
          <div class="pc-val">{soVN(boxed)}</div>
        </div>
        <div class="pc-sep">vs</div>
        <div class="pc-cell">
          <div class="pc-lb">📋 Báo cáo thợ</div>
          <div class="pc-val">{soVN(reported)}</div>
        </div>
        <div class="pc-verdict">
          {!hasReport ? "— chưa báo cáo" : match ? "✅ Khớp" : `⚠️ Lệch ${soVN(Math.abs(diff))} (${pctOff.toFixed(1)}%)`}
        </div>
      </div>

      <section class="card">
        <label class="card-label">Sản phẩm</label>
        <ProductPicker catalog={catalog} value={slip.sp_name || ""} onPick={changeProduct} placeholder="🔍 Tìm mã SP" />
        {slip.sp_mam != null && <div class="muted small">🌿 Số cây 1 mâm: {slip.sp_mam}</div>}
      </section>

      <section class="card">
        <label class="card-label">Ghi chú {noteSaved && <span class="muted small">✓ đã lưu</span>}</label>
        <textarea
          rows={2}
          value={noteInput}
          onInput={(e) => setNoteInput((e.target as HTMLTextAreaElement).value)}
          onBlur={saveNote}
          placeholder="Ghi chú cho phiếu (tự lưu khi rời ô)…"
        />
      </section>

      <ProductionBoxes threadId={threadId} slip={slip} onChanged={reload} />

      <ProductionReport threadId={threadId} slip={slip} />

      <Images base={`/api/media/production/${threadId}`} />
      <Comments base={`/api/media/production/${threadId}`} />
      <History base={`/api/media/production/${threadId}`} />

      <button class="btn danger block" onClick={doDelete}>🗑 Xoá phiếu</button>
    </div>
  );
}
