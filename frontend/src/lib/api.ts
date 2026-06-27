const API_BASE = 'http://localhost:8090/api';

function apiUrl(path: string): string {
  if (typeof window !== 'undefined') return `/api${path}`;
  return `${API_BASE}${path}`;
}

export interface OrderSummary {
  key: string;
  thread_id: number;
  channel_id: number;
  message_id: number;
  customer: string;
  total: string;
  paid: number;
  remaining: number;
  phone: string;
  date: string;
  status: string;
  soan: boolean;
  giao: boolean;
  nop: boolean;
  nhan: boolean;
  nhan_tien_note: string;
  hd_code: string;
  creator: string;
  text: string;
  invoice_count: number;
  invoice_summary: { sp: string; sl: number }[];
  topic_name: string;
}

export interface OrdersResponse {
  orders: OrderSummary[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  stats: { total_orders: number; pending: number; done: number };
}

export async function fetchOrders(params: {
  page?: number;
  limit?: number;
  search?: string;
  sort?: string;
}): Promise<OrdersResponse> {
  const sp = new URLSearchParams();
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  if (params.search) sp.set('search', params.search);
  if (params.sort) sp.set('sort', params.sort);
  const res = await fetch(apiUrl(`/orders?${sp}`));
  if (!res.ok) throw new Error('Failed to fetch orders');
  return res.json();
}

export async function fetchOrder(threadId: number) {
  const res = await fetch(apiUrl(`/order/${threadId}`));
  if (!res.ok) throw new Error('Order not found');
  return res.json();
}
