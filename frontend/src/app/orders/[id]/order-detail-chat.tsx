import { SectionCard } from './order-detail-shared';
import { toVnTime } from './order-detail-utils';

export function OrderDetailChat({ chatMessages }: { chatMessages: any[] }) {
  if (chatMessages.length === 0) return null;
  return (
    <SectionCard title={`Chat Messages (${chatMessages.length})`}>
      {chatMessages.map((m, i) => (
        <div key={i} className={`py-0.5 ${i < chatMessages.length - 1 ? 'border-b' : ''}`}>
          <div className="text-[10px] text-muted-foreground">{toVnTime(m.created_at)} <strong>{m.sender_name || m.sender_id || '?'}</strong></div>
          <div className="text-xs whitespace-pre-wrap">{m.text || (m.media_type ? `[${m.media_type}]` : '—')}</div>
        </div>
      ))}
    </SectionCard>
  );
}
