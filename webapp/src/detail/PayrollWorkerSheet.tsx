// HỒ SƠ LƯƠNG THÁNG của 1 thợ — nội dung popup khi bấm Ô TÊN ở bảng lương (#/luong-thang).
// Gom MỌI khoản của tháng vào 1 màn: thực lãnh + thanh tỉ lệ (lương/phụ cấp/thưởng ↔ ứng),
// NGUỒN lương (thợ SP: gộp theo mã SP từ báo cáo sản xuất · thợ TG: mốc → công → tăng ca),
// TỪNG khoản phụ cấp, TỪNG lần ứng (kèm lương tuần tự động), thưởng tháng cũ.
// CHỈ ĐỌC + điều hướng: mỗi khối bấm được để nhảy sang tab sửa tương ứng của popup
// (pc/ung/luong/cong/tc) — cố tình KHÔNG dựng editor thứ 2 ở đây, thao tác thêm/vô
// hiệu/sửa ghi chú chỉ nằm ở EntryPanel (xem luật ĐỒNG BỘ 2 CHỖ trong PayrollCellPopup).
// CHẤM CÔNG hiện LUÔN cho MỌI thợ (không riêng thợ lương thời gian): khối "Chấm công"
// = tổng công/TC + từng ngày; thợ lương SP xem view "Theo ngày" thì mỗi ngày còn kèm
// công + giờ chấm của ngày đó (thấy ngay hôm nào đi làm mà không có báo cáo SX).
// Data: listPayrollAllowances + listPayrollAdvances + getWorkerReport (thợ lương SP)
// + getAttendanceSummary (chấm công tháng).
import { useEffect, useState } from "preact/hooks";
import {
  getAttendanceSummary, getWorkerReport, listPayrollAdvances, listPayrollAllowances, soVN,
  type AttendanceDay, type PayrollRow, type SalaryAdvance, type SalaryAllowance, type WorkerReport,
} from "../api";
import { moneyR as money, dmy, pad2, ymLabel } from "../format";
import { mocNguon, type PayrollCol } from "./PayrollCellPopup";
import { AttendanceDayRows, attRows, attTotals, congVN, otVN, pairs } from "./AttendanceDays";
import { Icon } from "../ui/Icon";
import { LoadingInline } from "../ui/states";

/** Số cây: có dấu chấm nghìn, bỏ đuôi ,00 (3420 → "3.420"; 12,5 → "12,5"). */
const cayVN = (n: number) => soVN(Math.round((n || 0) * 100) / 100);
const monthFrom = (ym: string) => `${ym}-01`;
const monthTo = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return `${ym}-${pad2(new Date(y, m, 0).getDate())}`;
};

/** Gộp dòng báo cáo SX của tháng theo MÃ SP: bao nhiêu cây, mấy phiếu, ra bao nhiêu tiền. */
function byProduct(rep: WorkerReport | null) {
  const m = new Map<string, { code: string; cay: number; money: number; phieu: Set<number> }>();
  for (const row of rep?.rows || []) {
    const code = row.product_code || "—";
    const it = m.get(code) || { code, cay: 0, money: 0, phieu: new Set<number>() };
    it.cay += row.tong_calc || 0;
    it.money += row.money || 0;
    it.phieu.add(row.thread_id);
    m.set(code, it);
  }
  return [...m.values()].sort((a, b) => b.money - a.money || b.cay - a.cay);
}

/** Gộp dòng báo cáo SX theo NGÀY (report_ymd) — xem lương SP rơi vào ngày nào. */
function byDay(rep: WorkerReport | null) {
  const m = new Map<string, { ymd: string; cay: number; money: number; codes: Set<string>; phieu: Set<number> }>();
  for (const row of rep?.rows || []) {
    const ymd = row.ymd || "";
    const it = m.get(ymd) || { ymd, cay: 0, money: 0, codes: new Set<string>(), phieu: new Set<number>() };
    it.cay += row.tong_calc || 0;
    it.money += row.money || 0;
    if (row.product_code) it.codes.add(row.product_code);
    it.phieu.add(row.thread_id);
    m.set(ymd, it);
  }
  return [...m.values()].sort((a, b) => a.ymd.localeCompare(b.ymd));   // đầu tháng → cuối tháng
}

