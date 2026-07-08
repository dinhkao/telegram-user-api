// Lịch CUỘN LIỀN MẠCH kiểu macOS (dùng chung: lịch khách + lịch giao #/lich):
// KHÔNG header tháng — mọi ngày nối nhau thành 1 lưới tuần liên tục, CŨ trên →
// MỚI dưới, mở tại tháng hiện tại, LAZY VÔ HẠN 2 CHIỀU (kể cả tháng trống).
// Lướt tới tháng nào → ngày tháng đó NỔI BẬT (tháng khác mờ đi, transition êm),
// indicator "Tháng N/YYYY" dính trên đầu đổi theo (animation trượt); ô ngày 1
// có nhãn tháng nhỏ để định vị. Chấm ĐỎ (o) / XANH (p) đúng số lượng (cap 4+4
// + "+n"). Bấm ngày → onPick (parent lo popup).
import { useEffect, useRef, useState } from "preact/hooks";

const _WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const pad = (n: number) => String(n).padStart(2, "0");

export type CalDays = Map<string, { o: number; p: number }>;

type Ym = { y: number; m: number };
const addMonths = ({ y, m }: Ym, dm: number): Ym => {
  const t = new Date(y, m + dm, 1);
  return { y: t.getFullYear(), m: t.getMonth() };
};
const ymLte = (a: Ym, b: Ym) => a.y < b.y || (a.y === b.y && a.m <= b.m);
const ymStr = ({ y, m }: Ym) => `${y}-${pad(m + 1)}`;

/** Dãy NGÀY liền mạch: từ Thứ 2 đầu tuần chứa 1/from → CN cuối tuần chứa ngày
 *  cuối của to — lưới tuần nối nhau xuyên tháng, không ô trống giữa chừng. */
function contDays(from: Ym, to: Ym): Date[] {
  const start = new Date(from.y, from.m, 1);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));   // lùi về Thứ 2
  const end = new Date(to.y, to.m + 1, 0);
  end.setDate(end.getDate() + (7 - 1 - ((end.getDay() + 6) % 7)));   // tiến tới CN
  const out: Date[] = [];
  for (let t = new Date(start); t <= end && out.length < 20000; t.setDate(t.getDate() + 1))
    out.push(new Date(t));
  return out;
}

export function ScrollCalendar({ days, legend, onPick }: {
  days: CalDays;
  legend: { o: string; p: string };   // nhãn chú giải chấm đỏ / chấm xanh
  onPick: (day: string) => void;
}) {
  const now = new Date();
  const curYm: Ym = { y: now.getFullYear(), m: now.getMonth() };
  // LAZY VÔ HẠN 2 CHIỀU — hiện CẢ tháng trống, không phụ thuộc dữ liệu
  const [win, setWin] = useState<{ from: Ym; to: Ym }>({ from: addMonths(curYm, -3), to: curYm });
  const topRef = useRef<HTMLDivElement>(null);
  const botRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  // mở tại ĐÁY (tháng hiện tại) — cuộn LÊN là về quá khứ
  useEffect(() => {
    requestAnimationFrame(() =>
      window.scrollTo(0, document.documentElement.scrollHeight));
  }, []);
  // dữ liệu có tháng TƯƠNG LAI (ngày giao đặt trước) → nới cửa sổ tới đó
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

  // ── THÁNG ACTIVE theo vị trí cuộn (kiểu macOS): mốc = ô NGÀY 1 mỗi tháng;
  // tháng active = mốc CUỐI CÙNG đã vượt lên trên ~45% màn hình ──
  const [activeYm, setActiveYm] = useState(ymStr(curYm));
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const marks = gridRef.current?.querySelectorAll<HTMLElement>("[data-fom]");
        if (!marks || !marks.length) return;
        const mid = window.innerHeight * 0.45;
        let act: string | null = null;
        marks.forEach((el) => {
          if (el.getBoundingClientRect().top <= mid) act = el.getAttribute("data-fom");
        });
        if (act) setActiveYm((prev) => (prev === act ? prev : act!));
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); };
  }, [win.from.y, win.from.m, win.to.y, win.to.m]);

  const todayKey = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const [aY, aM] = activeYm.split("-").map(Number);

  return (
    <div class="cust-cal cc-cont">
      {/* indicator tháng + hàng thứ — DÍNH trên đầu; đổi tháng → animation trượt */}
      <div class="cc-cont-head">
        <b class="cc-mind" key={activeYm}>Tháng {aM}/{aY}</b>
        <div class="cc-grid cc-head">
          {_WD.map((w) => <span key={w} class="cc-wd">{w}</span>)}
        </div>
      </div>

      <div ref={topRef} style="height:1px" />
      <div class="cc-grid cc-cont-grid" ref={gridRef}>
        {contDays(win.from, win.to).map((t) => {
          const k = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`;
          const ym = k.slice(0, 7);
          const c = days.get(k);
          const has = !!c && (c.o > 0 || c.p > 0);
          // cap chấm: tối đa 4 đỏ + 4 xanh, dư gộp "+n" (ngày quá bận không phình ô)
          const oShow = has ? Math.min(c!.o, 4) : 0;
          const pShow = has ? Math.min(c!.p, 4) : 0;
          const extra = has ? c!.o + c!.p - oShow - pShow : 0;
          const first = t.getDate() === 1;
          return (
            <button key={k}
              class={"cc-cell cont" + (has ? " has" : "") + (k === todayKey ? " today" : "") + (ym !== activeYm ? " dim" : "")}
              data-fom={first ? ym : undefined}
              disabled={!has} onClick={() => onPick(k)}
              title={has ? `${c!.o ? `${c!.o} ${legend.o}` : ""}${c!.o && c!.p ? " · " : ""}${c!.p ? `${c!.p} ${legend.p}` : ""}` : undefined}>
              {first && <span class="cc-mlabel">Th{t.getMonth() + 1}</span>}
              <span class="cc-d">{t.getDate()}</span>
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
      <div ref={botRef} style="height:1px" />
      <div class="cc-legend muted small">
        <span><span class="cc-dot o" /> {legend.o}</span>
        <span><span class="cc-dot p" /> {legend.p}</span>
      </div>
    </div>
  );
}
