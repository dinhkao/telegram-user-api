import { SectionCard } from './order-detail-shared';

export function OrderDetailText({ text }: { text: string }) {
  if (!text) return null;
  return <SectionCard title="Order Text"><div className="text-xs whitespace-pre-wrap">{text}</div></SectionCard>;
}
