// GIẤY DÁN THÙNG của 1 đơn — #/order/:id/giay-dan-thung. Nhãn dán lên thùng hàng
// gửi xe: người gửi (cố định) · người nhận + SĐT · số thùng · ghi chú (vd "Thu hộ
// 700,000"). Form tự điền: bản đã lưu của đơn, chưa có thì lấy từ giấy dán thùng của
// ĐƠN TRƯỚC gần nhất của khách (khung vàng ghi rõ đơn nào + nhắc kiểm tra trước khi
// in). Thu hộ KHÔNG tự điền — chỉ là chip gợi ý = tiền còn phải thu. Xem trước SỐNG khi
// gõ (detail/GdtLivePreview, ghim đầu trang) + nút Xem trước toàn màn = ảnh PNG server
// render (chữ xoay dọc đúng như tờ in). In = đẩy vào máy in nhiệt như hoá đơn
// (server_app/gdt_routes.py), chọn số tờ 1–5.
import { useEffect, useState } from "preact/hooks";
import { getGdt, printGdt, saveGdt, gdtPngUrl, type GdtBody } from "../api";
import { fmtDateTimeVN } from "../format";
import { GdtLivePreview } from "../detail/GdtLivePreview";
import { SingleImageViewer } from "../detail/SingleImageViewer";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { ErrorState, Loading } from "../ui/states";

const MAX_COPIES = 5;

