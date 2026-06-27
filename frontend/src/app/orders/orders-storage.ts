import type { OrderSummary } from '@/lib/api';

export type OrdersSnapshot = {
  orders: OrderSummary[];
  stats: { total_orders: number; pending: number; done: number } | null;
  total: number;
  page: number;
  hasMore: boolean;
  search: string;
  sort: string;
  view: 'card' | 'table';
  scrollY: number;
};

const KEY = 'ordersState';

export function saveOrdersSnapshot(snapshot: OrdersSnapshot) {
  sessionStorage.setItem(KEY, JSON.stringify(snapshot));
}

export function readOrdersSnapshot(): OrdersSnapshot | null {
  try {
    const saved = sessionStorage.getItem(KEY);
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null;
  }
}

export function applyOrdersSnapshot(
  snapshot: OrdersSnapshot,
  setters: {
    setOrders: (orders: OrderSummary[]) => void;
    setStats: (stats: OrdersSnapshot['stats']) => void;
    setTotal: (total: number) => void;
    setPage: (page: number) => void;
    setHasMore: (hasMore: boolean) => void;
    setSearch: (search: string) => void;
    setSort: (sort: string) => void;
    setView: (view: OrdersSnapshot['view']) => void;
  },
) {
  setters.setOrders(snapshot.orders);
  if (snapshot.stats) setters.setStats(snapshot.stats);
  setters.setTotal(snapshot.total || 0);
  setters.setPage(snapshot.page || 1);
  setters.setHasMore(snapshot.hasMore ?? true);
  if (snapshot.search) setters.setSearch(snapshot.search);
  if (snapshot.sort) setters.setSort(snapshot.sort);
  if (snapshot.view) setters.setView(snapshot.view);
  return snapshot.scrollY || 0;
}

export function clearOrdersSnapshot() {
  sessionStorage.removeItem(KEY);
}
