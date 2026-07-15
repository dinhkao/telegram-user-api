export type CalendarItem = { t: string; done: boolean };

export type CalendarDay = {
  o: number;
  p: number;
  items?: CalendarItem[];
};

export type CalDays = Map<string, CalendarDay>;

export type Ym = {
  y: number;
  m: number;
};

export type ElementRef<T> = {
  current: T | null;
};

export type ValueRef<T> = {
  current: T;
};
