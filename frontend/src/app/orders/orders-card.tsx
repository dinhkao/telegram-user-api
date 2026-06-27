'use client';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { OrderSummary } from '@/lib/api';
import { debtInfo, fmtVND, relativeTime } from './orders-utils';

const STEP_LABELS = { soan: 'Soạn', giao: 'Giao', nop: 'Nộp', nhan: 'Nhận' } as const;

export function OrderCard({ order, onClick }: { order: OrderSummary; onClick: () => void }) {
  const debt = debtInfo(order);
  const rel = relativeTime(order.date);
  const inv = order.invoice_summary || [];

  return (
    <Card className="hover:shadow-md transition-shadow cursor-pointer" onClick={onClick}>
      <CardContent className="p-3 space-y-1.5">
        <div className="text-xs leading-snug line-clamp-3 font-medium">{order.text || order.customer || '—'}</div>
        <div className="text-[11px] text-muted-foreground">{order.customer || '—'}</div>
        <div className="flex gap-1.5 flex-wrap text-[10px] text-muted-foreground">
          {order.hd_code && <span>{order.hd_code}</span>}
          {order.date && <span>{order.date}</span>}
          {rel && <span className="text-amber-600 font-medium">{rel} trước</span>}
        </div>
        <div className="flex gap-2 items-center">
          {order.total && <span className="text-sm font-bold">{fmtVND(order.total)}</span>}
          <span className={`text-xs font-semibold ${debt.cls}`}>{debt.text}</span>
        </div>
        {inv.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            {inv.map((it, i) => <Badge key={i} variant="secondary" className="text-[10px]">{it.sp} x{it.sl}</Badge>)}
            {order.invoice_count > inv.length && <span className="text-[10px] text-muted-foreground">+{order.invoice_count - inv.length} more</span>}
          </div>
        )}
        <div className="flex gap-1 flex-wrap">
          {(['soan', 'giao', 'nop', 'nhan'] as const).map(s => (
            <Badge key={s} variant={order[s] ? 'success' : 'secondary'} className="text-[10px] px-1.5">{STEP_LABELS[s]}</Badge>
          ))}
        </div>
        <div className="text-[10px] text-muted-foreground">#{order.thread_id}</div>
      </CardContent>
    </Card>
  );
}