/** Tiêu đề 1 khối: nhãn + tổng + chevron, bấm → mở tab sửa tương ứng. */
function Block({ label, sub, total, tone, onTap }: {
  label: string; sub?: any; total: string; tone?: "ok" | "danger"; onTap?: () => void;
}) {
  return (
    <button class={`pws-block${onTap ? " tappable" : ""}`} disabled={!onTap} onClick={onTap}>
      <span class="pws-block-l">
        <b>{label}</b>
        {sub ? <span class="muted small">{sub}</span> : null}
      </span>
      <b class={tone === "danger" ? "t-danger" : tone === "ok" ? "t-ok" : ""}>{total}</b>
      {onTap ? <Icon name="chevronRight" size={15} /> : null}
    </button>
  );
}

export function PayrollWorkerSheet({ ym, r, onCol, toggleType, toggleWeekly }: {
  ym: string; r: PayrollRow;
  onCol: (c: PayrollCol) => void;   // mở tab tương ứng của PayrollCellPopup (gồm "moc")
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
}) {
  const isTime = r.wage_type === "time";
  const wid = r.worker_id;
  const [allows, setAllows] = useState<SalaryAllowance[] | null>(null);
  const [advs, setAdvs] = useState<SalaryAdvance[] | null>(null);
  const [rep, setRep] = useState<WorkerReport | null | "err">(null);
  const [att, setAtt] = useState<AttendanceDay[] | null>(null);
  const [spView, setSpView] = useState<"sp" | "ngay">("sp");   // lương SP: gộp theo mã SP hay theo ngày

  useEffect(() => {
    setAllows(null); setAdvs(null); setAtt(null);
    listPayrollAllowances(ym, wid).then(setAllows).catch(() => setAllows([]));
    listPayrollAdvances(ym, wid).then(setAdvs).catch(() => setAdvs([]));
    getAttendanceSummary(ym).then((s) => setAtt(s.days)).catch(() => setAtt([]));
  }, [ym, wid]);
  useEffect(() => {
    if (isTime) { setRep(null); return; }
    setRep(null);
    getWorkerReport(r.name, monthFrom(ym), monthTo(ym)).then(setRep).catch(() => setRep("err"));
  }, [ym, r.name, isTime]);

  // Thanh tỉ lệ: phần CỘNG (lương + phụ cấp + thưởng) so với phần TRỪ (ứng)
  const cong = r.luong + r.phu_cap + r.thuong;
  const tong = cong + r.ung;
  const pct = (v: number) => (tong > 0 ? Math.max(v > 0 ? 2 : 0, Math.round((v / tong) * 100)) : 0);
  const ungPct = cong > 0 ? Math.round((r.ung / cong) * 100) : 0;

  const sp = byProduct(rep === "err" ? null : rep);
  const days = byDay(rep === "err" ? null : rep);
  // Chấm công tháng của thợ + tra theo ngày (ghép vào bảng lương SP theo ngày)
  const attList = attRows(att, wid);
  const attTot = attTotals(attList);
  const attByDay = new Map(attList.map((a) => [a.day, a]));
  // MỌI ngày trong tháng có phát sinh: có báo cáo SX HOẶC có chấm công
  const dayKeys = [...new Set([...days.map((d) => d.ymd), ...attList.map((a) => a.day)])].sort();
  const spCay = sp.reduce((s, i) => s + i.cay, 0);
  const spPhieu = new Set(sp.flatMap((i) => [...i.phieu])).size;

  return (
    <>
      {/* ── Thực lãnh + cấu thành ─────────────────────────────────────────── */}
      <div class="pws-hero">
        <span class="muted small">Thực lãnh {ymLabel(ym).toLowerCase()}</span>
        <b class={r.thuc_lanh < 0 ? "t-danger" : ""}>{money(r.thuc_lanh)}đ</b>
        <div class="pws-formula muted small">
          {money(r.luong)}
          {r.phu_cap ? <> + {money(r.phu_cap)}</> : null}
          {r.thuong ? <> + {money(r.thuong)}</> : null}
          {r.ung ? <> − <span class="t-danger">{money(r.ung)}</span></> : null}
        </div>
      </div>
      {tong > 0 && (
        <>
          <div class="pws-bar" aria-hidden="true">
            <span class="pws-seg luong" style={`width:${pct(r.luong)}%`} />
            {r.phu_cap ? <span class="pws-seg pc" style={`width:${pct(r.phu_cap)}%`} /> : null}
            {r.thuong ? <span class="pws-seg thuong" style={`width:${pct(r.thuong)}%`} /> : null}
            {r.ung ? <span class="pws-seg ung" style={`width:${pct(r.ung)}%`} /> : null}
          </div>
          <div class="pws-legend muted small">
            <span><i class="pws-dot luong" /> Lương</span>
            {r.phu_cap ? <span><i class="pws-dot pc" /> Phụ cấp</span> : null}
            {r.thuong ? <span><i class="pws-dot thuong" /> Thưởng</span> : null}
            {r.ung ? <span><i class="pws-dot ung" /> Đã ứng{ungPct ? ` ${ungPct}%` : ""}</span> : null}
          </div>
        </>
      )}
      {r.thuc_lanh < 0 ? (
        <p class="pws-warn small">⚠ Ứng đã vượt lương tháng {money(-r.thuc_lanh)}đ — tháng sau trừ tiếp hoặc thu lại.</p>
      ) : null}

      {/* ── Lương ────────────────────────────────────────────────────────── */}
      <Block label="Lương" total={`${money(r.luong)}đ`} onTap={() => onCol("luong")}
        sub={isTime ? "theo công + tăng ca" : `sản phẩm${spPhieu ? ` · ${spPhieu} phiếu` : ""}`} />
      {isTime ? (
        <div class="pws-list">
          {/* Mốc lưu theo TỪNG THÁNG → nói rõ số này của tháng nào; bấm mở tab Mốc
              (sửa mốc + trao đổi về mốc lương của thợ, dùng chung mọi tháng). */}
          <button class="pws-item tappable" onClick={() => onCol("moc")}>
            <span>Mốc lương {ymLabel(ym).toLowerCase()} <span class="muted small">· {mocNguon(r, ym)}</span></span>
            <b>{r.monthly_salary ? `${money(r.monthly_salary)}đ` : "chưa đặt — bấm đặt"}</b>
          </button>
          <button class="pws-item tappable" onClick={() => onCol("luong_cong")}>
            <span>{congVN(r.cong)} công {r.monthly_salary
              ? <>× {money(r.monthly_salary / 26)}đ</>
              : <span class="t-warn">· chưa đặt mốc nên chưa tính được</span>}</span>
            <b>{money(r.luong_cong)}đ</b>
          </button>
          <button class="pws-item tappable" onClick={() => onCol("luong_tc")}>
            <span>Tăng ca {congVN(r.ot_gio)} giờ (×1,2)</span>
            <b>{r.luong_tc ? `${money(r.luong_tc)}đ` : "—"}</b>
          </button>
        </div>
      ) : rep === null ? (
        <p class="muted small pws-pad"><LoadingInline label="Đang tính lương sản phẩm…" /></p>
      ) : rep === "err" || !sp.length ? (
        <p class="muted small pws-pad">Tháng này chưa có báo cáo sản xuất nào của {r.name}.</p>
      ) : (
        <>
          <div class="seg pws-seg-view" role="group" aria-label="Cách xem lương sản phẩm">
            <button class={spView === "sp" ? "seg-btn active" : "seg-btn"} onClick={() => setSpView("sp")}>Theo sản phẩm</button>
            <button class={spView === "ngay" ? "seg-btn active" : "seg-btn"} onClick={() => setSpView("ngay")}>Theo ngày</button>
          </div>
          <div class="pws-list">
            {spView === "sp" ? sp.map((it) => (
              <a class="pws-item tappable" key={it.code} href={`#/kho/${encodeURIComponent(it.code)}`}>
                <span><b class="pws-day">{it.code}</b> <span class="muted small">· {cayVN(it.cay)} cây · {it.phieu.size} phiếu</span></span>
                <b>{money(it.money)}đ</b>
              </a>
            )) : dayKeys.map((ymd) => {
              // Ngày = báo cáo SX (nếu có) + CHẤM CÔNG (nếu có) → thấy ngay hôm đi làm
              // mà không có báo cáo, hoặc có báo cáo mà quên chấm công.
              const d = days.find((x) => x.ymd === ymd);
              const a = attByDay.get(ymd);
              // 1 phiếu trong ngày → bấm mở thẳng phiếu SX đó; nhiều phiếu thì để trơn
              const one = d && d.phieu.size === 1 ? [...d.phieu][0] : 0;
              const inner = (
                <>
                  <span>
                    <b class="pws-day">{dmy(ymd)}</b>{" "}
                    {d ? <span class="muted small">{[...d.codes].join(", ") || "—"} · {cayVN(d.cay)} cây
                      {d.phieu.size > 1 ? ` · ${d.phieu.size} phiếu` : ""}</span>
                      : <span class="muted small t-warn">chưa có báo cáo SX</span>}
                    <div class="muted small pws-att">
                      {a ? <><span class="wa-pair">⏱ {congVN(a.cong)} công</span>
                        {a.ot ? <span class="wa-pair t-warn">TC {otVN(a.ot)}g</span> : null}
                        {/* giờ ghép CẶP vào–ra cho gọn, giống dòng chấm công; các cụm
                            cách nhau bằng gap (không dùng dấu · để khỏi lơ lửng đầu dòng) */}
                        {pairs(a.times || []).map(([x, y], i) => (
                          <span class="wa-pair" key={i}>{x}<span class="wa-dash">–</span>
                            {y || <b class="t-danger">?</b>}</span>
                        ))}</>
                        : <span class="t-warn">⏱ không chấm công</span>}
                    </div>
                  </span>
                  <b class={d ? "" : "muted"}>{d ? `${money(d.money)}đ` : "—"}</b>
                </>
              );
              return one
                ? <a class="pws-item tappable" key={ymd} href={`#/san_xuat/${one}`}>{inner}</a>
                : <div class="pws-item" key={ymd}>{inner}</div>;
            })}
            <div class="pws-item pws-sum">
              <span>{spView === "sp" ? `Tổng ${cayVN(spCay)} cây`
                : `${days.length} ngày SX · ${cayVN(spCay)} cây · ${congVN(attTot.cong)} công`}</span>
              <b>{money(r.luong)}đ</b>
            </div>
          </div>
        </>
      )}

      {/* ── Chấm công (LUÔN hiện, mọi loại lương) ────────────────────────── */}
      <a class="pws-block tappable" href={`#/cham-cong/${wid}?ym=${encodeURIComponent(ym)}`}>
        <span class="pws-block-l">
          <b>Chấm công</b>
          <span class="muted small">
            {att === null ? "đang tải…"
              : attTot.ngay ? `${attTot.ngay} ngày có chấm${attTot.le ? ` · ${attTot.le} ngày lẻ giờ` : ""} · bấm để sửa giờ`
              : "tháng này chưa có giờ chấm"}
          </span>
        </span>
        <b>{congVN(attTot.cong)} công{attTot.ot ? <span class="t-warn"> · {congVN(attTot.ot)}g TC</span> : null}</b>
        <Icon name="chevronRight" size={15} />
      </a>
      {att === null ? <p class="muted small pws-pad"><LoadingInline label="Đang tải chấm công…" /></p>
        : !attList.length ? <p class="muted small pws-pad">Chưa có ngày nào chấm giờ trong tháng.</p>
        : <div class="pws-list wa-list pws-att-list"><AttendanceDayRows rows={attList} /></div>}

      {/* ── Phụ cấp ──────────────────────────────────────────────────────── */}
      <Block label="Phụ cấp" total={`+${money(r.phu_cap)}đ`} tone={r.phu_cap ? "ok" : undefined}
        sub={r.pc_count ? `${r.pc_count} khoản · bấm để thêm/sửa` : "bấm để thêm"} onTap={() => onCol("pc")} />
      {allows === null ? <p class="muted small pws-pad"><LoadingInline label="Đang tải…" /></p>
        : !allows.length ? <p class="muted small pws-pad">Chưa có khoản phụ cấp nào.</p>
        : (
          <div class="pws-list">
            {allows.map((a) => (
              <div class={`pws-item${a.voided_at ? " ua-voided" : ""}`} key={a.id}>
                <span>{a.note || <i class="muted">không ghi nội dung</i>}
                  {a.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}</span>
                <b class={a.voided_at ? "ua-amt-voided" : ""}>{money(a.amount)}đ</b>
              </div>
            ))}
          </div>
        )}

      {/* ── Ứng lương ────────────────────────────────────────────────────── */}
      <Block label="Đã ứng" total={`−${money(r.ung)}đ`} tone={r.ung ? "danger" : undefined}
        sub={r.adv_count ? `${r.adv_count} lần nhập tay · bấm để thêm/sửa` : "bấm để thêm"} onTap={() => onCol("ung")} />
      {advs === null ? <p class="muted small pws-pad"><LoadingInline label="Đang tải…" /></p>
        : !advs.length && !r.ung_weekly ? <p class="muted small pws-pad">Chưa ứng lần nào trong tháng.</p>
        : (
          <div class="pws-list">
            {r.ung_weekly > 0 ? (
              <div class="pws-item">
                <span>Lương tuần <span class="muted small">· tự động = lương SP đã trả theo tuần</span></span>
                <b>{money(r.ung_weekly)}đ</b>
              </div>
            ) : null}
            {advs.map((a) => (
              <div class={`pws-item${a.voided_at ? " ua-voided" : ""}`} key={a.id}>
                <span>{dmy(a.adv_date)} {a.note ? <span class="muted small">· {a.note}</span> : null}
                  {a.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}</span>
                <b class={a.voided_at ? "ua-amt-voided" : ""}>{money(a.amount)}đ</b>
              </div>
            ))}
          </div>
        )}

      {r.thuong ? <Block label="Thưởng (tháng cũ)" total={`+${money(r.thuong)}đ`} tone="ok" /> : null}
      {r.note ? <p class="muted small pws-pad">Ghi chú tháng: {r.note}</p> : null}

      {/* ── Cài đặt + lối đi tiếp ────────────────────────────────────────── */}
      <div class="pws-tools">
        <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
          title="Bấm để đổi loại lương">{isTime ? "Lương thời gian" : "Lương sản phẩm"}</button>
        <label class="pr-weekly-control">
          <span>Nhận lương tuần</span>
          <span class={r.weekly ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly}
            onClick={() => toggleWeekly(r)}><span class="tgl-knob" /></span>
        </label>
      </div>
      <div class="pws-links">
        <a class="btn" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>🏭 Chi tiết sản xuất</a>
        <a class="btn" href={`#/cham-cong/${wid}?ym=${encodeURIComponent(ym)}`}>🕐 Chấm công</a>
        <a class="btn" href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>💵 Nhập phụ cấp</a>
        <a class="btn" href={`#/nhap-ung?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>📋 Nhập ứng</a>
      </div>
    </>
  );
}
