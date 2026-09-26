// Khối TIỀN CÔNG + PHỤ CẤP của 1 phiếu SX — CHỈ văn phòng (parent gate isOffice()).
// Đơn giá lương /1SP CHỐT THEO PHIẾU (sửa ở đây chỉ ảnh hưởng phiếu này; mặc định
// chốt từ bảng lương lúc gán SP). Mỗi thợ: tiền SP (số cây × đơn giá) + chip TĂNG CA
// (bấm bật/tắt) + chip PHỤ CẤP: bấm → popup chọn nhanh (bằng tiền SP cao nhất/nhì/ba —
// KHÔNG tính phụ cấp, bằng 1 thợ cụ thể, Tự nhập qua hộp nhập số, hoặc bỏ).
// Bố cục danh sách (không bảng) → điện thoại xem trọn, không cuộn ngang.
// Data: phieuWages() (đơn giá + phụ cấp), setPhieuWage(), setAllowance().
// Server chặn 403 nếu không office.
import { useEffect, useState } from "preact/hooks";
import { phieuWages, setAllowance, setOvertimeOn, setPhieuWage, soVN, type PhieuWages } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { promptDialog, toast } from "../ui/feedback";
import { SelectPopup } from "../ui/SelectPopup";

import { moneyD as money, money as moneyN } from "../format";

