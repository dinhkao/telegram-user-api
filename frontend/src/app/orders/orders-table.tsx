'use client';

import type { OrderSummary } from '@/lib/api';
import { debtInfo, fmtVND } from './orders-utils';

export function OrderTable({ orders, onRowClick }: { orders: OrderSummary[]; onRowClick: (id: number) => void }) {
  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b bg-muted/50 text-muted-foreground">
            <th className="text-left p-2 font-medium">Thread</th>
            <th className="text-left p-2 font-medium">HD Code</th>
            <th className="text-left p-2 font-medium">Customer</th>
            <th className="text-right p-2 font-medium">Total</th>
            <th className="text-right p-2 font-medium">Debt</th>
            <th className="text-left p-2 font-medium">Steps</th>
            <th className="text-left p-2 font-medium">Date</th>
            <th className="text-right p-2 font-medium">Items</th>
          </tr>
        </thead>
        <tbody>
          {orders.map(o => {
            const debt = debtInfo(o);
            const tgChan = String(o.channel_id || '').replace('-100', '');
            return (
              <tr key={o.thread_id} className="border-b hover:bg-muted/50 cursor-pointer" onClick={() => onRowClick(o.thread_id)}>
                <td className="p-2">
                  {tgChan && o.message_id ? (
                    <a href={`https://t.me/c/${tgChan}/${o.message_id}`} target="_blank" onClick={e => e.stopPropagation()} className="text-primary hover:underline">
                      {o.thread_id}
                    </a>
                  ) : o.thread_id}
                </td>
                <td className="p-2">{o.hd_code || '—'}</td>
                <td className="p-2 max-w-32 truncate">{o.customer || '—'}</td>
                <td className="p-2 text-right font-mono">{o.total ? fmtVND(o.total) : '—'}</td>
                <td className={`p-2 text-right font-semibold ${debt.cls}`}>{debt.text}</td>
                <td className="p-2">
                  <div className="flex gap-1">
                    {(['soan', 'giao', 'nop', 'nhan'] as const).map(s => (
                      <span key={s} className={o[s] ? 'text-emerald-600' : 'text-muted-foreground/40'}>{({ soan: 'S', giao: 'G', nop: 'N', nhan: 'N' } as const)[s]}</span>
                    ))}
                  </div>
                </td>
                <td className="p-2 whitespace-nowrap">{o.date || '—'}</td>
                <td className="p-2 text-right">{o.invoice_count || 0}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
