import { SectionCard } from './order-detail-shared';
import { fmtVND } from './order-detail-utils';

export function OrderDetailInvoice({ invoice }: { invoice: any[] }) {
  if (invoice.length === 0) return null;
  return (
    <SectionCard title={`Invoice Items (${invoice.length})`}>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="text-left py-1 font-medium">Product</th>
            <th className="text-right py-1 font-medium">Qty</th>
            <th className="text-right py-1 font-medium">Price</th>
            <th className="text-right py-1 font-medium">Total</th>
            <th className="text-left py-1 font-medium">Note</th>
          </tr>
        </thead>
        <tbody>
          {invoice.map((item, i) => {
            const qty = item.sl || item.quantity || item.sl1pc || 0;
            const price = item.price || 0;
            return (
              <tr key={i} className="border-b last:border-0">
                <td className="py-0.5">{item.sp || item.productCode || item.name || '?'}</td>
                <td className="py-0.5 text-right">{qty}</td>
                <td className="py-0.5 text-right">{fmtVND(price)}</td>
                <td className="py-0.5 text-right">{fmtVND(qty * price)}</td>
                <td className="py-0.5">{item.note || item.qc_type || '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </SectionCard>
  );
}
