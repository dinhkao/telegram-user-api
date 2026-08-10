// TẠO PHIẾU KHO ĐẬU (#/kho-dau/tao?kind=nhap|xuat|dieu_chinh) — chọn loại phiếu,
// kho, rồi các dòng đậu × số lượng. Điều chỉnh: ô số là SỐ ĐẾM THỰC TẾ (prefill =
// tồn đang có, hiện chênh lệch ngay bên cạnh). Xuất: hiện tồn để không xuất quá.
import { useEffect, useMemo, useState } from "preact/hooks";
import {
  BEAN_KIND_LABEL, createBeanSlip, getBeanBoard, soVN,
  type BeanBoardData, type BeanSlipKind,
} from "../api";
import { fmtQty, isoDate, parseQty } from "../format";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { toast } from "../ui/feedback";
import { ErrorState, SkeletonList } from "../ui/states";

type Line = { bean_id: number | null; qty: string; note: string };

const KINDS: BeanSlipKind[] = ["nhap", "xuat", "dieu_chinh"];

function kindFromHash(): BeanSlipKind {
  const m = window.location.hash.match(/[?&]kind=([a-z_]+)/);
  const k = (m ? m[1] : "") as BeanSlipKind;
  return KINDS.includes(k) ? k : "nhap";
}

