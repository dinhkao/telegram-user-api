import { SectionCard, Row } from './order-detail-shared';
import { fmtVND } from './order-detail-utils';

export function OrderDetailPayments({ payments }: { payments: any[] }) {
  if (payments.length === 0) return null;
  return (
    <SectionCard title={`Payments (${payments.length})`}>
      {payments.map((p, i) => <Row key={i} label={`${p.method || '?'} ${p.created_at ? p.created_at.slice(0, 10) : ''}`}>{fmtVND(p.amount)}</Row>)}
    </SectionCard>
  );
}
