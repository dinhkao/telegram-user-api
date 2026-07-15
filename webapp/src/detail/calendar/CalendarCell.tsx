import { dateKey } from "./calendarDates";
import { lunarDateLabel } from "./lunarDate";
import type { CalDays } from "./types";

const MAX_DOTS = 4;
const MAX_LINES = 7;

function activityText(o: number, p: number, legend: { o: string; p: string }) {
  return `${o ? `${o} ${legend.o}` : ""}${o && p ? " · " : ""}${p ? `${p} ${legend.p}` : ""}`;
}

export function CalendarCell({ date, days, legend, activeYm, todayKey, onPick }: {
  date: Date;
  days: CalDays;
  legend: { o: string; p: string };
  activeYm: string;
  todayKey: string;
  onPick: (day: string) => void;
}) {
  const key = dateKey(date);
  const ym = key.slice(0, 7);
  const counts = days.get(key);
  const has = !!counts && (counts.o > 0 || counts.p > 0);
  const red = has ? Math.min(counts.o, MAX_DOTS) : 0;
  const green = has ? Math.min(counts.p, MAX_DOTS) : 0;
  const extra = has ? counts.o + counts.p - red - green : 0;
  const first = date.getDate() === 1;
  const lunar = lunarDateLabel(date);
  const activity = has ? activityText(counts.o, counts.p, legend) : "";
  const title = [lunar?.full, activity].filter(Boolean).join(" · ");

  return (
    <button key={key}
      class={"cc-cell cont" + (has ? " has" : "") + (key === todayKey ? " today" : "") + (ym !== activeYm ? " dim" : "")}
      data-fom={first ? ym : undefined}
      disabled={!has}
      onClick={() => onPick(key)}
      title={title}
      aria-label={`Dương lịch: ${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}. ${title}`}>
      {first && <span class="cc-mlabel">Th{date.getMonth() + 1}</span>}
      <span class="cc-d">{date.getDate()}</span>
      {lunar && <span class={"cc-lunar" + (lunar.day === 1 ? " new-month" : "")}>Â {lunar.short}</span>}
      {has && counts.items ? (
        <span class="cc-lines">
          {counts.items.slice(0, MAX_LINES).map((item, index) => (
            <span key={index} class={"cc-line" + (item.done ? " dn" : " pend")}>{item.t}</span>
          ))}
          {counts.items.length > MAX_LINES && <span class="cc-line more">+{counts.items.length - MAX_LINES}</span>}
        </span>
      ) : has ? (
        <span class="cc-dots">
          {Array.from({ length: red }, (_, index) => <span key={`o${index}`} class="cc-dot o" />)}
          {Array.from({ length: green }, (_, index) => <span key={`p${index}`} class="cc-dot p" />)}
          {extra > 0 && <span class="cc-more">+{extra}</span>}
        </span>
      ) : null}
    </button>
  );
}
