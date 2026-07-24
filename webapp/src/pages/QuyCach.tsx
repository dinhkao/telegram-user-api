// Quy cách đóng gói (#/quy-cach) — admin sửa số cái / thùng, cái / bịch theo
// mã SP. Đọc/ghi qua GET/POST /api/quy-cach. TỰ ĐỘNG LƯU (debounce) mỗi khi đổi —
// không có nút Lưu. Dùng PageHead + states + toast.
import { useEffect, useRef, useState } from "preact/hooks";
import { currentUser, getQuyCach, setQuyCach, type QuyCach } from "../api";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

// Một dòng override: mã SP → số cái
type OverrideRow = { code: string; value: number };

function overridesToList(o: Record<string, number>): OverrideRow[] {
  const r: OverrideRow[] = [];
  for (const k of Object.keys(o).sort()) r.push({ code: k, value: o[k] });
  return r;
}

function listToOverrides(list: OverrideRow[]): Record<string, number> {
  const o: Record<string, number> = {};
  for (const row of list) {
    const c = row.code.trim().toUpperCase();
    if (c) o[c] = row.value;
  }
  return o;
}

export function QuyCachPage() {
  const user = currentUser();
  const [cfg, setCfg] = useState<QuyCach | null>(null);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState<"" | "saving" | "saved">("");
  const [thungRows, setThungRows] = useState<OverrideRow[]>([]);
  const [bichRows, setBichRows] = useState<OverrideRow[]>([]);
  const loadedRef = useRef(false);       // đã qua lần render sau khi tải chưa (đừng auto-save lúc vừa tải)
  const saveTimer = useRef<any>(null);
  const okTimer = useRef<any>(null);

  const load = async () => {
    setErr("");
    loadedRef.current = false;
    try {
      const c = await getQuyCach();
      setCfg(c);
      setThungRows(overridesToList(c.thung_overrides));
      setBichRows(overridesToList(c.bich_overrides));
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải quy cách đóng gói");
    }
  };
  useEffect(() => { load(); }, []);

  // TỰ ĐỘNG LƯU: mỗi khi cfg/bảng đổi → debounce 700ms rồi POST. Bỏ qua lần set
  // state ngay sau khi tải về (loadedRef). KHÔNG đồng bộ state từ response để không
  // cắt ngang lúc đang gõ (server chuẩn hoá mã/khử dòng rỗng, local là nguồn sự thật).
  useEffect(() => {
    if (!cfg) return;
    if (!loadedRef.current) { loadedRef.current = true; return; }
    if (saveTimer.current) clearTimeout(saveTimer.current);
    setStatus("saving");
    const snapshot: QuyCach = {
      ...cfg,
      thung_overrides: listToOverrides(thungRows),
      bich_overrides: listToOverrides(bichRows),
    };
    saveTimer.current = setTimeout(async () => {
      try {
        await setQuyCach(snapshot);
        setStatus("saved");
        if (okTimer.current) clearTimeout(okTimer.current);
        okTimer.current = setTimeout(() => setStatus(""), 1500);
      } catch (e: any) {
        setStatus("");
        toast(e?.message || "Lỗi lưu quy cách", "err");
      }
    }, 700);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
  }, [cfg, thungRows, bichRows]);

  const updateField = (k: keyof QuyCach, v: number) => {
    if (!cfg) return;
    setCfg({ ...cfg, [k]: v });
  };

  const statusEl = status === "saving"
    ? <span class="qc-status">⏳ Đang lưu…</span>
    : status === "saved"
      ? <span class="qc-status ok">✓ Đã lưu</span>
      : <span class="qc-status muted">Tự lưu</span>;

  const head = (
    <PageHead fallback="#/login"
      title="📦 Quy cách đóng gói"
      sub="số cái / 1 thùng, 1 bịch, 1 lốc — admin sửa"
      right={statusEl} />
  );

  if (!user || user.role !== "admin") {
    return (
      <div class="rs-page">
        {head}
        <div class="card">
          <p class="muted center">🔒 Chỉ admin được xem trang này.</p>
          <p class="center"><a class="btn" href="#/login">← Quay lại</a></p>
        </div>
      </div>
    );
  }
  if (err) return <div class="rs-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!cfg) return <div class="rs-page">{head}<Loading /></div>;

  const addThungRow = () => setThungRows([...thungRows, { code: "", value: 1 }]);
  const updThungRow = (i: number, c: string, v: number) => {
    const r = [...thungRows]; r[i] = { code: c, value: v }; setThungRows(r);
  };
  const delThungRow = (i: number) => setThungRows(thungRows.filter((_, j) => j !== i));

  const addBichRow = () => setBichRows([...bichRows, { code: "", value: 1 }]);
  const updBichRow = (i: number, c: string, v: number) => {
    const r = [...bichRows]; r[i] = { code: c, value: v }; setBichRows(r);
  };
  const delBichRow = (i: number) => setBichRows(bichRows.filter((_, j) => j !== i));

  return (
    <div class="rs-page">
      {head}

      <section class="card">
        <label class="card-label">📐 Số mặc định</label>
        <div class="set-row">
          <span style={{ flex: 1 }}>1 thùng (<b>t</b>) mặc định =</span>
          <input class="qc-num" type="text" inputMode="numeric"
            value={cfg.thung_base}
            onInput={(e: any) => updateField("thung_base", Number(e.currentTarget.value) || 1)} />
          <span>cái</span>
        </div>
        <div class="set-row">
          <span style={{ flex: 1 }}>1 bịch (<b>b</b>) mặc định =</span>
          <input class="qc-num" type="text" inputMode="numeric"
            value={cfg.bich_base}
            onInput={(e: any) => updateField("bich_base", Number(e.currentTarget.value) || 1)} />
          <span>cái</span>
        </div>
        <div class="set-row">
          <span style={{ flex: 1 }}>1 lốc <b>DM180</b> =</span>
          <input class="qc-num" type="text" inputMode="numeric"
            value={cfg.dm180_loc}
            onInput={(e: any) => updateField("dm180_loc", Number(e.currentTarget.value) || 1)} />
          <span>cái</span>
        </div>
      </section>

      <section class="card">
        <label class="card-label"><Icon name="box" size={15} /> Số cái / 1 THÙNG theo mã (đè mặc định)</label>
        {thungRows.length === 0 ? (
          <p class="muted small" style={{ margin: "4px 0 8px" }}>Chưa có override nào.</p>
        ) : (
          <div style={{ marginBottom: 8 }}>
            {thungRows.map((r, i) => (
              <div class="qc-override-row" key={i}>
                <input class="qc-code" type="text" placeholder="Mã SP"
                  value={r.code}
                  onInput={(e: any) => updThungRow(i, e.currentTarget.value.toUpperCase(), r.value)} />
                <input class="qc-val" type="text" inputMode="numeric"
                  value={r.value}
                  onInput={(e: any) => updThungRow(i, r.code, Number(e.currentTarget.value) || 1)} />
                <button class="qc-del" onClick={() => delThungRow(i)} title="Xoá dòng">✕</button>
              </div>
            ))}
          </div>
        )}
        <button class="btn small" onClick={addThungRow}>+ Thêm dòng</button>
      </section>

      <section class="card">
        <label class="card-label">🛍️ Số cái / 1 BỊCH theo mã (đè mặc định)</label>
        {bichRows.length === 0 ? (
          <p class="muted small" style={{ margin: "4px 0 8px" }}>Chưa có override nào.</p>
        ) : (
          <div style={{ marginBottom: 8 }}>
            {bichRows.map((r, i) => (
              <div class="qc-override-row" key={i}>
                <input class="qc-code" type="text" placeholder="Mã SP"
                  value={r.code}
                  onInput={(e: any) => updBichRow(i, e.currentTarget.value.toUpperCase(), r.value)} />
                <input class="qc-val" type="text" inputMode="numeric"
                  value={r.value}
                  onInput={(e: any) => updBichRow(i, r.code, Number(e.currentTarget.value) || 1)} />
                <button class="qc-del" onClick={() => delBichRow(i)} title="Xoá dòng">✕</button>
              </div>
            ))}
          </div>
        )}
        <button class="btn small" onClick={addBichRow}>+ Thêm dòng</button>
      </section>

      <p class="muted small" style={{ padding: "0 4px 8px" }}>
        Thay đổi <b>tự động lưu</b>. Nhập tay số sau <code>&lt;n&gt;t</code> / <code>&lt;n&gt;b</code> trong
        nội dung đơn vẫn ghi đè bảng này. VD: <code>K10 2b</code> = 2 bịch × (bịch của K10).
      </p>

      <p class="center" style={{ margin: "12px 0" }}><a class="btn" href="#/login">← Quay lại</a></p>
    </div>
  );
}
