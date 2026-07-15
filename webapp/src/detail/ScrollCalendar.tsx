// Lịch cuộn liền mạch dùng chung cho lịch giao, lịch việc và lịch khách.
import type { ComponentChildren } from "preact";
import { useRef } from "preact/hooks";
import { CalendarCell } from "./calendar/CalendarCell";
import { CalendarHeader } from "./calendar/CalendarHeader";
import { continuousDays, dateKey } from "./calendar/calendarDates";
import { useActiveMonth } from "./calendar/useActiveMonth";
import { useCalendarWindow } from "./calendar/useCalendarWindow";
import type { CalDays, Ym } from "./calendar/types";
import "./calendar/calendar.css";

export type { CalDays } from "./calendar/types";

export function ScrollCalendar({ days, legend, onPick, headExtra }: {
  days: CalDays;
  legend: { o: string; p: string };
  onPick: (day: string) => void;
  headExtra?: ComponentChildren;
}) {
  const now = new Date();
  const current: Ym = { y: now.getFullYear(), m: now.getMonth() };
  const top = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  const flying = useRef(false);
  const range = useCalendarWindow(days, current, { top, bottom, grid, flying });
  const { activeYm, goToday } = useActiveMonth(grid, flying, current, range);
  const todayKey = dateKey(now);

  return (
    <div class="cust-cal cc-cont">
      <CalendarHeader activeYm={activeYm} currentYm={current} headExtra={headExtra} onToday={goToday} />
      <div ref={top} style="height:1px" />
      <div class="cc-grid cc-cont-grid" ref={grid}>
        {continuousDays(range.from, range.to).map((date) => (
          <CalendarCell key={dateKey(date)} date={date} days={days} legend={legend}
            activeYm={activeYm} todayKey={todayKey} onPick={onPick} />
        ))}
      </div>
      <div ref={bottom} style="height:1px" />
      <div class="cc-legend muted small">
        <span><span class="cc-dot o" /> {legend.o}</span>
        <span><span class="cc-dot p" /> {legend.p}</span>
        <span class="cc-lunar-key">Â = âm lịch</span>
      </div>
    </div>
  );
}
