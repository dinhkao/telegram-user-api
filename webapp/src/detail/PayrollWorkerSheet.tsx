// HỒ SƠ LƯƠNG THÁNG của 1 thợ — nội dung popup khi bấm Ô TÊN ở bảng lương (#/luong-thang).
// Gom MỌI khoản của tháng vào 1 màn: thực lãnh + thanh tỉ lệ (lương/phụ cấp/thưởng ↔ ứng),
// NGUỒN lương (thợ SP: CHI TIẾT từng phiếu SX của từng ngày · thợ TG: mốc → công → tăng ca),
// TỪNG khoản phụ cấp, TỪNG lần ứng (kèm lương tuần tự động), thưởng tháng cũ.
// CHỈ ĐỌC + điều hướng: mỗi khối bấm được để nhảy sang tab sửa tương ứng của popup
// (pc/ung/luong/cong/tc) — MỌI khối đều GẬP được (lương + chấm công mặc định ĐÓNG,
// các khối tiền ngắn mặc định MỞ). Cố tình KHÔNG dựng editor thứ 2 ở đây, thao tác thêm/vô
// hiệu/sửa ghi chú chỉ nằm ở EntryPanel (xem luật ĐỒNG BỘ 2 CHỖ trong PayrollCellPopup).
// 2 khối dài nhất — Lương và Chấm công — MẶC ĐỊNH GẬP, tiêu đề chỉ hiện TỔNG;
// bấm tiêu đề mới bung chi tiết ra (popup mở lên phải đọc được ngay con số).
// CHẤM CÔNG có cho MỌI thợ (không riêng thợ lương thời gian): khối "Chấm công"
// = tổng công/TC + từng ngày; thợ lương SP xem view "Theo ngày" thì mỗi ngày còn kèm
// công + giờ chấm của ngày đó (thấy ngay hôm nào đi làm mà không có báo cáo SX).
// Data: listPayrollAllowances + listPayrollAdvances + getWorkerReport (thợ lương SP)
// + getAttendanceSummary (chấm công tháng).
import { useEffect, useState } from "preact/hooks";
import {
  getAttendanceSummary, getWorkerReport, listPayrollAdvances, listPayrollAllowances,
  type AttendanceDay, type PayrollRow, type SalaryAdvance, type SalaryAllowance, type WorkerReport,
} from "../api";
import { moneyR as money, dmy, ymLabel } from "../format";
import { byDay, byDaySlip, cayVN, monthFrom, monthTo } from "./payrollWageRows";
import { bhxhNguon, mocNguon, type PayrollCol } from "./PayrollCellPopup";
import { isTimeWage, otInCong, wageLabel } from "./wageType";
import { AttendanceDayRows, attRows, attTotals, congVN, otVN, pairs } from "./AttendanceDays";
import { Icon } from "../ui/Icon";
import { LoadingInline } from "../ui/states";

/** Tiêu đề 1 khối: nhãn + tổng + chevron, bấm → mở tab sửa tương ứng.
 *  `open` khác undefined = khối GẬP ĐƯỢC: bấm tiêu đề để mở/gập, mũi tên đổi chiều.
 *  (Lương + Chấm công mặc định GẬP — mở popup ra chỉ cần thấy TỔNG TIỀN trước.) */
function Block({ label, sub, total, tone, onTap, open }: {
  label: string; sub?: any; total: string; tone?: "ok" | "danger";
  onTap?: () => void; open?: boolean;
}) {
  const fold = open !== undefined;
  return (
    <button class={`pws-block${onTap ? " tappable" : ""}`} disabled={!onTap} onClick={onTap}
      aria-expanded={fold ? open : undefined}>
      <span class="pws-block-l">
        <b>{label}</b>
        {sub ? <span class="muted small">{sub}</span> : null}
      </span>
      <b class={tone === "danger" ? "t-danger" : tone === "ok" ? "t-ok" : ""}>{total}</b>
      {fold ? <span class="pws-fold">{open ? "▾" : "▸"}</span>
        : onTap ? <Icon name="chevronRight" size={15} /> : null}
    </button>
  );
}

