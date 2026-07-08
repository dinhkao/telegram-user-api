// Lịch tháng CUỘN DỌC dùng chung (lịch khách #/khach/:key/lich + lịch giao #/lich):
// tháng xếp CŨ→MỚI (đúng chiều thời gian), mở sẵn Ở ĐÁY (tháng hiện tại), cuộn
// LÊN là về quá khứ; LAZY 2 CHIỀU (cửa sổ 4 tháng, sentinel trên prepend + BÙ
// scroll, sentinel dưới nới về phía mới). Ngày có biến động: chấm ĐỎ (o) / XANH
// (p) theo ĐÚNG SỐ LƯỢNG. Bấm ngày → onPick (parent lo popup).
import { useEffect, useRef, useState } from "preact/hooks";

const _WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const _MONTH = (y: number, m: number) => `Tháng ${m + 1}/${y}`;
const pad = (n: number) => String(n).padStart(2, "0");
const keyOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

export type CalDays = Map<string, { o: number; p: number }>;

/** Các ô của 1 tháng (Thứ 2 đầu tuần): null = ô trống đầu/cuối lưới. */
function monthCells(y: number, m: number): (number | null)[] {
  const first = new Date(y, m, 1);
  const lead = (first.getDay() + 6) % 7;   // CN=0 → 6; T2=1 → 0
  const days = new Date(y, m + 1, 0).getDate();
  const cells: (number | null)[] = Array(lead).fill(null);
  for (let d = 1; d <= days; d++) cells.push(d);
  while (cells.length % 7) cells.push(null);
  return cells;
}

/** Dãy tháng (CŨ → MỚI): từ tháng có biến động sớm nhất tới MAX(tháng hiện tại,
 *  tháng có dữ liệu muộn nhất) — lịch giao có ngày giao TƯƠNG LAI vẫn hiện. */
function monthRange(days: CalDays, now: Date): { y: number; m: number }[] {
  const cur = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
  let earliest = cur, latest = cur;
  for (const k of days.keys()) {
    const ym = k.slice(0, 7);
    if (ym < earliest) earliest = ym;
    if (ym > latest) latest = ym;
  }
  const out: { y: number; m: number }[] = [];
  let y = Number(latest.slice(0, 4)), m = Number(latest.slice(5, 7)) - 1;
  for (let i = 0; i < 120; i++) {   // trần 10 năm — chống dữ liệu hỏng
    out.push({ y, m });
    if (`${y}-${pad(m + 1)}` <= earliest) break;
    m -= 1;
    if (m < 0) { m = 11; y -= 1; }
  }
  return out.reverse();
}

export function ScrollCalendar({ days, legend, onPick }: {
  days: CalDays;
  legend: { o: string; p: string };   // nhãn chú giải chấm đỏ / chấm xanh
  onPick: (day: string) => void;
}) {
  const now = new Date();
  // LAZY 2 CHIỀU: chỉ render cửa sổ [start..end]; sentinel trên/dưới nới dần
  const [win, setWin] = useState<{ start: number; end: number } | null>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const botRef = useRef<HTMLDivElement>(null);
  const monthsAll = monthRange(days, now);

  // days đổi (nạp xong / realtime) → init cửa sổ 4 tháng cuối + cuộn xuống ĐÁY
  const inited = useRef(false);
  useEffect(() => {
    if (!days.size || inited.current) return;
    inited.current = true;
    const n = monthRange(days, new Date()).length;
    setWin({ start: Math.max(0, n - 4), end: n - 1 });
    requestAnimationFrame(() =>
      window.scrollTo(0, document.documentElement.scrollHeight));
  }, [days]);

  useEffect(() => {
    if (!win) return;
    const io = new IntersectionObserver((ents) => {
      for (const en of ents) {
        if (!en.isIntersecting) continue;
        if (en.target === topRef.current && win.start > 0) {
          const before = document.documentElement.scrollHeight;
          setWin((w) => w && ({ ...w, start: Math.max(0, w.start - 4) }));
          requestAnimationFrame(() =>
            window.scrollBy(0, document.documentElement.scrollHeight - before));
        } else if (en.target === botRef.current && win.end < monthsAll.length - 1) {
          setWin((w) => w && ({ ...w, end: Math.min(monthsAll.length - 1, w.end + 4) }));
        }
      }
    }, { rootMargin: "300px 0px" });
    if (topRef.current) io.observe(topRef.current);
    if (botRef.current) io.observe(botRef.current);
    return () => io.disconnect();
  }, [win?.start, win?.end, monthsAll.length]);

  const todayKey = keyOf(now.getFullYear(), now.getMonth(), now.getDate());
  return (
    <div class="cust-cal">
      <div ref={topRef} style="height:1px" />
      {(win ? monthsAll.slice(win.start, win.end + 1) : []).map(({ y, m }) => (
        <div class="cc-block" key={`${y}-${m}`}>
          <div class="cc-month-head"><b class="cc-month">{_MONTH(y, m)}</b></div>
          <div class="cc-grid cc-head">
            {_WD.map((w) => <span key={w} class="cc-wd">{w}</span>)}
          </div>
          <div class="cc-grid">
            {monthCells(y, m).map((d, i) => {
              if (d == null) return <span key={`e${i}`} class="cc-cell empty" />;
              const k = keyOf(y, m, d);
              const c = days.get(k);
              const has = !!c && (c.o > 0 || c.p > 0);
              // CAP chấm hiển thị (ngày quá nhiều biến động làm ô phình vỡ lưới):
              // tối đa 4 đỏ + 4 xanh, phần dư gộp thành "+n"
              const oShow = has ? Math.min(c!.o, 4) : 0;
              const pShow = has ? Math.min(c!.p, 4) : 0;
              const extra = has ? c!.o + c!.p - oShow - pShow : 0;
              return (
                <button key={k} class={"cc-cell" + (has ? " has" : "") + (k === todayKey ? " today" : "")}
                  disabled={!has} onClick={() => onPick(k)}
                  title={has ? `${c!.o ? `${c!.o} ${legend.o}` : ""}${c!.o && c!.p ? " · " : ""}${c!.p ? `${c!.p} ${legend.p}` : ""}` : undefined}>
                  <span class="cc-d">{d}</span>
                  {has && (
                    <span class="cc-dots">
                      {Array.from({ length: oShow }, (_, j) => <span key={`o${j}`} class="cc-dot o" />)}
                      {Array.from({ length: pShow }, (_, j) => <span key={`p${j}`} class="cc-dot p" />)}
                      {extra > 0 && <span class="cc-more">+{extra}</span>}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <div ref={botRef} style="height:1px" />
      <div class="cc-legend muted small">
        <span><span class="cc-dot o" /> {legend.o}</span>
        <span><span class="cc-dot p" /> {legend.p}</span>
      </div>
    </div>
  );
}