export function ProductionWages({ threadId, workers }: { threadId: string; workers: { name: string; cay: number; gio?: number; note?: string }[] }) {
  const [wage, setWage] = useState(0);
  const [defaultWage, setDefaultWage] = useState(0);
  const [wageDraft, setWageDraft] = useState<string | null>(null);
  const [allow, setAllow] = useState<Record<string, number>>({});
  const [hourly, setHourly] = useState<Record<string, number>>({});   // tiền 1 GIỜ theo thợ
  const [ot, setOt] = useState<{ map: PhieuWages["overtime"]; pct: number }>({ map: {}, pct: 0 });   // tăng ca theo giờ phiếu
  const [loaded, setLoaded] = useState(false);
  const [allowPop, setAllowPop] = useState<string | null>(null); // popup phụ cấp: tên thợ đang chọn

  useEffect(() => {
    let ok = true;
    const load = () =>
      phieuWages(threadId).then((d) => { if (ok) { setWage(d.wage); setDefaultWage(d.default_wage); setAllow(d.allowances || {}); setHourly(d.hourly_rates || {}); setOt({ map: d.overtime || {}, pct: d.ot_pct || 0 }); setLoaded(true); } }).catch(() => { if (ok) setLoaded(true); });
    load();
    // đổi tiền 1 giờ / bảng lương từ máy khác → tải lại đơn giá (khỏi kẹt số cũ).
    // production_changed của CHÍNH phiếu: lưu báo cáo có thể vừa áp PHỤ CẤP TỰ ĐỘNG
    // theo ghi chú (allowance_auto) → tải lại để hiện số mới.
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "workers_changed" || e.type === "productions_changed"
        || (e.type === "production_changed" && String((e as any).thread_id || "") === String(threadId))) {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { ok = false; off(); clearTimeout(t); };
  }, [threadId]);

  // bật/tắt tăng ca 1 thợ: đổi ngay trên màn (lạc quan), lỗi thì trả lại + báo
  const toggleOt = async (name: string, on: boolean) => {
    const prev = ot.map[name];
    if (!prev) return;
    setOt((o) => ({ ...o, map: { ...o.map, [name]: { ...prev, off: !on } } }));
    try {
      await setOvertimeOn(threadId, name, on);
      toast(on ? `Đã bật tăng ca cho ${name}` : `Đã tắt tăng ca cho ${name}`, "ok");
    } catch (e: any) {
      setOt((o) => ({ ...o, map: { ...o.map, [name]: prev } }));
      toast(`Không lưu được: ${e?.message || e}`, "err");
    }
  };

  const saveWage = async () => {
    if (wageDraft === null) return;
    const luong = Number(wageDraft.replace(/[^\d.]/g, "") || 0);
    setWageDraft(null);
    if (luong === wage) return;
    try {
      await setPhieuWage(threadId, luong);
      setWage(luong);
      toast(`Đã chốt đơn giá phiếu này: ${money(luong)}/SP`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu đơn giá", "err"); }
  };

  // Lưu phụ cấp = 1 SỐ CỤ THỂ (chọn từ popup) — không qua draft
  const applyAllow = async (name: string, amount: number) => {
    if (amount === (allow[name] || 0)) return;
    try {
      await setAllowance(threadId, name, amount);
      setAllow((a) => ({ ...a, [name]: Math.max(0, amount) }));
      toast(`Đã lưu phụ cấp: ${money(amount)}`, "ok");
    } catch (e: any) { toast(e?.message || "Lỗi lưu phụ cấp", "err"); }
  };

  if (!loaded) return null;
  const list = workers.filter((w) => w.name);
  if (!list.length) return null;

  // tra tiền-1-giờ KHÔNG phân biệt hoa/thường — tên trong báo cáo (gõ tay/Telegram)
  // có thể lệch case với tên đăng ký; server vốn khớp NOCASE, client phải giống
  const hourlyLower: Record<string, number> = {};
  for (const [k, v] of Object.entries(hourly)) hourlyLower[k.trim().toLowerCase()] = v;
  let totPiece = 0, totAllow = 0, totOt = 0;
  const rows = list.map((w) => {
    // dòng có SỐ GIỜ = SP tính lương theo giờ → tiền = giờ × tiền-1-giờ của thợ
    const gio = w.gio || 0;
    const rate = hourlyLower[w.name.trim().toLowerCase()] || 0;
    const piece = gio > 0 ? Math.round(gio * rate) : Math.round(w.cay * wage);
    const a = allow[w.name] || 0;
    // phụ trội TĂNG CA (cùng công thức server production_store/overtime.ot_money) — chỉ dòng cây
    const o = ot.map[w.name];
    const otFull = o && gio <= 0 ? Math.round(w.cay * wage * o.frac * ot.pct) : 0;   // tiền nếu BẬT
    const otOn = !!o && !o.off;
    const otMoney = otOn ? otFull : 0;
    totPiece += piece; totAllow += a; totOt += otMoney;
    return { name: w.name, cay: w.cay, gio, rate, piece, a, ot: otMoney, otFull, otOn, hasOt: otFull > 0, otMin: o?.min || 0, note: (w.note || "").trim() };
  });
  // Xếp hạng theo TIỀN SP (không tính phụ cấp) cho popup "bằng người cao nhất/nhì/ba"
  const ranked = [...rows].sort((x, y) => y.piece - x.piece);
  // thang cho thanh cấu thành từng thợ = người nhận NHIỀU nhất phiếu
  const maxTotal = Math.max(1, ...rows.map((r) => r.piece + r.ot + r.a));
  const grand = totPiece + totOt + totAllow;
  const pct = (v: number, of: number) => `${Math.max(0, (v / of) * 100)}%`;
  // Tự nhập phụ cấp: hộp nhập bàn phím số (thay ô gõ trong bảng cũ)
  const manualAllow = async (name: string) => {
    const cur = allow[name] || 0;
    const raw = await promptDialog(`Phụ cấp cho ${name} (đồng)`, { type: "tel", initial: cur ? String(cur) : "", placeholder: "vd 11500", okLabel: "Lưu phụ cấp" });
    if (raw == null) return;
    const amount = raw.trim() === "" ? 0 : Number(raw.replace(/[^\d]/g, ""));
    if (!Number.isFinite(amount)) { toast("Số tiền không hợp lệ", "err"); return; }
    applyAllow(name, amount);
  };
  const MEDALS = ["🥇 Bằng cao nhất", "🥈 Bằng cao nhì", "🥉 Bằng cao ba"];
  const onPickAllow = (v: string) => {
    const name = allowPop;
    if (!name) return;
    if (v === "manual") { manualAllow(name); return; }
    if (v === "zero") { applyAllow(name, 0); return; }
    let amt = 0;
    if (v.startsWith("t")) amt = ranked[Number(v.slice(1))]?.piece || 0;
    else if (v.startsWith("w:")) amt = rows.find((r2) => r2.name === v.slice(2))?.piece || 0;
    applyAllow(name, amt);
  };

  return (
    // Bố cục DANH SÁCH (không bảng) để điện thoại xem trọn không cuộn ngang. Chữ ký:
    // thanh CẤU THÀNH 3 màu (tiền SP · tăng ca · phụ cấp) — cả phiếu ở đầu khối, từng
    // thợ ở dưới tên (cùng thang = người nhận nhiều nhất) để so nhanh ai nhận bao nhiêu.
    <section class="card pwl">
      <div class="card-head">
        <label class="card-label"><Icon name="wallet" size={16} /> Tiền công + phụ cấp</label>
        <span class="muted small"><Icon name="lock" size={13} /> văn phòng</span>
      </div>

      <div class="pwl-sum">
        <div class="pwl-sum-top">
          <div>
            <div class="pwl-sum-lbl">Tổng phiếu</div>
            <div class="pwl-sum-val">{money(grand)}</div>
          </div>
          <label class="pwl-wage">
            <span class="pwl-sum-lbl">Đơn giá phiếu</span>
            <span class="pwl-wage-in">
              <input class="pw-input pw-wage-input" inputMode="numeric"
                value={wageDraft !== null ? wageDraft : (wage ? String(wage) : "")}
                placeholder="0"
                onInput={(e: any) => setWageDraft(e.target.value)}
                onBlur={saveWage}
                onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
              <span class="muted small">đ/cây</span>
            </span>
            {defaultWage !== wage ? <span class="pwl-wage-note">bảng lương {soVN(defaultWage)}đ</span> : null}
          </label>
        </div>
        {grand > 0 && (
          <div class="pwl-bar big" aria-hidden="true">
            <i class="sp" style={{ width: pct(totPiece, grand) }} />
            <i class="tc" style={{ width: pct(totOt, grand) }} />
            <i class="pc" style={{ width: pct(totAllow, grand) }} />
          </div>
        )}
        <div class="pwl-legend">
          <span><i class="sp" />Tiền SP <b>{moneyN(totPiece)}</b></span>
          {totOt > 0 && <span><i class="tc" />Tăng ca <b>{moneyN(totOt)}</b></span>}
          <span><i class="pc" />Phụ cấp <b>{moneyN(totAllow)}</b></span>
        </div>
      </div>

      <ul class="pwl-list">
        {rows.map((r) => {
          const total = r.piece + r.ot + r.a;
          const idle = total === 0 && !r.hasOt;   // không sản lượng, chưa phụ cấp → 1 dòng gọn
          const pcChip = (
            <button type="button" class={"pwl-chip pc" + (r.a ? " on" : "")} onClick={() => setAllowPop(r.name)}
              title="Phụ cấp của thợ ở phiếu này — bấm để chọn nhanh hoặc tự nhập">
              {r.a ? <>PC {moneyN(r.a)}</> : <>+ Phụ cấp</>}
            </button>
          );
          return (
            <li class={"pwl-row" + (idle ? " idle" : "")} key={r.name}>
              <div class="pwl-top">
                <a class="wr-tho-link pwl-name" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>{r.name}</a>
                {r.note ? <span class="pwl-note">{r.note}</span> : null}
                {idle && pcChip}
                <b class={"pwl-total" + (total ? "" : " zero")}>{money(total)}</b>
              </div>
              {!idle && (
                <div class="pwl-bits">
                  <span class="pwl-calc">
                    {r.gio > 0
                      ? <>{soVN(r.gio)} giờ × {soVN(r.rate)}{r.rate <= 0 ? <span class="t-danger"> · chưa đặt tiền 1 giờ</span> : null}</>
                      : r.cay > 0 ? <>{soVN(r.cay)} cây × {soVN(wage)}</> : <>không sản lượng</>}
                  </span>
                  {r.hasOt && (
                    // bấm để tắt/bật tăng ca riêng thợ này (mặc định bật)
                    <button type="button" role="switch" aria-checked={r.otOn} class={"pwl-chip tc" + (r.otOn ? " on" : "")}
                      onClick={() => toggleOt(r.name, !r.otOn)}
                      title={`${r.otOn ? "Đang tính" : "Đã tắt"} tăng ca (+${Math.round(ot.pct * 100)}% đơn giá phần cây làm trong giờ tăng ca) — bấm để ${r.otOn ? "tắt" : "bật"}`}>
                      <span class="pwl-dot" />TC {r.otMin ? `${r.otMin}p ` : ""}<span class="pwl-amt">+{moneyN(r.otFull)}</span>
                    </button>
                  )}
                  {pcChip}
                </div>
              )}
              {!idle && total > 0 && (
                <div class="pwl-bar" aria-hidden="true">
                  <i class="sp" style={{ width: pct(r.piece, maxTotal) }} />
                  <i class="tc" style={{ width: pct(r.ot, maxTotal) }} />
                  <i class="pc" style={{ width: pct(r.a, maxTotal) }} />
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {/* Popup chọn nhanh PHỤ CẤP: bằng tiền SP cao nhất/nhì/ba của bảng (không tính
          phụ cấp), bằng 1 thợ cụ thể, tự nhập, hoặc bỏ phụ cấp. */}
      <SelectPopup
        open={allowPop != null}
        onClose={() => setAllowPop(null)}
        title={`Phụ cấp — ${allowPop || ""}`}
        value={null}
        options={[
          ...ranked.slice(0, 3).map((r2, k) => ({ value: `t${k}`, label: `${MEDALS[k]} — ${r2.name}`, sub: money(r2.piece) })),
          ...rows.filter((r2) => r2.name !== allowPop).map((r2) => ({ value: `w:${r2.name}`, label: `Bằng ${r2.name}`, sub: money(r2.piece) })),
          { value: "manual", label: "✏️ Tự nhập số tiền" },
          ...(allowPop && allow[allowPop] ? [{ value: "zero", label: "✕ Bỏ phụ cấp" }] : []),
        ]}
        onChange={onPickAllow}
      />
    </section>
  );
}
