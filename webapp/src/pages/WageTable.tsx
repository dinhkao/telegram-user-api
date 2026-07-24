// Bảng LƯƠNG SP (#/luong-sp) — CHỈ văn phòng. Sửa đơn giá lương / 1 SP của từng
// mã: gõ số vào ô rồi rời ô (blur) là lưu; đơn giá 0/xoá trắng = gỡ mã khỏi bảng
// (SP về missing_wage). Thêm mã mới bằng ProductPicker + ô đơn giá.
// Data: listWages/setWage (+productionCatalog cho picker). Emit productions_changed
// phía server → dashboard tiền công + phiếu báo cáo tự tính lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { isOffice, listWages, productionCatalog, setWage, soVN, type ProdCatalogItem, type WageEntry } from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";
import { ProductPicker } from "../detail/ProductPicker";

const money = (n: number) => soVN(Math.round(n)) + "đ";

export function WageTable() {
  const [rows, setRows] = useState<WageEntry[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [catalog, setCatalog] = useState<ProdCatalogItem[]>([]);
  const [newCode, setNewCode] = useState("");
  const [newLuong, setNewLuong] = useState("");
  const savingRef = useRef<Set<string>>(new Set());

  const load = async () => {
    try { setRows(await listWages()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải bảng lương"); }
  };
  useEffect(() => { load(); productionCatalog().then(setCatalog).catch(() => {}); }, []);

  const save = async (code: string, luongStr: string, old: number) => {
    const luong = Number(String(luongStr).replace(/[^\d.]/g, "") || 0);
    if (luong === old) return;
    if (savingRef.current.has(code)) return;
    savingRef.current.add(code);
    try {
      setRows(await setWage(code, luong));
      toast(luong > 0 ? `${code}: ${money(luong)}/SP` : `Đã gỡ ${code} khỏi bảng lương`, "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
      load();
    } finally {
      savingRef.current.delete(code);
    }
  };

  const addNew = async () => {
    const code = newCode.trim().toUpperCase();
    const luong = Number(newLuong.replace(/[^\d.]/g, "") || 0);
    if (!code) { toast("Chọn mã SP trước", "err"); return; }
    if (luong <= 0) { toast("Nhập đơn giá lương (> 0)", "err"); return; }
    if (rows?.some((r) => r.code === code)) { toast(`${code} đã có trong bảng — sửa trực tiếp ở dòng của nó`, "err"); return; }
    try {
      setRows(await setWage(code, luong));
      toast(`Đã thêm ${code}: ${money(luong)}/SP`, "ok");
      setNewCode(""); setNewLuong("");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    }
  };

  const head = (
    <PageHead fallback="#/home"
      title={<><Icon name="wallet" size={18} /> Lương sản phẩm</>}
      sub="đơn giá tiền công / 1 SP theo mã — sửa là dashboard tiền tự tính lại" />
  );

  if (!isOffice()) return <div class="rs-page">{head}<EmptyState icon="🔒">Chỉ văn phòng được xem bảng lương.</EmptyState></div>;
  if (err) return <div class="rs-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!rows) return <div class="rs-page">{head}<Loading /></div>;

  const qn = q.trim().toUpperCase();
  const shown = qn ? rows.filter((r) => r.code.includes(qn) || (r.product_name || "").toUpperCase().includes(qn)) : rows;

  return (
    <div class="rs-page">
      {head}

      <section class="card rs-create">
        <label class="card-label"><Icon name="plus" size={15} /> Thêm mã vào bảng lương</label>
        <div class="wt-add">
          <div class="wt-add-code"><ProductPicker catalog={catalog} value={newCode} onPick={setNewCode} placeholder="Tìm mã SP" /></div>
          <input class="wt-add-luong" type="text" inputMode="numeric" placeholder="đ/SP" value={newLuong}
            onInput={(e: any) => setNewLuong(e.currentTarget.value)} />
          <button class="btn small primary" onClick={addNew}>Thêm</button>
        </div>
      </section>

      <SearchBar value={q} onInput={setQ} placeholder="Lọc mã / tên SP…" />

      {shown.length === 0 ? (
        <EmptyState icon="💰">{qn ? "Không có mã nào khớp." : "Bảng lương trống — thêm mã ở trên."}</EmptyState>
      ) : (
        <div class="card rs-list">
          {shown.map((r) => (
            <div class="wt-row" key={r.code}>
              <div class="wt-main">
                <span class="wt-code">{r.code}</span>
                {r.product_name ? <span class="wt-name muted small">{r.product_name}</span> : null}
                {r.updated_by ? <span class="wt-upd muted small">sửa bởi {r.updated_by}</span> : null}
              </div>
              <div class="wt-input-wrap">
                <input class="wt-input" type="text" inputMode="numeric" defaultValue={String(r.luong || "")}
                  onBlur={(e: any) => save(r.code, e.currentTarget.value, r.luong)}
                  onKeyDown={(e: any) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
                <span class="muted small">đ/SP</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <p class="muted small" style={{ padding: "4px 2px" }}>
        Để trống hoặc nhập 0 rồi rời ô = gỡ mã khỏi bảng (số SP của mã đó sẽ KHÔNG được tính tiền và hiện ở cảnh báo thiếu đơn giá).
      </p>
    </div>
  );
}