export function BeanSlipCreate() {
  const [kind, setKind] = useState<BeanSlipKind>(kindFromHash());
  const [data, setData] = useState<BeanBoardData | null>(null);
  const [err, setErr] = useState("");
  const [placeId, setPlaceId] = useState<number | null>(null);
  const [lines, setLines] = useState<Line[]>([{ bean_id: null, qty: "", note: "" }]);
  const [partner, setPartner] = useState("");
  const [note, setNote] = useState("");
  const [ymd, setYmd] = useState(isoDate(new Date()));
  const [busy, setBusy] = useState(false);

  const load = () => getBeanBoard()
    .then((d) => {
      setData(d); setErr("");
      setYmd((v) => d.today_ymd || v);
      setPlaceId((v) => v ?? (d.places[0]?.id ?? null));
    })
    .catch((e: any) => setErr(e?.message || "Lỗi tải kho đậu"));
  useEffect(() => { load(); }, []);

  /** Tồn hiện tại của (loại đậu, kho đang chọn) — 0 nếu chưa có. */
  const stockOf = useMemo(() => (beanId: number | null): number => {
    if (!data || !beanId || !placeId) return 0;
    const row = data.by_bean.find((b) => b.id === beanId);
    return row?.places.find((p) => p.place_id === placeId)?.qty || 0;
  }, [data, placeId]);

  const upd = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  // Điều chỉnh: chọn đậu xong prefill ô số = tồn đang có (người dùng sửa thành số đếm).
  const pickBean = (i: number, beanId: number) => {
    const patch: Partial<Line> = { bean_id: beanId };
    if (kind === "dieu_chinh" && !lines[i].qty) patch.qty = fmtQty(stockOf(beanId));
    upd(i, patch);
  };

  const parsed = lines
    .filter((l) => l.bean_id && l.qty.trim() !== "")
    .map((l) => ({ bean_id: l.bean_id as number, quantity: parseQty(l.qty), note: l.note.trim() }));
  const valid = parsed.filter((l) => (kind === "dieu_chinh" ? l.quantity >= 0 : l.quantity > 0));

  const submit = async () => {
    if (!placeId) return toast("Chọn kho trước", "info");
    if (!valid.length) return toast("Nhập ít nhất 1 dòng đậu có số lượng", "info");
    setBusy(true);
    try {
      const slip = await createBeanSlip({
        kind, place_id: placeId, items: valid,
        partner: partner.trim(), note: note.trim(), ymd,
      });
      toast(`Đã tạo phiếu ${BEAN_KIND_LABEL[kind].toLowerCase()}`, "ok");
      window.location.hash = `#/kho-dau/phieu/${slip.id}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo phiếu", "err");
    } finally {
      setBusy(false);
    }
  };

  if (err && !data) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!data) return <SkeletonList />;
  if (!data.beans.length || !data.places.length) {
    return (
      <div class="bean-create">
        <PageHead fallback="#/kho-dau" title="Tạo phiếu kho đậu" />
        <div class="bean-hint">
          Cần có ít nhất 1 <b>loại đậu</b> và 1 <b>kho</b> trước khi tạo phiếu.{" "}
          <a href="#/kho-dau/thiet-lap">Thiết lập ngay →</a>
        </div>
      </div>
    );
  }

  const beanOpts = data.beans.map((b) => ({
    value: b.id, label: b.name,
    sub: `tồn ${soVN(stockOf(b.id))} ${b.unit}`,
  }));
  const qtyLabel = kind === "dieu_chinh" ? "Số đếm thực tế" : "Số lượng";

  return (
    <div class="bean-create">
      <PageHead fallback="#/kho-dau" title={<>Tạo phiếu {BEAN_KIND_LABEL[kind].toLowerCase()}</>} />

      <div class="seg bean-seg">
        {KINDS.map((k) => (
          <button class={"seg-btn" + (kind === k ? " active" : "")} key={k} onClick={() => setKind(k)}>
            {BEAN_KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <div class="bean-form-row">
        <label class="bean-lbl">Kho</label>
        <SelectPopup value={placeId ?? ""} title="Chọn kho"
          options={data.places.map((p) => ({ value: p.id, label: p.name, sub: p.note || undefined }))}
          onChange={(v) => setPlaceId(Number(v))} placeholder="Chọn kho…" searchable />
      </div>
      <div class="bean-form-row">
        <label class="bean-lbl">Ngày</label>
        <input class="bean-in" type="date" value={ymd}
          onInput={(e: any) => setYmd(e.target.value)} />
      </div>

      <div class="ie-head">Các dòng đậu</div>
      {lines.map((l, i) => {
        const cur = stockOf(l.bean_id);
        const q = parseQty(l.qty);
        const diff = kind === "dieu_chinh" && l.qty.trim() !== "" ? q - cur : null;
        return (
          <div class="bean-line" key={i}>
            <div class="bean-line-top">
              <SelectPopup value={l.bean_id ?? ""} title="Chọn loại đậu" options={beanOpts}
                onChange={(v) => pickBean(i, Number(v))} placeholder="Chọn loại đậu…" searchable />
              <input class="bean-qty-in" type="text" inputMode="decimal" placeholder={qtyLabel}
                value={l.qty} onFocus={(e: any) => e.target.select()}
                onInput={(e: any) => upd(i, { qty: e.target.value })} />
              {lines.length > 1 && (
                <button class="btn small" title="Bỏ dòng"
                  onClick={() => setLines((prev) => prev.filter((_, j) => j !== i))}>
                  <Icon name="close" size={14} />
                </button>
              )}
            </div>
            {l.bean_id ? (
              <div class="bean-line-sub muted small">
                Tồn hiện tại: <b>{soVN(cur)}</b>
                {kind === "xuat" && q > cur ? <span class="t-danger"> · xuất quá tồn</span> : null}
                {diff !== null ? (
                  <span class={diff === 0 ? "" : diff > 0 ? " t-ok" : " t-danger"}>
                    {" · chênh lệch "}{diff > 0 ? "+" : diff < 0 ? "−" : ""}{soVN(Math.abs(diff))}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
      <button class="btn small" onClick={() => setLines((prev) => [...prev, { bean_id: null, qty: "", note: "" }])}>
        <Icon name="plus" size={14} /> Thêm dòng
      </button>

      <div class="bean-form-row">
        <label class="bean-lbl">{kind === "nhap" ? "Nhập từ" : kind === "xuat" ? "Xuất cho" : "Người kiểm"}</label>
        <input class="bean-in" type="text" placeholder="Tuỳ chọn" value={partner}
          onInput={(e: any) => setPartner(e.target.value)} />
      </div>
      <div class="bean-form-row">
        <label class="bean-lbl">Ghi chú</label>
        <input class="bean-in" type="text" placeholder="Tuỳ chọn" value={note}
          onInput={(e: any) => setNote(e.target.value)} />
      </div>

      <button class="btn primary bean-submit" disabled={busy || !valid.length} onClick={submit}>
        {busy ? "Đang lưu…" : `Tạo phiếu ${BEAN_KIND_LABEL[kind].toLowerCase()}`}
      </button>
    </div>
  );
}
