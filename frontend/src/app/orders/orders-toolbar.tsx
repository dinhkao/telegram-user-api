'use client';

import { LayoutGrid, List } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';

export function OrdersToolbar({
  search,
  sort,
  view,
  stats,
  ordersCount,
  total,
  onSearchChange,
  onSortChange,
  onViewChange,
}: {
  search: string;
  sort: string;
  view: 'card' | 'table';
  stats: { total_orders: number; pending: number; done: number } | null;
  ordersCount: number;
  total: number;
  onSearchChange: (value: string) => void;
  onSortChange: (value: string) => void;
  onViewChange: (value: 'card' | 'table') => void;
}) {
  return (
    <div className="sticky top-0 z-10 bg-card border-b">
      <div className="flex items-center gap-2 px-3 py-1.5">
        <h1 className="text-sm font-bold">📋 Orders</h1>
        <a href="/" className="text-[11px] text-muted-foreground hover:text-foreground">SM</a>
        <a href="/donhang" className="text-[11px] text-muted-foreground hover:text-foreground">#donhang</a>
      </div>
      <div className="px-2 pb-1.5 space-y-1">
        <Input placeholder="Search customer, phone, product..." value={search} onChange={e => onSearchChange(e.target.value)} className="h-7 text-xs" />
        <div className="flex gap-1.5 items-center">
          <Select value={sort} onChange={e => onSortChange(e.target.value)} className="h-7 text-xs w-24">
            <option value="created">Created</option>
            <option value="updated">Updated</option>
            <option value="date">Inv Date</option>
          </Select>
          <div className="flex border rounded-md overflow-hidden">
            <Button variant={view === 'card' ? 'default' : 'ghost'} size="sm" onClick={() => onViewChange('card')}><LayoutGrid className="h-3.5 w-3.5" /></Button>
            <Button variant={view === 'table' ? 'default' : 'ghost'} size="sm" onClick={() => onViewChange('table')}><List className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
      </div>
      {stats && (
        <div className="flex gap-2 px-2 pb-1 flex-wrap">
          <Badge variant="secondary" className="text-[10px]">{stats.total_orders?.toLocaleString('vi-VN')} total</Badge>
          <Badge variant="warning" className="text-[10px]">{stats.pending?.toLocaleString('vi-VN')} pending</Badge>
          <Badge variant="success" className="text-[10px]">{stats.done?.toLocaleString('vi-VN')} done</Badge>
        </div>
      )}
      <div className="text-[10px] text-muted-foreground px-2 pb-1">{ordersCount} of {total?.toLocaleString('vi-VN')}</div>
    </div>
  );
}
