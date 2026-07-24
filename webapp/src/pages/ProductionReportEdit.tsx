// Trang SỬA báo cáo thợ (#/san_xuat/:id/bao-cao) — tách khỏi trang chi tiết (chỉ xem).
// KHOÁ 1 người sửa/phiếu: người vào trước = người sửa; người vào sau bị phủ cảnh báo
// nhưng VẪN thấy bảng đang sửa TRỰC TIẾP (nháp phát realtime). Data: getProduction +
// lock/unlock/draft + saveProductionReport. Khoá + nháp: server_app/production_routes.py.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { BackLink, goBack } from "../nav";
import { PageHead } from "../ui/PageHead";
import { getProduction, saveProductionReport, lockReport, unlockReport, pushReportDraft, currentUser, soVN, listMediaImages, mediaImageUrl, deleteMediaImage, postForm, listWorkers, reorderWorkers, type ProdSlip, type ProdReport, type Worker } from "../api";
import { onRealtime } from "../realtime";
import { rNum as _num, round2, calcRow, type Wrow } from "../detail/reportCalc";
import { Loading } from "../ui/states";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { processImage } from "../detail/imageProcess";
import { WorkerOrderPopup } from "../detail/WorkerOrderPopup";
import { SelectPopup } from "../ui/SelectPopup";

// Gợi ý sẵn cho ô GHI CHÚ (bấm ô → popup chọn nhanh); gõ text khác vẫn được
// (qua nút "Tạo …" của popup) nhưng KHÔNG nạp vào list gợi ý.
const NOTE_PRESETS = ["nghỉ", "vít kẹo", "rắc mè", "rắc dừa", "gỡ bánh", "quậy kẹo", "vô kẹo"];

