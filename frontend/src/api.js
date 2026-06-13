const BASE = '/api';

export async function fetchOrders({ page = 1, limit = 50, search = '', sort = 'created' } = {}) {
  const params = new URLSearchParams({ page, limit, search, sort });
  const res = await fetch(`${BASE}/orders?${params}`);
  if (!res.ok) throw new Error('Failed to fetch orders');
  return res.json();
}

export async function fetchOrder(threadId) {
  const res = await fetch(`${BASE}/order/${threadId}`);
  if (!res.ok) throw new Error('Order not found');
  return res.json();
}
