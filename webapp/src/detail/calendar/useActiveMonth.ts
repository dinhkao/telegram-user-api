import { useEffect, useState } from "preact/hooks";
import { fastScrollToEl } from "../../scroll";
import { ymStr } from "./calendarDates";
import type { ElementRef, ValueRef, Ym } from "./types";

export function useActiveMonth(
  grid: ElementRef<HTMLDivElement>,
  flying: ValueRef<boolean>,
  current: Ym,
  range: { from: Ym; to: Ym },
) {
  const [activeYm, setActiveYm] = useState(ymStr(current));

  useEffect(() => {
    let frame = 0;
    const onScroll = () => {
      if (flying.current) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const marks = grid.current?.querySelectorAll<HTMLElement>("[data-fom]");
        if (!marks?.length) return;
        const middle = window.innerHeight * 0.55;
        let active: string | null = null;
        marks.forEach((element) => {
          if (element.getBoundingClientRect().top <= middle) active = element.dataset.fom ?? null;
        });
        if (active) setActiveYm((previous) => previous === active ? previous : active!);
      });
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [range.from.y, range.from.m, range.to.y, range.to.m]);

  const goToday = () => {
    const today = grid.current?.querySelector<HTMLElement>(".cc-cell.today");
    if (!today) return;
    setActiveYm(ymStr(current));
    flying.current = true;
    const viewport = window.innerHeight;
    const box = today.getBoundingClientRect();
    const target = window.scrollY + box.top - Math.max(56, (viewport - box.height) / 2);
    const distance = target - window.scrollY;
    if (Math.abs(distance) > 2.5 * viewport) {
      window.scrollTo(0, target - Math.sign(distance) * 1.2 * viewport);
    }
    fastScrollToEl(today, "center");
    setTimeout(() => { flying.current = false; }, 320);
  };

  return { activeYm, goToday };
}
