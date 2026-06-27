'use client';

import type { OrderSummary } from '@/lib/api';
import { OrderCard } from './orders-card';
import { OrderTable } from './orders-table';

export function OrdersList({
  orders,
  view,
  onOpen,
}: {
  orders: OrderSummary[];
  view: 'card' | 'table';
  onOpen: (id: number) => void;
}) {
  return view === 'card' ? (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-1">
      {orders.map(o => <OrderCard key={o.thread_id} order={o} onClick={() => onOpen(o.thread_id)} />)}
    </div>
  ) : (
    <OrderTable orders={orders} onRowClick={onOpen} />
  );
}