// spDe/mamDe = 2 cột ĐÈ như sheet (F "Số SP đè" / G "Số mâm đè"): mâm đè thay công
// thức gạch×5−trừ−lẻ; SP đè thay toàn bộ tổng. Rỗng = không đè (ISBLANK sheet).
const todayVN = (): string => { const d = new Date(); return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`; };
const blankRow = (name = ""): Wrow => ({ name, gach: "", tru: "", le: "", note: "", spDe: "", mamDe: "", gio: "" });
// Seed bảng: có báo cáo đã lưu → dùng nó; trống → tự điền thợ mặc định (template);
// không có template → 1 dòng trống.
const rowsFromReport = (rep: ProdReport | null, defaults: string[] = []): Wrow[] =>
  rep?.rows?.length
    ? rep.rows.map((r) => ({
        name: r.name, gach: r.so_gach ? String(r.so_gach) : "", tru: r.so_tru ? String(r.so_tru) : "",
        le: r.so_cay_le ? String(r.so_cay_le) : "", note: r.note || "",
        spDe: r.sp_de != null ? String(r.sp_de) : "", mamDe: r.mam_de != null ? String(r.mam_de) : "",
        gio: r.so_gio != null ? String(r.so_gio) : "",
      }))
    : defaults.length
      ? defaults.map((n) => blankRow(n))
      : [blankRow()];

export function ProductionReportEdit({ threadId }: { threadId: string }) {
  const me = useMemo(() => { const u = currentUser(); return u?.display_name || u?.username || ""; }, []);
  // sid = mã phiên NGẪU NHIÊN mỗi lần mở trang; server gom nhiều phiên của cùng
  // tài khoản vào một khoá, nhưng vẫn giữ heartbeat/nhả khoá riêng cho từng phiên.
  const sid = useMemo(() => Math.random().toString(36).slice(2) + Date.now().toString(36), []);
  const [slip, setSlip] = useState<ProdSlip | null>(null);
  const [wrows, setWrows] = useState<Wrow[]>([blankRow()]);
  const [date, setDate] = useState(todayVN());
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  // Khoá sửa 3 trạng thái: wait = đang xin (chưa cho gõ) · mine = tôi giữ · other = người khác
  const [holder, setHolder] = useState<string | null>(null);
  const [lockState, setLockState] = useState<"wait" | "mine" | "other">("wait");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const seeded = useRef(false);
  const draftTimer = useRef<any>(null);
  const autoTimer = useRef<any>(null);
  const [saveState, setSaveState] = useState<"" | "saving" | "saved" | "error">("");
  // Danh sách thợ + thợ mặc định (template tự điền). defaultsRef để seed
  // đúng lúc (nạp thợ TRƯỚC khi seed bảng, tránh race với loadSlip).
  const [workers, setWorkers] = useState<Worker[]>([]);   // full (id+name) → map tên↔id khi lưu thứ tự
  const defaultsRef = useRef<string[]>([]);
  const [orderPop, setOrderPop] = useState(false);        // popup sắp thứ tự thợ
  const [notePop, setNotePop] = useState<number | null>(null); // popup ghi chú: index dòng đang chọn
  // Ảnh nền để DÒ — lưu VĨNH VIỄN trên SERVER (DB + đĩa) theo phiếu, scope report_bg
  // (1 ảnh/phiếu, còn mãi + chung mọi máy). Mặc định ẩn; GIỮ nút tròn để hiện (thả ra ẩn).
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgShow, setBgShow] = useState(false);   // đang giữ nút → hiện ảnh
  const [bgLoading, setBgLoading] = useState(false);
  const bgInput = useRef<HTMLInputElement>(null);

  const mine = lockState === "mine";          // CHỈ sửa được khi đã cầm khoá xác nhận
  const readOnly = !mine;                     // gồm cả lúc đang xin khoá (wait)

  const loadSlip = async () => {
    const s = await getProduction(threadId);
    setSlip(s);
    if (s && !seeded.current) {                // seed 1 lần từ báo cáo đã lưu / template
      const rep = s.bang as ProdReport | null;
      setWrows(rowsFromReport(rep, defaultsRef.current));
      if ((rep as any)?.date) setDate((rep as any).date);
      if ((rep as any)?.start) setStart((rep as any).start);
      if ((rep as any)?.end) setEnd((rep as any).end);
      seeded.current = true;
    }
  };
  // Nạp danh sách thợ TRƯỚC (để có template), rồi mới seed bảng từ slip.
  useEffect(() => {
    (async () => {
      try {
        const w = await listWorkers();
        defaultsRef.current = w.defaults;
        setWorkers(w.workers);
      } catch { /* im — không có thợ thì bảng 1 dòng trống */ }
      loadSlip();
    })();
  }, [threadId]);

  // Áp CHỌN + THỨ TỰ thợ (từ popup) → DỰNG LẠI bảng theo đúng thợ đã chọn & thứ tự:
  //  • giữ nguyên số liệu thợ đang có; thợ mới chọn = dòng trống; thợ bỏ chọn = gỡ khỏi bảng.
  //  • bỏ thợ ĐÃ NHẬP số liệu → hỏi xác nhận (khỏi mất oan).
  //  • lưu BỀN sort_order toàn cục cho thợ khớp id (template sau đúng thứ tự).
  const applyWorkerSelection = async (order: string[]) => {
    const chosen = new Set(order.map((n) => n.trim().toLowerCase()));
    const dropped = wrows.filter((r) => r.name.trim() && !chosen.has(r.name.trim().toLowerCase())
      && (r.gach || r.tru || r.le || r.note));
    if (dropped.length) {
      const nm = dropped.map((r) => r.name.trim()).join(", ");
      if (!(await confirmDialog(`Bỏ ${dropped.length} thợ đã nhập số liệu khỏi bảng (${nm})? Số liệu của họ sẽ mất.`, { danger: true }))) return;
    }
    const byName = new Map(wrows.filter((r) => r.name.trim()).map((r) => [r.name.trim().toLowerCase(), r] as const));
    const next = order.map((n) => byName.get(n.trim().toLowerCase()) || blankRow(n));
    setWrows(next.length ? next : [blankRow()]);
    const idByName = new Map(workers.map((w) => [w.name.trim().toLowerCase(), w.id] as const));
    const ids = order.map((n) => idByName.get(n.trim().toLowerCase())).filter((x): x is number => typeof x === "number");
    if (ids.length)
      reorderWorkers(ids).then((w) => {
        setWorkers(w.workers);
        defaultsRef.current = w.defaults;
      }).catch(() => {});
    toast("Đã cập nhật thợ trong bảng");
  };

  // mineRef = bản đồng bộ của lockState cho listener realtime (deps không đổi → khỏi stale).
  const mineRef = useRef(false);
  useEffect(() => { mineRef.current = mine; }, [mine]);

  // Xin/gia hạn khoá — cập nhật cả holder lẫn lockState (dùng chung mọi chỗ)
  const aliveRef = useRef(true);
  const acquire = async () => {
    // Listener realtime/heartbeat có thể đã xếp acquire vào microtask ngay lúc trang
    // đang unmount. Chặn TRƯỚC request để khỏi vừa unlock xong lại tự xin khoá.
    if (!aliveRef.current) return;
    try {
      const r = await lockReport(threadId, sid);
      if (!aliveRef.current) {
        // Request đã bay đi trước lúc unmount và hoàn thành muộn: nếu nó vừa giành
        // được khoá thì nhả lần nữa. sid bảo đảm không đụng khoá của phiên mới.
        if (r.mine) unlockReport(threadId, sid).catch(() => {});
        return;
      }
      setHolder(r.mine ? null : r.holder);
      setLockState(r.mine ? "mine" : "other");
    } catch { /* mất mạng → giữ trạng thái hiện tại, heartbeat sẽ thử lại */ }
  };

  // Khoá: xin lúc vào + heartbeat 20s; nhả khi rời trang (đúng phiên sid)
  useEffect(() => {
    aliveRef.current = true;
    acquire();
    const hb = setInterval(acquire, 20000);
    return () => { aliveRef.current = false; clearInterval(hb); unlockReport(threadId, sid).catch(() => {}); };
  }, [threadId]);

  // Realtime: đổi chủ khoá / nhận nháp của người đang sửa / báo cáo đã lưu
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "report_lock" && e.thread_id === String(threadId)) {
        // Mọi thay đổi chủ khoá → hỏi lại server bằng sid (event chỉ mang TÊN,
        // không phân biệt được 2 máy cùng tài khoản). lock idempotent, không cướp.
        acquire();
      } else if (e.type === "report_draft" && e.thread_id === String(threadId)) {
        // CHỈ người XEM nhận nháp; phiên ĐANG SỬA bỏ qua (so sid — cùng tên khác
        // máy vẫn lọc đúng) — kẻo echo/nháp cũ đè lên phím vừa gõ.
        if (!mineRef.current && e.draft?.sid !== sid) {
          if (Array.isArray(e.draft?.rows) && e.draft.rows.length) setWrows(e.draft.rows);
          if (e.draft?.date != null) setDate(e.draft.date);
          if (e.draft?.start != null) setStart(e.draft.start);
          if (e.draft?.end != null) setEnd(e.draft.end);
        }
      } else if ((e.type === "production_changed" || e.type === "resync") && String((e as any).thread_id || "") === String(threadId)) {
        loadSlip();
      }
    });
  }, [threadId, me]);

  // Người sửa → phát nháp (debounce) cho người xem
  useEffect(() => {
    if (!mine || !seeded.current) return;
    clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => { pushReportDraft(threadId, { rows: wrows, date, start, end }, sid).catch(() => {}); }, 500);
    return () => clearTimeout(draftTimer.current);
  }, [wrows, date, start, end, mine]);

  const scm = Number((slip?.bang as ProdReport)?.so_cay_1_mam || slip?.sp_mam || 0);
  const calc = (r: Wrow) => calcRow(r, scm);   // logic dùng chung ở detail/reportCalc
  const grand = useMemo(() => round2(wrows.reduce((s, r) => s + calc(r).tong, 0)), [wrows, scm]);
  // Cột "Giờ" (số giờ làm — SP tính lương theo giờ): chỉ phiếu SẢN XUẤT
  const showGio = (slip?.kind || "san_xuat") === "san_xuat";

  const setRow = (i: number, patch: Partial<Wrow>) => setWrows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const selAll = (e: any) => e.target.select();   // bấm vào ô → chọn hết nội dung, gõ đè ngay
  // Enter trong 1 ô → nhảy focus xuống ĐÚNG CỘT hàng dưới.
  const tableRef = useRef<HTMLTableElement>(null);
  const focusCell = (col: string, row: number): boolean => {
    const el = tableRef.current?.querySelector(`[data-col="${col}"][data-row="${row}"]`) as HTMLInputElement | null;
    if (!el) return false;
    el.focus(); el.select?.(); return true;
  };
  const onCellKey = (col: string, row: number) => (e: any) => {
    // Enter/Go/Next: bàn phím mobile báo key khác nhau → nhận cả keyCode 13
    if (e.key !== "Enter" && e.keyCode !== 13 && e.which !== 13) return;
    e.preventDefault();                     // chặn xuống dòng / submit
    focusCell(col, row + 1);
  };

  // ── Ảnh nền để dò: chọn ảnh (camera/thư viện) → nén bằng engine như trang đơn
  // (processImage: co ~1600px, EXIF, HEIC ok) → upload lên SERVER scope report_bg
  // theo phiếu → lưu bền (DB + đĩa), còn mãi + chung mọi máy. 1 ảnh/phiếu: upload
  // ảnh mới thì xoá ảnh cũ. Giữ nút tròn để hiện; thả ra ẩn.
  const bgBase = `/api/media/report_bg/${threadId}`;
  const refreshBg = async () => {
    try {
      const imgs = await listMediaImages(bgBase);   // sắp mới→cũ
      if (imgs.length) {
        // chỉ giữ ảnh MỚI nhất làm ảnh nền; dọn ảnh cũ (nếu có) cho gọn
        for (const o of imgs.slice(1)) deleteMediaImage(bgBase, o.id).catch(() => {});
        setBgUrl(mediaImageUrl(bgBase, imgs[0].id, "full"));
      } else setBgUrl(null);
    } catch { /* mất mạng → giữ nguyên */ }
  };
  useEffect(() => { refreshBg(); }, [threadId]);   // nạp ảnh nền đã lưu khi vào trang
  // Nạp sẵn ảnh full vào cache trình duyệt ngay khi có URL → bấm 👁️ hiện tức thì
  // (không phải chờ tải ~1600px lần đầu như trước).
  useEffect(() => { if (bgUrl) { const im = new Image(); im.src = bgUrl; } }, [bgUrl]);
  const onPickBg = async (e: any) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBgLoading(true);
    try {
      const p = await processImage(file);
      const fd = new FormData();
      fd.append("photo", p.full, `photo${p.ext}`);
      fd.append("thumb", p.thumb, `thumb${p.ext}`);
      fd.append("width", String(p.width));
      fd.append("height", String(p.height));
      await postForm(`${bgBase}/images`, fd);
      await refreshBg();     // lấy ảnh mới + tự dọn ảnh cũ
    } catch (err: any) {
      setMsg(err?.message || "Không tải được ảnh");
    } finally {
      setBgLoading(false);
    }
  };
  const clearBg = async () => {
    setBgUrl(null); setBgShow(false);
    try { const imgs = await listMediaImages(bgBase); for (const o of imgs) await deleteMediaImage(bgBase, o.id); }
    catch { /* im */ }
  };
  // Desktop: phím 'k' bật/tắt ảnh nền (bỏ qua khi đang gõ trong ô nhập)
  useEffect(() => {
    if (!bgUrl) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "k" && e.key !== "K") return;
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
      setBgShow((s) => !s);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [bgUrl]);

  const buildText = (): string => {
    const CODE = (slip?.sp_name || "").toUpperCase();
    const lines = wrows.filter((r) => r.name.trim()).map((r) => {
      const { soMam, tong } = calc(r);
      const c = Array(20).fill("");
      c[0] = r.name.trim(); c[1] = r.gach.trim(); c[2] = r.tru.trim(); c[3] = r.le.trim(); c[4] = r.note.trim();
      // cột 5/17 = kết quả CUỐI (đã gồm đè, như Text view sheet); cột 6/7 = đè thô
      c[5] = String(tong); c[6] = r.spDe.trim(); c[7] = r.mamDe.trim();
      c[12] = (r.gio || "").trim();   // số giờ làm (SP tính lương theo giờ)
      c[13] = CODE; c[14] = date.trim();
      c[17] = String(soMam); c[18] = start.trim(); c[19] = end.trim();
      return c.join(";");
    });
    return ["thợ;gạch;trừ;lẻ;ghi chú", ...lines].join("\n");
  };

  // TỰ LƯU: gõ xong ~1.5s là lưu (không cần bấm). Chỉ khi TÔI đang sửa + đã seed +
  // có ít nhất 1 thợ. Server tự đẩy Google Sheet. Không điều hướng, chỉ hiện trạng thái.
  useEffect(() => {
    if (!mine || !seeded.current) return;
    if (!wrows.some((r) => r.name.trim())) return;
    clearTimeout(autoTimer.current);
    autoTimer.current = setTimeout(async () => {
      setSaveState("saving");
      try { await saveProductionReport(threadId, buildText(), sid); setSaveState("saved"); }
      catch { setSaveState("error"); }
    }, 1500);
    return () => clearTimeout(autoTimer.current);
  }, [wrows, date, start, end, mine]);   // eslint-disable-line

  // Nút "Xong": lưu ngay (bỏ debounce) rồi quay về chi tiết phiếu.
  const finishEdit = async () => {
    clearTimeout(autoTimer.current);
    if (wrows.some((r) => r.name.trim())) {
      setBusy(true);
      try { await saveProductionReport(threadId, buildText(), sid); } catch { /* im — đã tự lưu trước đó */ }
      setBusy(false);
    }
    // BACK (history.back) thay vì gán hash: gán hash = điều hướng FORWARD → hệ
    // scroll trung tâm (main.tsx useScrollMemory) đưa detail về ĐẦU trang thay vì
    // khôi phục vị trí cũ. goBack → popstate → khôi phục đúng chỗ đang đứng.
    goBack(`#/san_xuat/${threadId}`);
  };

  if (!slip) return <div class="prod-detail"><BackLink fallback={`#/san_xuat/${threadId}`} /><Loading /></div>;

  return (
    <div class="prod-detail wr-page">
      <PageHead fallback={`#/san_xuat/${threadId}`}
        title={<><Icon name="edit" size={18} /> Sửa báo cáo — {slip.sp_name || "?"}</>}
        sub={<>Phiếu #{threadId}{scm > 0 ? ` · 🌿 ${scm}/mâm` : ""}</>}
        right={
          /* Indicator quyền sửa — luôn hiện 1 trong 3 trạng thái */
          <span class={"wr-lockpill " + lockState}>
            {lockState === "mine" ? <><Icon name="check" size={12} /> Bạn đang sửa</>
              : lockState === "other" ? <><Icon name="lock" size={12} /> {holder} đang sửa</>
              : <><Icon name="clock" size={12} /> Xin quyền sửa…</>}
          </span>
        } />

      {lockState === "other" && (
        <div class="wr-lock-alert">
          <Icon name="lock" size={16} /> <b>{holder}</b> đang chỉnh sửa báo cáo này. Bạn đang <b>xem trực tiếp</b> — khi họ xong bạn sẽ tự được quyền sửa.
        </div>
      )}

      <section class="card wr-editcard">
        <div class="prod-report-meta">
          {slip.sp_name && <span><Icon name="box" size={14} /> {slip.sp_name}</span>}
          <label><Icon name="calendar" size={14} /> <input class="wr-meta" value={date} disabled={readOnly} onInput={(e: any) => setDate(e.target.value)} placeholder="d/m/yyyy" /></label>
          <label><Icon name="clock" size={14} /> <input class="wr-meta wr-time" value={start} disabled={readOnly} onInput={(e: any) => setStart(e.target.value)} placeholder="bắt đầu" />–<input class="wr-meta wr-time" value={end} disabled={readOnly} onInput={(e: any) => setEnd(e.target.value)} placeholder="xong" /></label>
        </div>
        {scm <= 0 && <div class="prod-save-msg">⚠️ SP chưa có số cây 1 mâm — chọn mã SP để tính tổng.</div>}

        {/* Ảnh nền để dò — lưu bền; GIỮ nút tròn 👁️ (giữa màn hình, trên nav) để hiện */}
        <div class="wr-bg-ctrl">
          <input ref={bgInput} type="file" accept="image/*" hidden onChange={onPickBg} />
          {!bgUrl ? (
            <button class="btn small" disabled={bgLoading} onClick={() => bgInput.current?.click()}>
              {bgLoading ? "⏳ Đang mở ảnh…" : <><Icon name="image" size={16} /> Ảnh nền để dò</>}
            </button>
          ) : (
            <>
              <span class="wr-bg-lbl"><Icon name="image" size={14} /> Giữ <Icon name="eye" size={14} /> (hoặc phím K) để xem ảnh</span>
              <button class="btn small" onClick={() => bgInput.current?.click()} disabled={bgLoading} title="Đổi ảnh"><Icon name="refresh" size={16} /> Đổi</button>
              <button class="btn small" onClick={clearBg} title="Bỏ ảnh"><Icon name="close" size={16} /> Bỏ</button>
            </>
          )}
        </div>

        <div class="prod-report-scroll wr-scroll">
          <table class="prod-report-table wr-edit" ref={tableRef}>
            <colgroup>
              <col class="c-name" /><col class="c-num" /><col class="c-num" /><col class="c-num" />
              {showGio && <col class="c-num" />}
              <col class="c-num" /><col class="c-num" />
              <col class="c-calc" /><col class="c-calc" /><col class="c-note" />
            </colgroup>
            <thead>
              <tr><th>Thợ</th><th>Gạch</th><th>Trừ</th><th>Lẻ</th>{showGio && <th title="Số giờ làm — SP tính lương theo giờ">Giờ</th>}<th>SP đè</th><th>Mâm đè</th><th>Mâm</th><th>Tổng</th><th>Ghi chú</th></tr>
            </thead>
            <tbody>
              {wrows.map((r, i) => {
                const c = calc(r);
                return (
                  <tr key={i} class={c.tong > 0 ? "" : "prod-row-off"}>
                    <td><span class="wr-worker-name">{r.name || "—"}</span></td>
                    <td><input class="wr-in wr-num" inputMode="decimal" data-col="gach" data-row={i} enterKeyHint="next" value={r.gach} disabled={readOnly} onFocus={selAll} onKeyDown={onCellKey("gach", i)} onInput={(e: any) => setRow(i, { gach: e.target.value })} /></td>
                    <td><input class="wr-in wr-num" inputMode="decimal" data-col="tru" data-row={i} enterKeyHint="next" value={r.tru} disabled={readOnly} onFocus={selAll} onKeyDown={onCellKey("tru", i)} onInput={(e: any) => setRow(i, { tru: e.target.value })} /></td>
                    <td><input class="wr-in wr-num" inputMode="decimal" data-col="le" data-row={i} enterKeyHint="next" value={r.le} disabled={readOnly} onFocus={selAll} onKeyDown={onCellKey("le", i)} onInput={(e: any) => setRow(i, { le: e.target.value })} /></td>
                    {showGio && <td><input class={"wr-in wr-num" + ((r.gio || "").trim() ? " wr-gio-in" : "")} inputMode="decimal" data-col="gio" data-row={i} enterKeyHint="next" title="Số giờ làm — tiền = giờ × tiền 1 giờ của thợ" value={r.gio || ""} disabled={readOnly} onFocus={selAll} onKeyDown={onCellKey("gio", i)} onInput={(e: any) => setRow(i, { gio: e.target.value })} /></td>}
                    <td><input class={"wr-in wr-num" + (c.spDeSet ? " wr-ovr-in" : "")} inputMode="decimal" data-col="spDe" data-row={i} enterKeyHint="next" title="Số SP đè — đè toàn bộ tổng" value={r.spDe} disabled={readOnly} onFocus={selAll} onKeyDown={onCellKey("spDe", i)} onInput={(e: any) => setRow(i, { spDe: e.target.value })} /></td>
                    <td><input class={"wr-in wr-num" + (c.mamDeSet ? " wr-ovr-in" : "")} inputMode="decimal" data-col="mamDe" data-row={i} enterKeyHint="next" title="Số mâm đè — thay công thức gạch" value={r.mamDe} disabled={readOnly} onFocus={selAll} onKeyDown={onCellKey("mamDe", i)} onInput={(e: any) => setRow(i, { mamDe: e.target.value })} /></td>
                    <td class={"wr-calc" + (c.mamDeSet ? " wr-ovr" : "")}>{soVN(c.soMam)}</td>
                    <td class={"wr-calc strong" + (c.spDeSet ? " wr-ovr" : "")}>{soVN(c.tong)}</td>
                    <td><button type="button" class={"wr-in wr-note wr-note-btn" + (r.note ? "" : " empty")}
                      disabled={readOnly} onClick={() => setNotePop(i)}>{r.note || "—"}</button></td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr><td colSpan={showGio ? 8 : 7}>TỔNG CỘNG</td><td class="strong">{soVN(grand)}</td><td></td></tr>
            </tfoot>
          </table>
        </div>

        {!readOnly && (
          <div class="row">
            <button class="btn" onClick={() => setOrderPop(true)} title="Chọn thợ & sắp thứ tự"><Icon name="settings" size={16} /> Chọn/sắp thợ</button>
            <span class="wr-autosave" data-st={saveState}>
              {saveState === "saving" ? "⏳ Đang lưu…" : saveState === "saved" ? "✓ Đã lưu tự động" : saveState === "error" ? "⚠ Lỗi lưu — thử lại" : "Tự lưu khi gõ"}
            </span>
            <button class="btn primary" disabled={busy} onClick={finishEdit}><Icon name="check" size={16} /> Xong</button>
          </div>
        )}
        {msg && <div class="prod-save-msg">{msg}</div>}
      </section>

      {/* Ảnh phủ cố định (fixed) — KHÔNG trôi theo cuộn. Che vùng nhập, chừa app-bar
          + nav; nút 👁️ nổi trên ảnh. Chỉ hiện khi đang giữ nút. */}
      {bgUrl && bgShow && (
        <div class="wr-bg-overlay">
          <img src={bgUrl} alt="" />
        </div>
      )}

      {/* Nút tròn cố định giữa màn hình, trên nav — GIỮ để hiện ảnh, thả ra ẩn */}
      {bgUrl && (
        <button
          class={"wr-peek-btn" + (bgShow ? " on" : "")}
          onPointerDown={(e: any) => { e.preventDefault(); setBgShow(true); }}
          onPointerUp={() => setBgShow(false)}
          onPointerLeave={() => setBgShow(false)}
          onPointerCancel={() => setBgShow(false)}
          // chặn long-press của Android (rung + chọn chữ/menu): touchstart phải
          // preventDefault ở CHÍNH nút — contextmenu một mình không đủ trên WebView
          onTouchStart={(e: any) => e.preventDefault()}
          onContextMenu={(e: any) => { e.preventDefault(); return false; }}
          title="Giữ để xem ảnh"
        ><Icon name="eye" size={20} /></button>
      )}

      <WorkerOrderPopup
        open={orderPop}
        entries={(() => {
          // MỌI thợ: thợ đang trong bảng (on) trước — giữ thứ tự bảng; rồi thợ chung chưa dùng (off)
          const tableNames = wrows.map((r) => r.name.trim()).filter(Boolean);
          const seen = new Set(tableNames.map((n) => n.toLowerCase()));
          return [
            ...tableNames.map((n) => ({ name: n, on: true })),
            ...workers.map((w) => w.name).filter((n) => !seen.has(n.toLowerCase())).map((n) => ({ name: n, on: false })),
          ];
        })()}
        onClose={() => setOrderPop(false)}
        onApply={applyWorkerSelection}
      />

      {/* Popup GHI CHÚ: gợi ý sẵn + gõ text tự do (không nạp vào list). Chọn/tạo → ghi
          thẳng vào dòng đang mở; "— Trống" để xoá ghi chú. */}
      <SelectPopup
        open={notePop != null}
        onClose={() => setNotePop(null)}
        title={`Ghi chú — ${(notePop != null && wrows[notePop]?.name) || "thợ"}`}
        value={notePop != null ? wrows[notePop]?.note || "" : ""}
        options={[
          ...NOTE_PRESETS.map((v) => ({ value: v, label: v })),
          { value: "", label: "— Trống (xoá ghi chú)" },
        ]}
        searchable
        onChange={(v) => { if (notePop != null) setRow(notePop, { note: v }); }}
        onCreate={(t) => { if (notePop != null) setRow(notePop, { note: t }); }}
      />
    </div>
  );
}
