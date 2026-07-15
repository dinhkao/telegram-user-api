import type { ComponentChildren } from "preact";
import { ymStr } from "./calendarDates";
import type { Ym } from "./types";

const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

export function CalendarHeader({ activeYm, currentYm, headExtra, onToday }: {
  activeYm: string;
  currentYm: Ym;
  headExtra?: ComponentChildren;
  onToday: () => void;
}) {
  const [year, month] = activeYm.split("-").map(Number);

  return (
    <div class="cc-cont-head">
      <div class="cc-mind-row">
        <b class="cc-mind" key={activeYm}>Tháng {month}/{year}</b>
        {headExtra}
        {activeYm !== ymStr(currentYm) && (
          <button class="btn small cc-today-btn" onClick={onToday}>Hôm nay</button>
        )}
      </div>
      <div class="cc-grid cc-head">
        {WEEKDAYS.map((weekday) => <span key={weekday} class="cc-wd">{weekday}</span>)}
      </div>
    </div>
  );
}
