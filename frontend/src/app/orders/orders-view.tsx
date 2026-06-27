'use client';

import { useOrdersPage } from './use-orders-page';
import { OrdersToolbar } from './orders-toolbar';
import { OrdersList } from './orders-list';

export function OrdersView() {
  const { orders, stats, total, search, sort, view, loading, hasMore, onSearchChange, onSortChange, onViewChange, onOpen, sentinelRef } = useOrdersPage();

  return (
    <div className="pb-8">
      <OrdersToolbar search={search} sort={sort} view={view} stats={stats} ordersCount={orders.length} total={total} onSearchChange={onSearchChange} onSortChange={onSortChange} onViewChange={onViewChange} />
      <div className="px-1 pt-1">
        <OrdersList orders={orders} view={view} onOpen={onOpen} />
        <div ref={sentinelRef} className="text-center py-4 text-xs text-muted-foreground">
          {loading && <span>⏳ Loading...</span>}
          {!loading && hasMore && orders.length > 0 && <span>Scroll for more...</span>}
          {!hasMore && orders.length > 0 && <span>✅ All loaded</span>}
        </div>
      </div>
    </div>
  );
}
