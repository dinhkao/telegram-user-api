import { OrderDetailHeader } from './order-detail-header';
import { OrderDetailBasic } from './order-detail-basic';
import { OrderDetailText } from './order-detail-text';
import { OrderDetailChat } from './order-detail-chat';
import { OrderDetailTasks } from './order-detail-tasks';
import { OrderDetailInvoice } from './order-detail-invoice';
import { OrderDetailPayments } from './order-detail-payments';
import { OrderDetailRaw } from './order-detail-raw';

export function OrderDetailView({ d, data, params }: { d: any; data: any; params: { id: string } }) {
  const pc = d.hoadon?.print_content || {};
  const chatMessages = data.chat_messages || [];
  const userName: Record<string, string> = {};
  chatMessages.forEach((m: any) => { if (m.sender_id && m.sender_name) userName[String(m.sender_id)] = m.sender_name; });
  const showName = (id: any) => Array.isArray(id) ? id.map((x: any) => userName[String(x)] || x).join(', ') : (userName[String(id)] || String(id || ''));
  const customer = d.customer_name || pc.kh || d.customer || d.khach_hang || '—';
  const hdCode = d.hd_code || d.hoadon?.hd_code || d.kiotvietInvoiceCode || '';
  const total = d.total || pc.tongthanhtoan || '';
  const text = d.text || d.text_raw || '';
  const channelId = String(d.channel_id || data.channel_id || '').replace('-100', '');
  const msgId = d.message_id || data.message_id || '';
  const telegramUrl = channelId && msgId ? `https://t.me/c/${channelId}/${msgId}` : '';
  const invoice = d.invoice || d.invoice_items || [];
  const payments = d.payments || [];
  const tasks = d.task_status || {};

  return (
    <div className="pb-8">
      <OrderDetailHeader title={`Order ${hdCode || '#' + (d.thread_id || params.id)} — ${customer}`} />
      <div className="max-w-2xl mx-auto px-1.5 pt-1.5 space-y-1.5">
        <OrderDetailBasic threadId={d.thread_id || params.id} customer={customer} phone={d.phone || pc.sdt || '—'} total={total} date={d.date || pc.datetime || '—'} hdCode={hdCode || '—'} firebaseKey={d.key || d.firebase_key || '—'} creator={showName(d.nguoi_tao_HD) || '—'} telegramUrl={telegramUrl} />
        <OrderDetailText text={text} />
        <OrderDetailChat chatMessages={chatMessages} />
        <OrderDetailTasks tasks={tasks} showName={showName} />
        <OrderDetailInvoice invoice={invoice} />
        <OrderDetailPayments payments={payments} />
        <OrderDetailRaw json={d} />
      </div>
    </div>
  );
}
