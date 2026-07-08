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

type Ym = { y: number; m: number };
const addMonths = ({ y, m }: Ym, dm: number): Ym => {
  const t = new Date(y, m + dm, 1);
  return { y: t.getFullYear(), m: t.getMonth() };
};
const ymLte = (a: Ym, b: Ym) => a.y < b.y || (a.y === b.y && a.m <= b.m);
/** Liệt kê tháng từ `from` tới `to` (CŨ → MỚI, kể cả tháng KHÔNG có dữ liệu). */
function enumerate(from: Ym, to: Ym): Ym[] {
  const out: Ym[] = [];
  let cur = from;
  for (let i = 0; i < 600 && ymLte(cur, to); i++) {   // trần 50 năm
    out.push(cur);
    cur = addMonths(cur, 1);
  }
  return out;
}

export function ScrollCalendar({ days, legend, onPick }: {
  days: CalDays;
  legend: { o: string; p: string };   // nhãn chú giải chấm đỏ / chấm xanh
  onPick: (day: string) => void;
}) {
  const now = new Date();
  // LAZY VÔ HẠN 2 CHIỀU: cửa sổ [from..to] mở rộng mãi — hiện CẢ tháng trống
  // (quá khứ lẫn tương lai), không phụ thuộc dữ liệu.
  const curYm: Ym = { y: now.getFullYear(), m: now.getMonth() };
  const [win, setWin] = useState<{ from: Ym; to: Ym }>({ from: addMonths(curYm, -3), to: curYm });
  const topRef = useRef<HTMLDivElement>(null);
  const botRef = useRef<HTMLDivElement>(null);

  // mở tại ĐÁY (tháng hiện tại) — cuộn LÊN là về quá khứ
  useEffect(() => {
    requestAnimationFrame(() =>
      window.scrollTo(0, document.documentElement.scrollHeight));
  }, []);
  // dữ liệu có tháng TƯƠNG LAI (vd ngày giao đặt trước) → nới cửa sổ tới đó
  useEffect(() => {
    let latest = curYm;
    for (const k of days.keys()) {
      const ym: Ym = { y: Number(k.slice(0, 4)), m: Number(k.slice(5, 7)) - 1 };
      if (!ymLte(ym, latest)) latest = ym;
    }
    if (!ymLte(latest, win.to)) setWin((w) => ({ ...w, to: latest }));
  }, [days]);

  useEffect(() => {
    const io = new IntersectionObserver((ents) => {
      for (const en of ents) {
        if (!en.isIntersecting) continue;
        if (en.target === topRef.current) {
          const before = document.documentElement.scrollHeight;
          setWin((w) => ({ ...w, from: addMonths(w.from, -4) }));
          requestAnimationFrame(() =>
            window.scrollBy(0, document.documentElement.scrollHeight - before));
        } else if (en.target === botRef.current) {
          setWin((w) => ({ ...w, to: addMonths(w.to, 4) }));
        }
      }
    }, { rootMargin: "200px 0px" });
    if (topRef.current) io.observe(topRef.current);
    if (botRef.current) io.observe(botRef.current);
    return () => io.disconnect();
  }, [win.from.y, win.from.m, win.to.y, win.to.m]);

  const todayKey = keyOf(now.getFullYear(), now.getMonth(), now.getDate());
  return (
    <div class="cust-cal">
      <div ref={topRef} style="height:1px" />
      {enumerate(win.from, win.to).map(({ y, m }) => (
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