export function OrderBoxLabel({ threadId }: { threadId: string }) {
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState<any>(null);
  const [f, setF] = useState<GdtBody>({ ten: "", sdt: "", so_thung: "", note: "" });
  const [copies, setCopies] = useState(1);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [suggest, setSuggest] = useState("");   // gợi ý "Thu hộ …" (chip)

  const load = () => {
    setErr("");
    getGdt(threadId)
      .then((j) => {
        setLoaded(j);
        const src = j.gdt || j.prefill;
        setF({ ten: src.ten_gdt || "", sdt: src.sdt_gdt || "", so_thung: src.so_thung || "", note: src.note_gdt || "" });
        setSuggest(j.thu_ho || "");
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [threadId]);

  if (err && !loaded) return <ErrorState msg={err} onRetry={load} />;
  if (!loaded) return <Loading />;

  const set = (k: keyof GdtBody, v: string) => setF((p) => ({ ...p, [k]: v }));
  const check = (): boolean => {
    if (!f.ten.trim()) { toast("Thiếu tên người nhận", "err"); return false; }
    if (!f.so_thung.trim()) { toast("Thiếu số thùng", "err"); return false; }
    return true;
  };
  const doSave = async () => {
    if (busy || !check()) return;
    setBusy(true);
    try {
      await saveGdt(threadId, f);
      toast("Đã lưu giấy dán thùng", "ok");
      window.location.hash = `#/order/${threadId}`;
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); } finally { setBusy(false); }
  };
  const doPrint = async () => {
    if (busy || !check()) return;
    const ask = loaded.gdt ? `Lưu và in ${copies} tờ giấy dán thùng?`
      : `Lưu và in ${copies} tờ giấy dán thùng?\n\nĐã kiểm tra người nhận, số điện thoại và ghi chú chưa? Nội dung đang là gợi ý tự điền.`;
    if (!(await confirmDialog(ask, { okLabel: "In" }))) return;
    setBusy(true);
    try {
      const r = await printGdt(threadId, copies, f);
      toast(`🖨️ Đã gửi lệnh in ${r.copies} tờ`, "ok");
      window.location.hash = `#/order/${threadId}`;
    } catch (e: any) { toast(e?.message || "Lỗi in", "err"); } finally { setBusy(false); }
  };

  const fld = (label: string, k: keyof GdtBody, ph: string, extra: any = {}) => (
    <div class="mt-1">
      <div class="page-head-sub">{label}</div>
      <input class="note-inp" style="width:100%;font-size:1rem;padding:8px" placeholder={ph}
        value={f[k]} onInput={(e: any) => set(k, e.target.value)} {...extra} />
    </div>
  );

  return (
    <div class="prod-detail">
      <PageHead fallback={`#/order/${threadId}`} title="Giấy dán thùng"
        sub={loaded.gdt ? "Sửa nhãn đã lưu" : "Nhãn mới — nội dung gợi ý"}
        right={<button class="btn small" disabled={busy} onClick={() => check() && setPreview(gdtPngUrl(threadId, f))}>
          <Icon name="eye" size={14} /> Xem trước
        </button>} />
      {preview && <SingleImageViewer src={preview} title="giấy dán thùng" onClose={() => setPreview(null)} />}

      {!loaded.gdt && <SourceNote src={loaded.prefill_source} />}
      <GdtLivePreview threadId={threadId} body={f} />

      <section class="card">
        <div class="muted small">Người gửi: <b>{loaded.sender}</b></div>
        {fld("Người nhận *", "ten", "Tên khách / người nhận", { autoFocus: !f.ten })}
        {fld("Số điện thoại", "sdt", "0978 237 353", { type: "tel", inputMode: "tel" })}
        {fld("Số thùng *", "so_thung", "1", { inputMode: "numeric" })}
        {fld("Ghi chú (in dòng cuối)", "note", "Thu hộ 700,000")}
        {(suggest && suggest !== f.note) || f.note ? (
          <div class="chips mt-1">
            {suggest && suggest !== f.note && <button class="chip" onClick={() => set("note", suggest)}>{suggest}</button>}
            {f.note && <button class="chip" onClick={() => set("note", "")}>✕ Xoá ghi chú</button>}
          </div>
        ) : null}
      </section>

      <section class="card">
        <div class="row space">
          <b>Số tờ in</b>
          <span class="row">
            <button class="btn small" disabled={copies <= 1} onClick={() => setCopies((c) => Math.max(1, c - 1))}><Icon name="minus" size={14} /></button>
            <b style="min-width:2ch;text-align:center">{copies}</b>
            <button class="btn small" disabled={copies >= MAX_COPIES} onClick={() => setCopies((c) => Math.min(MAX_COPIES, c + 1))}><Icon name="plus" size={14} /></button>
          </span>
        </div>
        <p class="muted small">In ra máy in nhiệt như hoá đơn — tờ dài ~29 cm, chữ xoay dọc để dán theo cạnh thùng.</p>
        <div class="row mt-2">
          <button class="btn fill" disabled={busy} onClick={doSave}><Icon name="save" size={16} /> Lưu</button>
          <button class="btn fill primary" disabled={busy} onClick={doPrint}><Icon name="printer" size={16} /> Lưu &amp; In</button>
        </div>
      </section>
    </div>
  );
}

/** Khung nhắc NGUỒN của nội dung tự điền (chỉ hiện khi đơn chưa lưu giấy dán thùng). */
function SourceNote({ src }: { src?: { kind: string; thread_id?: number; created?: string } }) {
  const kind = src?.kind || "name";
  let what;
  if (kind === "order" && src?.thread_id) {
    const at = fmtDateTimeVN(src.created);
    what = <>Người nhận, số điện thoại và ghi chú được lấy từ giấy dán thùng gần nhất của khách này —{" "}
      <a href={`#/order/${src.thread_id}`}>đơn #{src.thread_id}</a>{at ? ` (${at})` : ""}. Số thùng và thu hộ không chép.</>;
  } else if (kind === "contact") {
    what = <>Người nhận và số điện thoại được lấy từ lần dán thùng trước của khách này.</>;
  } else {
    what = <>Khách này chưa có giấy dán thùng nào trước đây — người nhận đang tạm lấy theo tên khách.</>;
  }
  return (
    <div class="gdt-src">
      <Icon name="info" size={16} />
      <div>{what} <b>Kiểm tra lại thông tin trước khi in.</b></div>
    </div>
  );
}
