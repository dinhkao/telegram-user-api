export type ProfitPoint = { day: string; revenue: number; cost: number; profit: number; real_profit: number | null; orders?: number; returns?: number; loan?: number | null; cost_complete?: boolean };
export function aggregateProfit(chart: ProfitPoint[], mode: string): ProfitPoint[] {
  if (mode === "daily") return chart;
  const groups: Record<string, ProfitPoint> = {};
  for (const c of chart) {
    let key = c.day.slice(0, 7);
    if (mode === "weekly") {
      const d = new Date(`${c.day}T00:00:00Z`);
      d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7);
      key = d.toISOString().slice(0, 10);
    }
    const g = groups[key] || (groups[key] = { day: key, revenue: 0, cost: 0, profit: 0, real_profit: 0, orders: 0, loan: 0 });
    for (const k of ["revenue", "cost", "profit", "orders", "returns"] as const) g[k] = (g[k] || 0) + (c[k] || 0);
    for (const k of ["real_profit", "loan"] as const) g[k] = g[k] === null || c[k] === null ? null : (g[k] || 0) + (c[k] || 0);
    g.cost_complete = g.cost_complete !== false && c.cost_complete !== false;
  }
  return Object.keys(groups).sort().map(k => groups[k]);
}
export const grossMargin = (p: ProfitPoint): number | null => p.revenue > 0 && p.cost_complete !== false ? p.profit / p.revenue * 100 : null;
