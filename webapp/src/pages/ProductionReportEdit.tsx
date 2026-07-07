// Trang SỬA báo cáo thợ (#/san_xuat/:id/bao-cao) — tách khỏi trang chi tiết (chỉ xem).
// KHOÁ 1 người sửa/phiếu: người vào trước = người sửa; người vào sau bị phủ cảnh báo
// nhưng VẪN thấy bảng đang sửa TRỰC TIẾP (nháp phát realtime). Data: getProduction +
// lock/unlock/draft + saveProductionReport. Khoá + nháp: server_app/production_routes.py.
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getProduction, saveProductionReport, lockReport, unlockReport, pushReportDraft, currentUser, soVN, listMediaImages, mediaImageUrl, deleteMediaImage, postForm, listWorkers, reorderWorkers, type ProdSlip, type ProdReport, type Worker } from "../api";
import { onRealtime } from "../realtime";
import { Loading } from "../ui/states";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { processImage } from "../detail/imageProcess";
import { WorkerOrderPopup } from "../detail/WorkerOrderPopup";

type Wrow = { name: string; gach: string; tru: string; le: string; note: string };

const _num = (s: string): number => { const n = parseFloat((s || "").trim().replace(",", ".")); return isFinite(n) ? n : 0; };
const round2 = (x: number) => Math.round(x * 100) / 100;
const todayVN = (): string => { const d = new Date(); return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`; };
const blankRow = (name = ""): Wrow => ({ name, gach: "", tru: "", le: "", note: "" });
// Seed bảng: có báo cáo đã lưu → dùng nó; trống → tự điền thợ mặc định (template);
// không có template → 1 dòng trống.
const rowsFromReport = (rep: ProdReport | null, defaults: string[] = []): Wrow[] =>
  rep?.rows?.length
    ? rep.rows.map((r) => ({ name: r.name, gach: r.so_gach ? String(r.so_gach) : "", tru: r.so_tru ? String(r.so_tru) : "", le: r.so_cay_le ? String(r.so_cay_le) : "", note: r.note || "" }))
    : defaults.length
      ? defaults.map((n) => blankRow(n))
      : [blankRow()];

export function ProductionReportEdit({ threadId }: { threadId: string }) {
  const me = useMemo(() => { const u = currentUser(); return u?.display_name || u?.username || ""; }, []);
  const [slip, setSlip] = useState<ProdSlip | null>(null);
  const [wrows, setWrows] = useState<Wrow[]>([{ name: "", gach: "", tru: "", le: "", note: "" }]);
  const [date, setDate] = useState(todayVN());
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [holder, setHolder] = useState<string | null>(null);   // null = tôi đang giữ / chưa ai giữ
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const seeded = useRef(false);
  const draftTimer = useRef<any>(null);
  // Danh sách thợ (picker) + thợ mặc định (template tự điền). defaultsRef để seed
  // đúng lúc (nạp thợ TRƯỚC khi seed bảng, tránh race với loadSlip).
  const [workerNames, setWorkerNames] = useState<string[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);   // full (id+name) → map tên↔id khi lưu thứ tự
  const [defaults, setDefaults] = useState<string[]>([]);
  const defaultsRef = useRef<string[]>([]);
  const [orderPop, setOrderPop] = useState(false);        // popup sắp thứ tự thợ
  // Ảnh nền để DÒ — lưu VĨNH VIỄN trên SERVER (DB + đĩa) theo phiếu, scope report_bg
  // (1 ảnh/phiếu, còn mãi + chung mọi máy). Mặc định ẩn; GIỮ nút tròn để hiện (thả ra ẩn).
  const [bgUrl, setBgUrl] = useState<string | null>(null);
  const [bgShow, setBgShow] = useState(false);   // đang giữ nút → hiện ảnh
  const [bgLoading, setBgLoading] = useState(false);
  const bgInput = useRef<HTMLInputElement>(null);

  const mine = !holder;                       // tôi được sửa khi không ai khác giữ
  const readOnly = !!holder;                  // người khác giữ → chỉ xem

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
        setWorkerNames(w.workers.map((x) => x.name));
        setDefaults(w.defaults);
      } catch { /* im — không có thợ thì bảng 1 dòng trống */ }
      loadSlip();
    })();
  }, [threadId]);

  // Chèn thợ mặc định (template) — thêm các thợ chưa có vào bảng
  const insertDefaults = () => {
    const have = new Set(wrows.map((r) => r.name.trim().toLowerCase()).filter(Boolean));
    const toAdd = defaults.filter((n) => !have.has(n.toLowerCase())).map((n) => blankRow(n));
    if (!toAdd.length) return;
    setWrows((rs) => {
      const only = rs.length === 1 && !rs[0].name.trim() && !rs[0].gach && !rs[0].tru && !rs[0].le;
      return only ? toAdd : [...rs, ...toAdd];   // bảng đang trống → thay; có rồi → nối
    });
  };

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
        setWorkers(w.workers); setWorkerNames(w.workers.map((x) => x.name));
        defaultsRef.current = w.defaults; setDefaults(w.defaults);
      }).catch(() => {});
    toast("Đã cập nhật thợ trong bảng");
  };

  // holderRef = bản đồng bộ của `holder` cho listener realtime (deps không đổi → khỏi stale).
  const holderRef = useRef<string | null>(null);
  useEffect(() => { holderRef.current = holder; }, [holder]);

  // Khoá: xin lúc vào + heartbeat 20s; nhả khi rời trang
  useEffect(() => {
    let alive = true;
    const acquire = async () => { try { const r = await lockReport(threadId); if (alive) setHolder(r.mine ? null : r.holder); } catch { /* im */ } };
    acquire();
    const hb = setInterval(acquire, 20000);
    return () => { alive = false; clearInterval(hb); unlockReport(threadId).catch(() => {}); };
  }, [threadId]);

  // Realtime: đổi chủ khoá / nhận nháp của người đang sửa / báo cáo đã lưu
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "report_lock" && e.thread_id === String(threadId)) {
        if (e.holder && e.holder !== me) setHolder(e.holder);
        else if (!e.holder) lockReport(threadId).then((r) => setHolder(r.mine ? null : r.holder)).catch(() => {}); // nhả → tôi giành
      } else if (e.type === "report_draft" && e.thread_id === String(threadId)) {
        // CHỈ người XEM (đang bị người khác giữ khoá) mới nhận nháp; người ĐANG SỬA bỏ
        // qua — kẻo echo/nháp cũ đè lên phím vừa gõ → số vừa nhập biến mất.
        if (holderRef.current && e.draft?.by && e.draft.by !== me) {
          if (Array.isArray(e.draft.rows) && e.draft.rows.length) setWrows(e.draft.rows);
          if (e.draft.date != null) setDate(e.draft.date);
          if (e.draft.start != null) setStart(e.draft.start);
          if (e.draft.end != null) setEnd(e.draft.end);
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
    draftTimer.current = setTimeout(() => { pushReportDraft(threadId, { rows: wrows, date, start, end }).catch(() => {}); }, 500);
    return () => clearTimeout(draftTimer.current);
  }, [wrows, date, start, end, mine]);

  const scm = Number((slip?.bang as ProdReport)?.so_cay_1_mam || slip?.sp_mam || 0);
  const calc = (r: Wrow) => {
    const g = _num(r.gach), t = _num(r.tru), l = _num(r.le);
    const soMam = Math.max(g * 5 - t - (l > 0 ? 1 : 0), 0);
    return { soMam, tong: scm > 0 ? round2(scm * soMam + l) : 0 };
  };
  const grand = useMemo(() => round2(wrows.reduce((s, r) => s + calc(r).tong, 0)), [wrows, scm]);

  const setRow = (i: number, patch: Partial<Wrow>) => setWrows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const addRow = () => setWrows((rs) => [...rs, { name: "", gach: "", tru: "", le: "", note: "" }]);
  const delRow = async (i: number) => {
    const nm = wrows[i]?.name?.trim();
    if (nm && !(await confirmDialog(`Xoá dòng thợ "${nm}"?`, { danger: true }))) return;
    setWrows((rs) => (rs.length > 1 ? rs.filter((_, k) => k !== i) : rs));
  };
  const selAll = (e: any) => e.target.select();   // bấm vào ô → chọn hết nội dung, gõ đè ngay

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
      c[5] = tong ? String(tong) : ""; c[13] = CODE; c[14] = date.trim();
      c[17] = soMam ? String(soMam) : ""; c[18] = start.trim(); c[19] = end.trim();
      return c.join(";");
    });
    return ["thợ;gạch;trừ;lẻ;ghi chú", ...lines].join("\n");
  };

  const save = async () => {
    if (!wrows.some((r) => r.name.trim())) { setMsg("Chưa nhập thợ nào."); return; }
    setBusy(true); setMsg("");
    try {
      const r = await saveProductionReport(threadId, buildText());
      const s = r.sheet;
      const sheetMsg = s?.ok ? `+ Google Sheet (${s.tab})` : s?.disabled ? "(chưa cấu hình Sheet)" : `❌ Sheet: ${s?.error || "?"}`;
      setMsg(`✅ Đã lưu ${sheetMsg}`);
      setTimeout(() => { window.location.hash = `#/san_xuat/${threadId}`; }, 700);
    } catch (e: any) {
      setMsg(e?.message || "Lỗi lưu báo cáo");
    } finally { setBusy(false); }
  };

  if (!slip) return <div class="prod-detail"><BackLink fallback={`#/san_xuat/${threadId}`} /><Loading /></div>;

  return (
    <div class="prod-detail wr-page">
      <div class="prod-detail-head">
        <BackLink fallback={`#/san_xuat/${threadId}`} />
        <div>
          <div class="prod-sp"><Icon name="edit" size={18} /> Sửa báo cáo — {slip.sp_name || "?"}</div>
          <div class="muted small">Phiếu #{threadId}{scm > 0 ? ` · 🌿 ${scm}/mâm` : ""}</div>
        </div>
      </div>

      {readOnly && (
        <div class="wr-lock-alert">
          <Icon name="lock" size={16} /> <b>{holder}</b> đang chỉnh sửa báo cáo này. Bạn đang <b>xem trực tiếp</b> — chỉ 1 người sửa cùng lúc.
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

        {/* Gợi ý chọn thợ từ danh sách chung (gõ để lọc) */}
        <datalist id="wr-worker-list">
          {workerNames.map((n) => <option value={n} key={n} />)}
        </datalist>

        <div class="prod-report-scroll wr-scroll">
          <table class="prod-report-table wr-edit">
            <colgroup>
              <col class="c-name" /><col class="c-num" /><col class="c-num" /><col class="c-num" />
              <col class="c-calc" /><col class="c-calc" /><col class="c-note" />
              {!readOnly && <col class="c-del" />}
            </colgroup>
            <thead>
              <tr><th>Thợ</th><th>Gạch</th><th>Trừ</th><th>Lẻ</th><th>Mâm</th><th>Tổng</th><th>Ghi chú</th>{!readOnly && <th></th>}</tr>
            </thead>
            <tbody>
              {wrows.map((r, i) => {
                const c = calc(r);
                return (
                  <tr key={i} class={c.tong > 0 ? "" : "prod-row-off"}>
                    <td><input class="wr-in wr-name" list="wr-worker-list" value={r.name} disabled={readOnly} onFocus={selAll} onInput={(e: any) => setRow(i, { name: e.target.value })} placeholder="Tên" /></td>
                    <td><input class="wr-in wr-num" inputMode="decimal" value={r.gach} disabled={readOnly} onFocus={selAll} onInput={(e: any) => setRow(i, { gach: e.target.value })} /></td>
                    <td><input class="wr-in wr-num" inputMode="decimal" value={r.tru} disabled={readOnly} onFocus={selAll} onInput={(e: any) => setRow(i, { tru: e.target.value })} /></td>
                    <td><input class="wr-in wr-num" inputMode="decimal" value={r.le} disabled={readOnly} onFocus={selAll} onInput={(e: any) => setRow(i, { le: e.target.value })} /></td>
                    <td class="wr-calc">{soVN(c.soMam)}</td>
                    <td class="wr-calc strong">{soVN(c.tong)}</td>
                    <td><textarea class="wr-in wr-note" rows={1} value={r.note} disabled={readOnly}
                      onFocus={selAll}
                      ref={(el: any) => { if (el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; } }}
                      onInput={(e: any) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; setRow(i, { note: e.target.value }); }}
                      placeholder="—" /></td>
                    {!readOnly && <td><button class="btn small wr-del" title="Xoá dòng" onClick={() => delRow(i)}><Icon name="close" size={16} /></button></td>}
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr><td colSpan={5}>TỔNG CỘNG</td><td class="strong">{soVN(grand)}</td><td colSpan={readOnly ? 1 : 2}></td></tr>
            </tfoot>
          </table>
        </div>

        {!readOnly && (
          <div class="row">
            <button class="btn" onClick={addRow}><Icon name="plus" size={16} /> Thêm thợ</button>
            {defaults.length > 0 && <button class="btn" onClick={insertDefaults} title="Chèn các thợ mặc định"><Icon name="users" size={16} /> Chèn thợ mặc định</button>}
            <button class="btn" onClick={() => setOrderPop(true)} title="Chọn thợ & sắp thứ tự"><Icon name="settings" size={16} /> Chọn/sắp thợ</button>
            <button class="btn primary" disabled={busy} onClick={save}><Icon name="save" size={16} /> Lưu báo cáo</button>
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
          onContextMenu={(e: any) => e.preventDefault()}
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
    </div>
  );
}
