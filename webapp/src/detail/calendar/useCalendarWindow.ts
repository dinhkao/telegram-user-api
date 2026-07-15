import { useEffect, useState } from "preact/hooks";
import { addMonths, ymLte } from "./calendarDates";
import type { CalDays, ElementRef, ValueRef, Ym } from "./types";

type CalendarRefs = {
  top: ElementRef<HTMLDivElement>;
  bottom: ElementRef<HTMLDivElement>;
  grid: ElementRef<HTMLDivElement>;
  flying: ValueRef<boolean>;
};

export function useCalendarWindow(days: CalDays, current: Ym, refs: CalendarRefs) {
  const [range, setRange] = useState<{ from: Ym; to: Ym }>({
    from: addMonths(current, -3),
    to: current,
  });

  useEffect(() => {
    const root = document.documentElement;
    const previous = root.style.overflowAnchor;
    root.style.overflowAnchor = "none";
    return () => { root.style.overflowAnchor = previous; };
  }, []);

  useEffect(() => {
    requestAnimationFrame(() => {
      const today = refs.grid.current?.querySelector(".cc-cell.today");
      if (today) today.scrollIntoView({ block: "center" });
      else window.scrollTo(0, document.documentElement.scrollHeight);
    });
  }, []);

  useEffect(() => {
    let latest = current;
    for (const key of days.keys()) {
      const ym = { y: Number(key.slice(0, 4)), m: Number(key.slice(5, 7)) - 1 };
      if (!ymLte(ym, latest)) latest = ym;
    }
    if (!ymLte(latest, range.to)) setRange((value) => ({ ...value, to: latest }));
  }, [days]);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        if (entry.target === refs.top.current) prependMonths();
        else if (entry.target === refs.bottom.current) {
          setRange((value) => ({ ...value, to: addMonths(value.to, 4) }));
        }
      }
    }, { rootMargin: "200px 0px" });

    function prependMonths() {
      if (refs.flying.current) return;
      const anchor = refs.grid.current?.querySelector<HTMLElement>("[data-fom]");
      const beforeTop = anchor?.getBoundingClientRect().top ?? 0;
      setRange((value) => ({ ...value, from: addMonths(value.from, -4) }));
      requestAnimationFrame(() => {
        if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - beforeTop);
      });
    }

    if (refs.top.current) observer.observe(refs.top.current);
    if (refs.bottom.current) observer.observe(refs.bottom.current);
    return () => observer.disconnect();
  }, [range.from.y, range.from.m, range.to.y, range.to.m]);

  return range;
}
