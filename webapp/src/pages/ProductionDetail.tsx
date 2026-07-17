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
  setProductionKind,
  deleteProduction,
  lockProductionSlip,
  unlockProductionSlip,
  currentUser,
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
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";
import { fastScrollToEl } from "../scroll";

// "còn X giờ Y phút" tới lúc tự khoá (từ ISO lock_at); null nếu đã qua/không có
function untilLock(iso?: string | null): string | null {
  if (!iso) return null;
  const ms = Date.parse(iso) - Date.now();
  if (!(ms > 0)) return null;
  const h = Math.floor(ms / 3600e3), m = Math.floor((ms % 3600e3) / 60000);
  return h > 0 ? `${h} giờ ${m} phút` : `${m} phút`;
}

export function ProductionDetail({ threadId, focus }: { threadId: string; focus?: string }) {
  const [slip, setSlip] = useState<ProdSlip | null>(null);
  const [catalog, setCatalog] = useState<ProdCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [noteInput, setNoteInput] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);
  const [, setTick] = useState(0);   // nhịp phút để đếm ngược tự khoá cập nhật
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 60000); return () => clearInterval(t); }, []);
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
        fastScrollToEl(el, "center");
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

  const locked = !!slip?.locked;
  const lockedToast = () => toast("Phiếu đã khoá — chỉ trao đổi được. Nhờ admin mở khoá.", "info");
  const toggleLock = async () => {
    if (!slip) return;
    try {
      if (locked) await unlockProductionSlip(threadId); else await lockProductionSlip(threadId);
      toast(locked ? "✅ Đã mở khoá phiếu" : "🔒 Đã khoá phiếu", "ok");
      reload();
    } catch (e: any) { toast(e?.message || "Lỗi khoá/mở", "err"); }
  };

  const changeProduct = async (code: string) => {
    if (!code) return;
    if (locked) return lockedToast();
    setErr("");
    try {
      await setProductionProduct(threadId, code);
      reload();
    } catch (e: any) {
      setErr(e?.message || "Lỗi cập nhật SP");
    }
  };

  const saveNote = async () => {
    if (locked) { setNoteInput(slip?.ghi_chu || ""); return lockedToast(); }
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

  const changeKind = async (k: "san_xuat" | "dong_goi") => {
    if (!slip || (slip.kind || "san_xuat") === k) return;
    if (locked) return lockedToast();
    // Đã nhập thùng → loại bị KHOÁ (loại quyết định logic trừ nguyên liệu lúc tạo thùng)
    if ((slip.box_count || 0) > 0) {
      toast(`Phiếu đã nhập ${slip.box_count} thùng — không đổi loại được nữa`, "info");
      return;
    }
    setSlip((s) => (s ? { ...s, kind: k } : s));   // optimistic
    try { await setProductionKind(threadId, k); }
    catch (e: any) { setErr(e?.message || "Lỗi đổi loại phiếu"); reload(); }
  };

  const doDelete = async () => {
    // Còn thùng tạo từ phiếu → nút mờ, bấm chỉ hiện toast (server cũng chặn 400)
    if ((slip?.box_count || 0) > 0) {
      toast(`Phiếu đã tạo ${slip!.box_count} thùng — xoá các thùng đó trước`, "info");
      return;
    }
    if (!(await confirmDialog("Xoá phiếu sản xuất này?", { danger: true }))) return;
    try {
      await deleteProduction(threadId);
      window.location.hash = "#/san_xuat";
    } catch (e: any) {
      setErr(e?.message || "Lỗi xoá phiếu");
    }
  };

  if (loading) return <Loading />;
  if (!slip) {
    // Lỗi tải (mạng/server) → ErrorState thử lại; tải ok mà không có → không tìm thấy
    if (err) return <ErrorState msg={err} onRetry={() => { setErr(""); setLoading(true); reload(); }} />;
    return <EmptyState icon="🏭">Không tìm thấy phiếu. <a href="#/san_xuat">← Danh sách</a></EmptyState>;
  }

  const boxed = slip.boxed_total ?? 0;                    // tổng nhập thùng (chỉ thùng từ UI, bỏ nhập tay)
  const reported = Number(slip.bang?.grand_total || 0);   // tổng báo cáo theo thợ
  const diff = Math.round((boxed - reported) * 100) / 100;
  const pctOff = reported > 0 ? Math.abs(diff) / reported * 100 : (diff === 0 ? 0 : 100);
  const match = pctOff <= 1;                               // cho phép lệch ≤ 1%
  const hasReport = reported > 0 || (slip.bang?.rows?.length || 0) > 0;
  const isSX = (slip.kind || "san_xuat") === "san_xuat";   // sản xuất → có bảng báo cáo thợ

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/san_xuat" />
        <div>
          <div class="prod-sp big">{slip.sp_name || "Chưa có SP"}</div>
          <div class="prod-date muted"><Icon name="calendar" size={14} /> Tạo: {prodCreated(slip)}</div>
        </div>
      </div>

      {err && <div class="error-banner">{err}</div>}

      {locked && (
        <div class="prod-lock-banner">
          <Icon name="lock" size={15} /> Phiếu đã khoá{slip.lock_override === "locked" ? " (admin khoá)" : " (quá 24h)"} — chỉ trao đổi (bình luận/ảnh) được.
          {currentUser()?.role === "admin" && <span class="muted small"> Admin có thể mở khoá bên dưới.</span>}
        </div>
      )}

      {!locked && untilLock(slip.lock_at) && (
        <div class="prod-lock-hint">
          <Icon name="clock" size={14} /> Tự khoá sau <b>{untilLock(slip.lock_at)}</b> nữa — sửa được tới lúc đó.
        </div>
      )}

      {/* Loại phiếu: Sản xuất (có bảng báo cáo thợ) ↔ Đóng gói (không).
          Đã nhập ≥1 thùng → KHOÁ (mờ nút kia; bấm hiện toast lý do). */}
      <div class="pk-seg">
        <button class={"pk-opt" + (isSX ? " on" : (locked || (slip.box_count || 0) > 0) ? " faded" : "")} onClick={() => changeKind("san_xuat")}><Icon name="factory" size={15} /> Sản xuất</button>
        <button class={"pk-opt" + (!isSX ? " on" : (locked || (slip.box_count || 0) > 0) ? " faded" : "")} onClick={() => changeKind("dong_goi")}><Icon name="box" size={15} /> Đóng gói</button>
      </div>
      {(slip.box_count || 0) > 0 && <div class="muted small pk-lock-hint"><Icon name="lock" size={12} /> Đã nhập thùng — loại phiếu bị khoá</div>}

      {/* So sánh: tổng nhập thùng vs tổng báo cáo theo thợ (khớp/lệch) — chỉ phiếu SX */}
      {isSX && <div class={"prod-compare" + (!hasReport ? " none" : match ? " ok" : " warn")}>
        <div class="pc-cell">
          <div class="pc-lb"><Icon name="box" size={14} /> Nhập thùng</div>
          <div class="pc-val">{soVN(boxed)}</div>
        </div>
        <div class="pc-sep">vs</div>
        <div class="pc-cell">
          <div class="pc-lb"><Icon name="clipboard" size={14} /> Báo cáo thợ</div>
          <div class="pc-val">{soVN(reported)}</div>
        </div>
        <div class="pc-verdict">
          {!hasReport ? "— chưa báo cáo" : match ? "✅ Khớp" : `⚠️ Lệch ${soVN(Math.abs(diff))} (${pctOff.toFixed(1)}%)`}
        </div>
      </div>}

      <section class="card">
        <label class="card-label">Sản phẩm</label>
        {locked
          ? <div class="prod-ro"><Icon name="tag" size={14} /> {slip.sp_name || "Chưa có SP"}</div>
          : <ProductPicker catalog={catalog} value={slip.sp_name || ""} onPick={changeProduct} placeholder="Tìm mã SP" />}
        {slip.sp_mam != null && <div class="muted small">🌿 Số cây 1 mâm: {slip.sp_mam}</div>}
      </section>

      <section class="card">
        <label class="card-label">Ghi chú {noteSaved && <span class="muted small">✓ đã lưu</span>}</label>
        {locked
          ? <div class="prod-ro">{slip.ghi_chu || <span class="muted small">Không có ghi chú</span>}</div>
          : <textarea
              rows={2}
              value={noteInput}
              onInput={(e) => setNoteInput((e.target as HTMLTextAreaElement).value)}
              onBlur={saveNote}
              placeholder="Ghi chú cho phiếu (tự lưu khi rời ô)…"
            />}
      </section>

      <ProductionBoxes threadId={threadId} slip={slip} onChanged={reload} locked={locked} />

      {isSX && <ProductionReport threadId={threadId} slip={slip} locked={locked} />}

      <Images base={`/api/media/production/${threadId}`} />
      <Comments base={`/api/media/production/${threadId}`} />
      <History base={`/api/media/production/${threadId}`} />

      {currentUser()?.role === "admin" && (
        <>
          <button class="btn block prod-lockbtn" onClick={toggleLock}>
            <Icon name={locked ? "key" : "lock"} size={16} /> {locked ? "Mở khoá phiếu (admin)" : "Khoá phiếu ngay (admin)"}
          </button>
          <button class={"btn danger block" + ((slip.box_count || 0) > 0 ? " faded" : "")} onClick={doDelete}
            title={(slip.box_count || 0) > 0 ? "Phiếu đã tạo thùng — xoá thùng trước" : undefined}>
            <Icon name="trash" size={16} /> Xoá phiếu (admin)
          </button>
        </>
      )}
    </div>
  );
}
