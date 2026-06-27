'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { fetchOrders, type OrderSummary } from '@/lib/api';
import { applyOrdersSnapshot, clearOrdersSnapshot, readOrdersSnapshot, saveOrdersSnapshot } from './orders-storage';

const LIMIT = 50;

export function useOrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [stats, setStats] = useState<{ total_orders: number; pending: number; done: number } | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('created');
  const [view, setView] = useState<'card' | 'table'>('table');
  const sentinelRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef(0);

  useEffect(() => {
    const stored = localStorage.getItem('orderView');
    if (stored === 'table' || stored === 'card') setView(stored);
    else if (window.innerWidth < 768) setView('card');
  }, []);

  const persist = useCallback(() => saveOrdersSnapshot({ orders, stats, total, page, hasMore, search, sort, view, scrollY: window.scrollY }), [orders, stats, total, page, hasMore, search, sort, view]);

  useEffect(() => {
    const save = () => persist();
    window.addEventListener('beforeunload', save);
    return () => window.removeEventListener('beforeunload', save);
  }, [persist]);

  useEffect(() => {
    const saved = readOrdersSnapshot();
    if (saved?.orders?.length) {
      scrollRef.current = applyOrdersSnapshot(saved, { setOrders, setStats, setTotal, setPage, setHasMore, setSearch, setSort, setView });
    }
    clearOrdersSnapshot();
  }, []);

  useEffect(() => {
    if (scrollRef.current && orders.length > 0) {
      requestAnimationFrame(() => {
        window.scrollTo(0, scrollRef.current);
        scrollRef.current = 0;
      });
    }
  }, [orders]);

  const load = useCallback(async (pageNum: number, append: boolean) => {
    if (loading) return;
    setLoading(true);
    try {
      const data = await fetchOrders({ page: pageNum, limit: LIMIT, search, sort });
      setOrders(prev => append ? [...prev, ...data.orders.filter(o => !new Set(prev.map(x => x.thread_id)).has(o.thread_id))] : data.orders);
      setTotal(data.total);
      setHasMore(pageNum < data.total_pages);
      if (data.stats) setStats(data.stats);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [loading, search, sort]);

  useEffect(() => { setOrders([]); setPage(1); setHasMore(true); load(1, false); }, [search, sort]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && hasMore && !loading) {
        const next = page + 1;
        setPage(next);
        load(next, true);
      }
    }, { rootMargin: '200px' });
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasMore, loading, page, load]);

  const onOpen = useCallback((id: number) => {
    persist();
    router.push(`/orders/${id}`);
  }, [persist, router]);

  const onViewChange = useCallback((nextView: 'card' | 'table') => {
    setView(nextView);
    localStorage.setItem('orderView', nextView);
  }, []);

  return { orders, stats, total, search, sort, view, loading, hasMore, sentinelRef, onSearchChange: setSearch, onSortChange: setSort, onViewChange, onOpen };
}
