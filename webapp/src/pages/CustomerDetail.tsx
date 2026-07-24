// Chi tiết 1 khách (#/khach/:key) — TRỌNG TÂM là feed ĐƠN + THANH TOÁN (3 kiểu xem
// như dashboard, detail/CustomerFeed). Dưới: ghi chú (sửa được), khối GIÁ BÁN gộp
// (bảng giá chung + giá riêng đè + giá hiệu lực), việc mặc định, pattern nhận diện.
// API: getCustomer / updateCustomer / getCustomerFeed / refreshCustomerDebt.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getCustomer, updateCustomer, refreshCustomerDebt,
  getCustomerPriceList, type CustomerPriceList,
  getPriceLists, type PriceListSummary,
  searchKiotvietCustomers, linkCustomerKiotviet, unlinkCustomerKiotviet, type KvCustomer,
  deleteCustomer, currentUser, type CustomerDetail as Cust } from "../api";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { confirmDialog } from "../ui/feedback";
import { SearchBar } from "../ui/SearchBar";
import { money, parseMoney, initial } from "../format";
import { CustomerFeed } from "../detail/CustomerFeed";
import { History } from "../detail/History";
import { onRealtime } from "../realtime";
import { toast } from "../ui/feedback";
import { Loading, ErrorState, LoadingInline } from "../ui/states";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";

type Row = { sp: string; price: string };

