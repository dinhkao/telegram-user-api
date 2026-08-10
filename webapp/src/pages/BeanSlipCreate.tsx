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

// unit_id = đơn vị quy đổi đã chọn; null = ĐƠN VỊ GỐC của loại đậu.
type Line = { bean_id: number | null; qty: string; unit_id: number | null; note: string };

const EMPTY_LINE: Line = { bean_id: null, qty: "", unit_id: null, note: "" };

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
  const [lines, setLines] = useState<Line[]>([{ ...EMPTY_LINE }]);
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

  const beanOf = (id: number | null) => data?.beans.find((b) => b.id === id);
  /** Đơn vị GỐC của loại đậu (kg/bao…) — mọi số tồn tính theo nó. */
  const baseUnit = (id: number | null) => beanOf(id)?.unit || "";
  /** Hệ số của đơn vị đang chọn trên 1 dòng (đơn vị gốc = 1). */
  const factorOf = (l: Line) =>
    (l.unit_id ? beanOf(l.bean_id)?.units?.find((u) => u.id === l.unit_id)?.factor : 1) || 1;
  /** Số đã gõ → quy về ĐƠN VỊ GỐC (server cũng quy đúng như vậy). */
  const baseQty = (l: Line) => parseQty(l.qty) * factorOf(l);

  const upd = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  // Đổi loại đậu = đổi bộ đơn vị → bỏ đơn vị đã chọn của dòng (tránh giữ đơn vị của đậu khác).
  // Điều chỉnh: prefill ô số = tồn đang có, theo ĐƠN VỊ GỐC (người dùng sửa thành số đếm).
  const pickBean = (i: number, beanId: number) => {
    const patch: Partial<Line> = { bean_id: beanId, unit_id: null };
    if (kind === "dieu_chinh" && !lines[i].qty) patch.qty = fmtQty(stockOf(beanId));
    upd(i, patch);
  };

  const parsed = lines
    .filter((l) => l.bean_id && l.qty.trim() !== "")
    .map((l) => ({ bean_id: l.bean_id as number, quantity: parseQty(l.qty),
                   unit_id: l.unit_id, note: l.note.trim() }));
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
        const cur = stockOf(l.bean_id);              // tồn — luôn theo đơn vị GỐC
        const base = baseQty(l);                     // số đã gõ, quy về đơn vị GỐC
        const factor = factorOf(l);
        const bu = baseUnit(l.bean_id);
        const units = beanOf(l.bean_id)?.units || [];
        const diff = kind === "dieu_chinh" && l.qty.trim() !== "" ? base - cur : null;
        return (
          <div class="bean-line" key={i}>
            <div class="bean-line-top">
              <SelectPopup value={l.bean_id ?? ""} title="Chọn loại đậu" options={beanOpts}
                onChange={(v) => pickBean(i, Number(v))} placeholder="Chọn loại đậu…" searchable />
              <input class="bean-qty-in" type="text" inputMode="decimal" placeholder={qtyLabel}
                value={l.qty} onFocus={(e: any) => e.target.select()}
                onInput={(e: any) => upd(i, { qty: e.target.value })} />
              {/* Chọn đơn vị: đơn vị gốc + các đơn vị quy đổi của CHÍNH loại đậu này.
                  Chỉ hiện khi loại đậu có khai quy đổi (khỏi rối khi chỉ dùng 1 đơn vị). */}
              {l.bean_id && units.length > 0 ? (
                <div class="bean-unit-pick">
                  <SelectPopup value={l.unit_id ?? ""} title="Đơn vị"
                    options={[{ value: "", label: bu, sub: "đơn vị gốc" },
                              ...units.map((u) => ({ value: u.id, label: u.name,
                                                     sub: `1 ${u.name} = ${soVN(u.factor)} ${bu}` }))]}
                    onChange={(v) => upd(i, { unit_id: v === "" ? null : Number(v) })}
                    placeholder={bu} />
                </div>
              ) : l.bean_id ? <span class="bean-unit-fixed muted small">{bu}</span> : null}
              {lines.length > 1 && (
                <button class="btn small" title="Bỏ dòng"
                  onClick={() => setLines((prev) => prev.filter((_, j) => j !== i))}>
                  <Icon name="close" size={14} />
                </button>
              )}
            </div>
            {l.bean_id ? (
              <div class="bean-line-sub muted small">
                {factor !== 1 && l.qty.trim() !== "" ? (
                  <b class="bean-conv">= {soVN(base)} {bu}</b>
                ) : null}
                {factor !== 1 && l.qty.trim() !== "" ? " · " : ""}
                Tồn hiện tại: <b>{soVN(cur)} {bu}</b>
                {kind === "xuat" && base > cur ? <span class="t-danger"> · xuất quá tồn</span> : null}
                {diff !== null ? (
                  <span class={diff === 0 ? "" : diff > 0 ? " t-ok" : " t-danger"}>
                    {" · chênh lệch "}{diff > 0 ? "+" : diff < 0 ? "−" : ""}{soVN(Math.abs(diff))} {bu}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
      <button class="btn small" onClick={() => setLines((prev) => [...prev, { ...EMPTY_LINE }])}>
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
