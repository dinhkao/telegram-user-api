import { ExternalLink } from 'lucide-react';
import { SectionCard, Row } from './order-detail-shared';
import { fmtVND } from './order-detail-utils';

export function OrderDetailBasic({
  threadId,
  customer,
  phone,
  total,
  date,
  hdCode,
  firebaseKey,
  creator,
  telegramUrl,
}: {
  threadId: string | number;
  customer: string;
  phone: string;
  total: unknown;
  date: string;
  hdCode: string;
  firebaseKey: string;
  creator: string;
  telegramUrl: string;
}) {
  return (
    <SectionCard title="Basic Info">
      <Row label="Thread ID">{threadId}</Row>
      <Row label="Customer">{customer}</Row>
      <Row label="Phone">{phone}</Row>
      <Row label="Total">{fmtVND(total)}</Row>
      <Row label="Date">{date || '—'}</Row>
      <Row label="HD Code">{hdCode || '—'}</Row>
      <Row label="Firebase Key">{firebaseKey || '—'}</Row>
      <Row label="Creator">{creator || '—'}</Row>
      {telegramUrl && <Row label="Telegram"><a href={telegramUrl} target="_blank" className="text-primary hover:underline inline-flex items-center gap-0.5">Open in Telegram <ExternalLink className="h-3 w-3" /></a></Row>}
    </SectionCard>
  );
}