export function CustomerDetail({ ckey }: { ckey: string }) {
  const [cust, setCust] = useState<Cust | null>(null);
  const [err, setErr] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [patterns, setPatterns] = useState("");
  const [noteInput, setNoteInput] = useState("");
  const [nicknameInput, setNicknameInput] = useState("");
  const [nicknameSaved, setNicknameSaved] = useState(false);
  const [noteSaved, setNoteSaved] = useState(false);
  const [savingP, setSavingP] = useState(false);
  const [savingPat, setSavingPat] = useState(false);
  const [debtBusy, setDebtBusy] = useState(false);
  const [effective, setEffective] = useState<CustomerPriceList | null>(null);
  const [priceLists, setPriceLists] = useState<PriceListSummary[]>([]);
  const [savingPl, setSavingPl] = useState(false);

  const hydrate = (c: Cust) => {
    setCust(c);
    const ppl = c.personal_price_list || {};
    setRows(Object.keys(ppl).map((sp) => ({ sp, price: String(ppl[sp]) })));
    setPatterns((c.detectPatterns || []).join(", "));
    setNoteInput(c.note || "");
    setNicknameInput(c.nickname || "");
    setDefTasks(c.default_tasks || []);
  };

  const loadEffective = () => getCustomerPriceList(ckey).then(setEffective).catch(() => setEffective(null));
  const reload = () => {
    getCustomer(ckey).then(hydrate).catch((e) => setErr(e.message));
    loadEffective();
  };

  useEffect(() => { getPriceLists().then(setPriceLists).catch(() => {}); }, []);
  useEffect(() => { reload(); }, [ckey]);

  // Realtime: thông tin khách / bảng giá đổi → tải lại (feed tự lo phần đơn)
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const rel = e.type === "resync" || e.type === "price_lists_changed" ||
        (e.type === "customer_changed" && (e.key == null || e.key === String(ckey)));
      if (rel) { clearTimeout(t); t = setTimeout(reload, 300); }
    });
    return () => { off(); clearTimeout(t); };
  }, [ckey]);

  // ── Ghi chú khách: sửa trực tiếp, tự lưu khi rời ô ──
  const saveNote = async () => {
    if (!cust || noteInput === (cust.note || "")) return;
    try {
      hydrate(await updateCustomer(ckey, { note: noteInput }));
      setNoteSaved(true);
      setTimeout(() => setNoteSaved(false), 1500);
    } catch (e: any) { toast(e.message || "Lỗi lưu ghi chú", "err"); }
  };

  const saveNickname = async () => {
    const value = nicknameInput.trim();
    if (!cust || value === (cust.nickname || "")) return;
    try {
      hydrate(await updateCustomer(ckey, { nickname: value }));
      setNicknameSaved(true);
      setTimeout(() => setNicknameSaved(false), 1500);
    } catch (e: any) { toast(e.message || "Lỗi lưu tên gọi ngắn", "err"); }
  };

  // ── Giá bán ──
  const changePriceList = async (id: string) => {
    setSavingPl(true);
    try {
      hydrate(await updateCustomer(ckey, { price_list: id || null }));
      loadEffective();
      toast("Đã đổi bảng giá chung", "ok");
    } catch (e: any) { toast(e.message, "err"); } finally { setSavingPl(false); }
  };
  const setRow = (i: number, k: keyof Row, v: string) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const addRow = () => setRows((rs) => [...rs, { sp: "", price: "" }]);
  const delRow = (i: number) => setRows((rs) => rs.filter((_, j) => j !== i));
  const savePrices = async () => {
    setSavingP(true);
    const ppl: Record<string, number> = {};
    for (const r of rows) {
      const sp = r.sp.trim();
      const p = parseMoney(r.price);
      if (sp && p > 0) ppl[sp] = p;
    }
    try {
      hydrate(await updateCustomer(ckey, { personal_price_list: ppl }));
      loadEffective();
      toast("Đã lưu giá riêng", "ok");
    } catch (e: any) { toast(e.message, "err"); } finally { setSavingP(false); }
  };

  // ── Việc mặc định: auto-thêm vào MỌI đơn gán khách này. Thêm/xoá LƯU NGAY ──
  const [defTasks, setDefTasks] = useState<string[]>([]);
  const [newTask, setNewTask] = useState("");
  const [savingTasks, setSavingTasks] = useState(false);
  const saveDefTasks = async (list: string[]) => {
    setSavingTasks(true);
    try {
      hydrate(await updateCustomer(ckey, { default_tasks: list }));
      toast("Đã lưu việc mặc định", "ok");
    } catch (e: any) { toast(e.message, "err"); } finally { setSavingTasks(false); }
  };
  const addDefTask = () => {
    const s = newTask.trim();
    if (!s) return;
    if (defTasks.some((t) => t.toLowerCase() === s.toLowerCase())) { setNewTask(""); return; }
    setNewTask("");
    saveDefTasks([...defTasks, s]);
  };
  const delDefTask = (i: number) => saveDefTasks(defTasks.filter((_, j) => j !== i));

  const savePatterns = async () => {
    setSavingPat(true);
    const list = patterns.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    try {
      hydrate(await updateCustomer(ckey, { detectPatterns: list }));
      toast("Đã lưu pattern nhận diện", "ok");
    } catch (e: any) { toast(e.message, "err"); } finally { setSavingPat(false); }
  };

  const doRefreshDebt = async () => {
    setDebtBusy(true);
    try {
      const { debt } = await refreshCustomerDebt(ckey);
      setCust((c) => (c ? { ...c, debt } : c));
      toast("Đã cập nhật nợ KiotViet", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lấy nợ", "err"); } finally { setDebtBusy(false); }
  };

  // ── Liên kết KiotViet (như trang chi tiết SP): badge trạng thái + tìm/gắn/gỡ ──
  const isAdmin = currentUser()?.role === "admin";
  const [linkOpen, setLinkOpen] = useState(false);
  const [kvQ, setKvQ] = useState("");
  const [kvRes, setKvRes] = useState<KvCustomer[]>([]);
  const [kvLoading, setKvLoading] = useState(false);
  usePopupBack(linkOpen, () => setLinkOpen(false));
  useScrollLock(linkOpen);   // khoá cuộn nền khi modal liên kết KiotViet mở
  useEffect(() => {
    if (!linkOpen) return;
    const q = kvQ.trim();
    if (q.length < 2) { setKvRes([]); return; }
    let alive = true;
    setKvLoading(true);
    const t = setTimeout(() => {
      searchKiotvietCustomers(q)
        .then((r) => { if (alive) setKvRes(r); })
        .catch(() => { if (alive) setKvRes([]); })
        .finally(() => { if (alive) setKvLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [kvQ, linkOpen]);
  const doLink = async (kv: KvCustomer) => {
    try {
      hydrate(await linkCustomerKiotviet(ckey, kv.id));
      toast(`✅ Đã liên kết → ${kv.name} #${kv.id}`, "ok");
      setLinkOpen(false);
    } catch (e: any) { toast(e?.message || "Liên kết lỗi", "err"); }
  };
  const doUnlink = async () => {
    if (!(await confirmDialog(`Bỏ liên kết KiotViet #${cust?.kh_id}? Nợ sẽ không tự cập nhật nữa.`, { danger: true, okLabel: "Bỏ liên kết" }))) return;
    try {
      hydrate(await unlinkCustomerKiotviet(ckey));
      toast("Đã bỏ liên kết KiotViet", "ok");
    } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
  };
  // Xoá khách (admin) — CHỈ khi chưa liên kết KiotViet; đã liên kết = nút mờ + toast lý do
  const doDelete = async () => {
    if (cust?.kh_id) { toast("Khách đang liên kết KiotViet — bỏ liên kết trước rồi mới xoá", "err"); return; }
    if (!(await confirmDialog(`Xoá khách "${cust?.name}"? (xoá mềm — đơn cũ giữ nguyên)`, { danger: true, okLabel: "Xoá khách" }))) return;
    try {
      await deleteCustomer(ckey);
      toast("Đã xoá khách", "ok");
      window.location.hash = "#/customers";
    } catch (e: any) { toast(e?.message || "Lỗi xoá khách", "err"); }
  };

  if (err && !cust) return <div class="prod-detail"><BackLink fallback="#/customers" /><ErrorState msg={err} onRetry={reload} /></div>;
  if (!cust) return <div class="prod-detail"><Loading /></div>;

  const owes = Number(cust.debt) > 0;
  return (
    <div class="prod-detail cust-page">
      {/* Header gọn: avatar + tên + KV · nợ + nút cập nhật — 1 khối, không chiếm chỗ feed */}
      <div class="prod-detail-head cust-head">
        <BackLink fallback="#/customers" />
        <span class="co-avatar cust-av" aria-hidden="true">{initial(cust.name)}</span>
        <div class="cust-head-main">
          <div class="prod-sp">{cust.name}</div>
          <div class="muted small">{cust.kh_id ? `KV ${cust.kh_id} · ` : ""}{cust.key}</div>
        </div>
        <button class="cust-debt-chip" disabled={debtBusy} onClick={doRefreshDebt}
          title="Công nợ KiotViet — bấm để cập nhật">
          <span class="cdc-lb">Công nợ</span>
          <b class={owes ? "owe" : "paid-ok"}>{cust.debt != null ? `${money(Number(cust.debt) || 0)}` : "—"}</b>
          <Icon name="refresh" size={13} class={debtBusy ? "spin" : undefined} />
        </button>
      </div>

      <section class="cust-nickname">
        <label for="cust-nickname"><Icon name="tag" size={14} /> Tên gọi ngắn {nicknameSaved && <span>✓ đã lưu</span>}</label>
        <input id="cust-nickname" value={nicknameInput} maxLength={40} placeholder={cust.name || "vd: Ngọc Trang"}
          onInput={(e: any) => setNicknameInput(e.target.value)} onBlur={saveNickname}
          onKeyDown={(e: any) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
        <small>Dùng trên banner giao hàng; để trống sẽ dùng tên đầy đủ.</small>
      </section>

      {/* Trạng thái đồng bộ KiotViet — như trang chi tiết SP */}
      <div class="row space cust-kv-row">
        {cust.kh_id ? (
          <span class="kv-badge on" title="Nợ đồng bộ từ KiotViet theo kh_id này">
            <Icon name="link" size={16} /> Đã liên kết KiotViet #{cust.kh_id}
          </span>
        ) : (
          <span class="kv-badge off">⚠️ Chưa liên kết KiotViet — nợ không tự cập nhật</span>
        )}
        {isAdmin && (
          <span class="row">
            {cust.kh_id
              ? <button class="btn small" onClick={doUnlink}>Bỏ liên kết</button>
              : <button class="btn small primary" onClick={() => { setKvQ(cust.name || ""); setLinkOpen(true); }}>
                  <Icon name="link" size={16} /> Liên kết
                </button>}
            <button class={"btn small danger" + (cust.kh_id ? " faded" : "")} title="Xoá khách (chỉ khi chưa liên kết KiotViet)"
              onClick={doDelete}><Icon name="trash" size={16} /></button>
          </span>
        )}
      </div>

      {linkOpen && (
        <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) setLinkOpen(false); }}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="link" size={18} /> Liên kết khách với KiotViet</div>
            <SearchBar value={kvQ} onInput={setKvQ} autofocus placeholder="Tìm khách KiotViet (tên/mã)…" />
            {kvLoading ? (
              <p class="muted small"><LoadingInline label="Đang tìm…" /></p>
            ) : kvRes.length === 0 ? (
              <p class="muted small">{kvQ.trim().length < 2 ? "Gõ ≥2 ký tự để tìm." : "Không thấy khách KiotViet."}</p>
            ) : (
              <div class="inv-detail-list kv-list">
                {kvRes.map((kv) => (
                  <button class="inv-detail-row link kv-row" key={kv.id} onClick={() => doLink(kv)}>
                    <span class="prod-ord-text">{kv.name}{kv.phone ? ` · ${kv.phone}` : ""}</span>
                    <span class={Number(kv.debt) > 0 ? "owe" : "muted small"}>{kv.debt != null ? money(Number(kv.debt)) : ""}</span>
                    <span class="muted small">#{kv.id}</span>
                  </button>
                ))}
              </div>
            )}
            <button class="btn block mt-2" onClick={() => setLinkOpen(false)}>Đóng</button>
          </div>
        </div>
      )}

      {/* Ghi chú dặn dò — nổi vàng khi CÓ nội dung, sửa trực tiếp, tự lưu khi rời ô */}
      <section class={"card cust-note-card" + (noteInput.trim() ? " has-note" : "")}>
        <label class="card-label"><Icon name="edit" size={15} /> Ghi chú khách {noteSaved && <span class="muted small">✓ đã lưu</span>}</label>
        <textarea rows={noteInput.trim() ? 2 : 1} value={noteInput} placeholder="Dặn dò giao hàng, lưu ý riêng… (tự lưu)"
          onInput={(e: any) => setNoteInput(e.target.value)} onBlur={saveNote} />
      </section>

      {/* ⭐ TRỌNG TÂM: đơn + thanh toán xen kẽ theo thời gian, 3 kiểu xem như dashboard */}
      <CustomerFeed ckey={ckey} />

      {/* ── GIÁ BÁN: 1 khối duy nhất — bảng chung → giá riêng đè → giá hiệu lực ── */}
      <section class="card">
        <label class="card-label"><Icon name="tag" size={16} /> Giá bán</label>
        <div class="pb-form">
          <span class="pb-lb">Bảng giá chung</span>
          <div class="pb-ctl">
            <SelectPopup class="pl-select" title="Bảng giá chung" searchable disabled={savingPl}
              value={String(cust.price_list ?? "")} onChange={changePriceList}
              options={[{ value: "", label: "— Không gắn —" }, ...priceLists.map((pl) => ({ value: pl.id, label: pl.name, sub: `${pl.product_count} SP` }))]} />
          </div>
        </div>

        <div class="cust-ppl-head muted small">Giá riêng của khách (ĐÈ lên bảng giá chung):</div>
        <table class="invoice-table">
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><input value={r.sp} placeholder="Mã SP" onInput={(e: any) => setRow(i, "sp", e.target.value)} /></td>
                <td class="num"><input class="num-inp" type="text" inputMode="numeric" value={r.price} placeholder="Giá" onFocus={(e: any) => e.target.select()} onInput={(e: any) => setRow(i, "price", e.target.value)} /></td>
                <td><button class="btn small" onClick={() => delRow(i)}><Icon name="close" size={16} /></button></td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={3} class="muted small">Chưa có giá riêng — dùng nguyên bảng giá chung.</td></tr>}
          </tbody>
        </table>
        <div class="row">
          <button class="btn small" onClick={addRow}><Icon name="plus" size={16} /> Thêm SP</button>
          <button class="btn primary" disabled={savingP} onClick={savePrices}>{savingP ? "Đang lưu…" : <><Icon name="save" size={16} /> Lưu giá riêng</>}</button>
        </div>

        <details class="collapse-card cust-eff">
          <summary class="card-label collapse-sum">
            Giá hiệu lực đang áp dụng{effective?.name ? ` — ${effective.name}` : ""}
            {effective?.items?.length ? <span class="muted small"> ({effective.items.length} SP)</span> : null}
          </summary>
          {!effective ? (
            <p class="muted small"><LoadingInline /></p>
          ) : effective.items.length ? (
            <table class="invoice-table">
              <tbody>
                {effective.items.map((it) => {
                  const rieng = !!(cust.personal_price_list && it.sp in cust.personal_price_list);
                  return (
                    <tr key={it.sp}>
                      <td>{it.sp} {rieng ? <span class="tag-new">riêng</span> : <span class="muted small">chung</span>}</td>
                      <td class="num">{money(it.price)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p class="muted small">Khách chưa gắn bảng giá chung nào.</p>
          )}
        </details>
      </section>

      <section class="card">
        <label class="card-label"><Icon name="check" size={16} /> Việc mặc định cho đơn</label>
        <p class="muted small">Đơn nào gán khách này sẽ tự có các việc dưới đây (sau 5 việc chuẩn).</p>
        {defTasks.length > 0 && (
          <ul class="deftask-list">
            {defTasks.map((t, i) => (
              <li key={`${t}-${i}`} class="deftask-row">
                <span class="deftask-lb">{t}</span>
                <button class="btn small" disabled={savingTasks} title="Xoá việc" onClick={() => delDefTask(i)}><Icon name="close" size={14} /></button>
              </li>
            ))}
          </ul>
        )}
        <div class="row">
          <input value={newTask} placeholder="vd: Gọi trước khi giao" maxLength={60}
            onInput={(e: any) => setNewTask(e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") { e.preventDefault(); addDefTask(); } }} />
          <button class="btn primary" disabled={savingTasks || !newTask.trim()} onClick={addDefTask}>
            {savingTasks ? "…" : <><Icon name="plus" size={16} /> Thêm</>}
          </button>
        </div>
      </section>

      <details class="card collapse-card">
        <summary class="card-label collapse-sum">Pattern nhận diện khách trong text đơn</summary>
        <textarea rows={3} value={patterns} placeholder="vd: loan phu, chị loàn, lp" onInput={(e: any) => setPatterns(e.target.value)} />
        <button class="btn primary" disabled={savingPat} onClick={savePatterns}>{savingPat ? "Đang lưu…" : <><Icon name="save" size={16} /> Lưu pattern</>}</button>
      </details>

      {/^\d+$/.test(String(ckey)) && <History base={`/api/media/customer/${ckey}`} />}
    </div>
  );
}