export function PayrollWorkerSheet({ ym, r, onCol, toggleType, toggleWeekly }: {
  ym: string; r: PayrollRow;
  onCol: (c: PayrollCol) => void;   // mở tab tương ứng của PayrollCellPopup (gồm "moc")
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
}) {
  const isTime = isTimeWage(r.wage_type);   // TG hoặc TG*
  const otCong = otInCong(r.wage_type);     // TG*: giờ TC gộp vào công, không trả riêng
  const wid = r.worker_id;
  const [allows, setAllows] = useState<SalaryAllowance[] | null>(null);
  const [advs, setAdvs] = useState<SalaryAdvance[] | null>(null);
  const [rep, setRep] = useState<WorkerReport | null | "err">(null);
  const [att, setAtt] = useState<AttendanceDay[] | null>(null);
  // MỌI khối đều gập được. 2 khối DÀI (lương, chấm công) mặc định ĐÓNG — mở popup ra
  // thấy ngay tổng tiền; các khối tiền ngắn (thưởng, phụ cấp, ứng, BHXH) mặc định MỞ
  // vì đó là thứ văn phòng hay sửa nhất (chốt 2026-08-05).
  const [open, setOpen] = useState<Record<string, boolean>>({
    luong: false, cham: false, thuong: true, pc: true, ung: true, bhxh: true,
  });
  const tog = (k: string) => setOpen((o) => ({ ...o, [k]: !o[k] }));
  const [spView, setSpView] = useState<"chitiet" | "ngay">("chitiet");   // lương SP: chi tiết từng phiếu hay gộp theo ngày

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

  // Thanh tỉ lệ: phần CỘNG (lương + phụ cấp + thưởng) so với phần TRỪ (ứng + BHXH)
  const cong = r.luong + r.phu_cap + r.thuong + r.thuong_cc + r.thuong_vs + r.cho_hang;
  const tong = cong + r.ung + r.bhxh;
  const pct = (v: number) => (tong > 0 ? Math.max(v > 0 ? 2 : 0, Math.round((v / tong) * 100)) : 0);
  const ungPct = cong > 0 ? Math.round((r.ung / cong) * 100) : 0;

  const detail = byDaySlip(rep === "err" ? null : rep);
  const days = byDay(rep === "err" ? null : rep);
  // Chấm công tháng của thợ + tra theo ngày (ghép vào bảng lương SP theo ngày)
  const attList = attRows(att, wid);
  const attTot = attTotals(attList);
  const attByDay = new Map(attList.map((a) => [a.day, a]));
  // MỌI ngày trong tháng có phát sinh: có báo cáo SX HOẶC có chấm công
  const dayKeys = [...new Set([...days.map((d) => d.ymd), ...attList.map((a) => a.day)])].sort();
  const spCay = detail.reduce((s, d) => s + d.cay, 0);
  const spPhieu = new Set(detail.flatMap((d) => d.slips.map((x) => x.tid))).size;

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
          {r.thuong_cc ? <> + {money(r.thuong_cc)} <span class="muted">ch.cần</span></> : null}
          {r.thuong_vs ? <> + {money(r.thuong_vs)} <span class="muted">vệ sinh</span></> : null}
          {r.cho_hang ? <> + {money(r.cho_hang)} <span class="muted">chờ hàng</span></> : null}
          {r.ung ? <> − <span class="t-danger">{money(r.ung)}</span></> : null}
          {r.bhxh ? <> − <span class="t-danger">{money(r.bhxh)}</span> <span class="muted">BHXH</span></> : null}
        </div>
      </div>
      {tong > 0 && (
        <>
          <div class="pws-bar" aria-hidden="true">
            <span class="pws-seg luong" style={`width:${pct(r.luong)}%`} />
            {r.phu_cap ? <span class="pws-seg pc" style={`width:${pct(r.phu_cap)}%`} /> : null}
            {r.thuong ? <span class="pws-seg thuong" style={`width:${pct(r.thuong)}%`} /> : null}
            {r.ung ? <span class="pws-seg ung" style={`width:${pct(r.ung)}%`} /> : null}
            {r.bhxh ? <span class="pws-seg bhxh" style={`width:${pct(r.bhxh)}%`} /> : null}
          </div>
          <div class="pws-legend muted small">
            <span><i class="pws-dot luong" /> Lương</span>
            {r.phu_cap ? <span><i class="pws-dot pc" /> Phụ cấp</span> : null}
            {r.thuong ? <span><i class="pws-dot thuong" /> Thưởng</span> : null}
            {r.ung ? <span><i class="pws-dot ung" /> Đã ứng{ungPct ? ` ${ungPct}%` : ""}</span> : null}
            {r.bhxh ? <span><i class="pws-dot bhxh" /> Trừ BHXH</span> : null}
          </div>
        </>
      )}
      {r.thuc_lanh < 0 ? (
        <p class="pws-warn small">⚠ Ứng đã vượt lương tháng {money(-r.thuc_lanh)}đ — tháng sau trừ tiếp hoặc thu lại.</p>
      ) : null}

      {/* ── Lương ────────────────────────────────────────────────────────── */}
      {/* thợ SP: nói rõ trong Lương đã có phụ cấp ghi ở phiếu SX (khác phụ cấp THÁNG) */}
      <Block label="Lương" total={`${money(r.luong)}đ`} open={open.luong}
        onTap={() => tog("luong")}
        sub={otCong ? "cố định theo ngày công (đã gộp tăng ca)"
          : isTime ? "theo công + tăng ca"
          : `sản phẩm${spPhieu ? ` · ${spPhieu} phiếu` : ""}${r.pc_phieu ? ` · gồm ${money(r.pc_phieu)}đ phụ cấp phiếu` : ""}`} />
      {!open.luong ? null : isTime ? (
        <div class="pws-list">
          {/* Mốc lưu theo TỪNG THÁNG → nói rõ số này của tháng nào; bấm mở tab Mốc
              (sửa mốc + trao đổi về mốc lương của thợ, dùng chung mọi tháng). */}
          <button class="pws-item tappable" onClick={() => onCol("moc")}>
            <span>Mốc lương {ymLabel(ym).toLowerCase()} <span class="muted small">· {mocNguon(r, ym)}</span></span>
            <b>{r.monthly_salary ? `${money(r.monthly_salary)}đ` : "chưa đặt — bấm đặt"}</b>
          </button>
          <button class="pws-item tappable" onClick={() => onCol("luong_cong")}>
            <span>{congVN(r.cong)} công{otCong && r.ot_gio ? ` (gồm ${congVN(r.ot_gio)}g TC)` : ""} {r.monthly_salary
              ? <>× {money(r.monthly_salary / 26)}đ</>
              : <span class="t-warn">· chưa đặt mốc nên chưa tính được</span>}</span>
            <b>{money(r.luong_cong)}đ</b>
          </button>
          {/* TG*: tăng ca đã nằm trong công ở trên → dòng này chỉ để nói rõ không trả riêng */}
          <button class="pws-item tappable" onClick={() => onCol("luong_tc")}>
            <span>{otCong ? `Tăng ca ${congVN(r.ot_gio)} giờ — đã gộp vào công` : `Tăng ca ${congVN(r.ot_gio)} giờ (×1,2)`}</span>
            <b>{otCong ? "—" : r.luong_tc ? `${money(r.luong_tc)}đ` : "—"}</b>
          </button>
        </div>
      ) : rep === null ? (
        <p class="muted small pws-pad"><LoadingInline label="Đang tính lương sản phẩm…" /></p>
      ) : rep === "err" || !detail.length ? (
        <p class="muted small pws-pad">Tháng này chưa có báo cáo sản xuất nào của {r.name}.</p>
      ) : (
        <>
          <div class="seg pws-seg-view" role="group" aria-label="Cách xem lương sản phẩm">
            <button class={spView === "chitiet" ? "seg-btn active" : "seg-btn"} onClick={() => setSpView("chitiet")}>Chi tiết</button>
            <button class={spView === "ngay" ? "seg-btn active" : "seg-btn"} onClick={() => setSpView("ngay")}>Theo ngày</button>
          </div>
          <div class="pws-list">
            {spView === "chitiet" ? detail.map((d) => (
              <>
                {/* mỗi NGÀY 1 dòng đậm, dưới là TỪNG PHIẾU SX của ngày đó + tiền phiếu */}
                <div class="pws-item pws-dayhead" key={d.ymd}>
                  <span><b class="pws-day">{dmy(d.ymd)}</b>
                    <span class="muted small"> · {d.slips.length} phiếu · {cayVN(d.cay)} cây</span></span>
                  <b>{money(d.money)}đ</b>
                </div>
                {d.slips.map((sl) => (
                  <a class="pws-item pws-subitem tappable" key={`${d.ymd}-${sl.tid}`} href={`#/san_xuat/${sl.tid}`}>
                    <span><b>{[...sl.codes].join(", ") || "—"}</b>
                      <span class="muted small"> · {cayVN(sl.cay)} cây</span></span>
                    <b>{money(sl.money)}đ</b>
                  </a>
                ))}
              </>
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
              <span>{spView === "chitiet" ? `${detail.length} ngày · ${spPhieu} phiếu · ${cayVN(spCay)} cây`
                : `${days.length} ngày SX · ${cayVN(spCay)} cây · ${congVN(attTot.cong)} công`}</span>
              <b>{money(r.luong)}đ</b>
            </div>
          </div>
        </>
      )}
      {open.luong ? (
        <button class="pws-item tappable pws-more" onClick={() => onCol(isTime ? "luong_cong" : "luong")}>
          <span class="muted small">Xem cách tính lương</span><b>›</b>
        </button>
      ) : null}

      {/* ── Chấm công (LUÔN hiện, mọi loại lương) ────────────────────────── */}
      <Block label="Chấm công" open={open.cham} onTap={() => tog("cham")}
        total={`${congVN(attTot.cong)} công${attTot.ot ? ` · ${congVN(attTot.ot)}g TC` : ""}`}
        sub={att === null ? "đang tải…"
          : attTot.ngay ? `${attTot.ngay} ngày có chấm${attTot.le ? ` · ${attTot.le} ngày lẻ giờ` : ""}`
          : "tháng này chưa có giờ chấm"} />
      {open.cham ? (
        att === null ? <p class="muted small pws-pad"><LoadingInline label="Đang tải chấm công…" /></p>
        : !attList.length ? <p class="muted small pws-pad">Chưa có ngày nào chấm giờ trong tháng.</p>
        : <>
            <div class="pws-list wa-list pws-att-list"><AttendanceDayRows rows={attList} /></div>
            <a class="pws-item tappable pws-more" href={`#/cham-cong/${wid}?ym=${encodeURIComponent(ym)}`}>
              <span class="muted small">Mở trang chấm công để sửa giờ</span><b>›</b>
            </a>
          </>
      ) : null}

      {/* ── Phụ cấp ──────────────────────────────────────────────────────── */}
      <Block label="Phụ cấp" total={`+${money(r.phu_cap)}đ`} tone={r.phu_cap ? "ok" : undefined}
        open={open.pc} onTap={() => tog("pc")}
        sub={r.pc_count ? `${r.pc_count} khoản` : "chưa có khoản nào"} />
      {!open.pc ? null
        : allows === null ? <p class="muted small pws-pad"><LoadingInline label="Đang tải…" /></p>
        : (
          <>
            {allows.length ? (
              <div class="pws-list">
                {allows.map((a) => (
                  <div class={`pws-item${a.voided_at ? " ua-voided" : ""}`} key={a.id}>
                    <span>{a.calc_label ? <b class="ua-calc">{a.calc_label}</b> : null}
                      {a.calc_label && a.note ? " · " : ""}
                      {a.note || (a.calc_label ? "" : <i class="muted">không ghi nội dung</i>)}
                      {a.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}</span>
                    <b class={a.voided_at ? "ua-amt-voided" : ""}>{money(a.amount)}đ</b>
                  </div>
                ))}
              </div>
            ) : <p class="muted small pws-pad">Chưa có khoản phụ cấp nào.</p>}
            <button class="pws-item tappable pws-more" onClick={() => onCol("pc")}>
              <span class="muted small">Thêm / sửa khoản phụ cấp</span><b>›</b>
            </button>
          </>
        )}

      {/* ── Ứng lương ────────────────────────────────────────────────────── */}
      <Block label="Đã ứng" total={`−${money(r.ung)}đ`} tone={r.ung ? "danger" : undefined}
        open={open.ung} onTap={() => tog("ung")}
        sub={r.adv_count ? `${r.adv_count} lần nhập tay` : "chưa ứng lần nào"} />
      {!open.ung ? null
        : advs === null ? <p class="muted small pws-pad"><LoadingInline label="Đang tải…" /></p>
        : !advs.length && !r.ung_weekly ? (
          <>
            <p class="muted small pws-pad">Chưa ứng lần nào trong tháng.</p>
            <button class="pws-item tappable pws-more" onClick={() => onCol("ung")}>
              <span class="muted small">Ghi ứng lương</span><b>›</b>
            </button>
          </>
        ) : (
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
            <button class="pws-item tappable pws-more" onClick={() => onCol("ung")}>
              <span class="muted small">Thêm / sửa lần ứng</span><b>›</b>
            </button>
          </div>
        )}

      {/* ── 2 khoản thưởng bật/tắt ───────────────────────────────────────── */}
      {/* Luôn hiện KỂ CẢ khi đang tắt hết — không thì không ai biết có 2 khoản này.
          Chỉ ăn tháng đang xem (không kế thừa); bật/tắt ở ô Ch.cần/Vệ sinh của bảng. */}
      <Block label="Thưởng" open={open.thuong} onTap={() => tog("thuong")}
        total={`+${money(r.thuong_cc + r.thuong_vs)}đ`} tone={r.thuong_cc + r.thuong_vs ? "ok" : undefined}
        sub={r.cc_on || r.vs_on
          ? [r.cc_on ? "chuyên cần" : "", r.vs_on ? "vệ sinh" : ""].filter(Boolean).join(" · ")
          : "chưa bật khoản nào"} />
      {open.thuong ? (
        <div class="pws-list">
          <div class="pws-item">
            <span>Chuyên cần <span class="muted small">· cố định</span></span>
            <b class={r.cc_on ? "t-ok" : "muted"}>{r.cc_on ? `+${money(r.thuong_cc)}đ` : "chưa bật"}</b>
          </div>
          <div class="pws-item">
            <span>Vệ sinh <span class="muted small">· {congVN(r.cong)} công</span></span>
            <b class={r.vs_on ? "t-ok" : "muted"}>{r.vs_on ? `+${money(r.thuong_vs)}đ` : "chưa bật"}</b>
          </div>
          <div class="pws-item"><span class="muted small">Bật/tắt ở ô Ch.cần và Vệ sinh trên bảng lương</span><b /></div>
        </div>
      ) : null}

      {/* ── Trừ BHXH ─────────────────────────────────────────────────────── */}
      {/* Mức lưu theo TỪNG THÁNG + kế thừa (bhxhNguon nói rõ số này của tháng nào) */}
      <Block label="Trừ BHXH" total={r.bhxh ? `−${money(r.bhxh)}đ` : "—"} tone={r.bhxh ? "danger" : undefined}
        open={open.bhxh} onTap={() => tog("bhxh")} sub={bhxhNguon(r, ym)} />
      {open.bhxh ? (
        <button class="pws-item tappable pws-more" onClick={() => onCol("bhxh")}>
          <span class="muted small">{r.bhxh ? "Sửa mức trừ" : "Đặt mức trừ"} · trao đổi về BHXH</span><b>›</b>
        </button>
      ) : null}

      {r.thuong ? <Block label="Thưởng (tháng cũ)" total={`+${money(r.thuong)}đ`} tone="ok" /> : null}
      {r.note ? <p class="muted small pws-pad">Ghi chú tháng: {r.note}</p> : null}

      {/* ── Cài đặt + lối đi tiếp ────────────────────────────────────────── */}
      <div class="pws-tools">
        <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
          title="Bấm để đổi loại lương (SP → TG → TG*)">Lương {wageLabel(r.wage_type).toLowerCase()}</button>
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
