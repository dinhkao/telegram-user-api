import { fetchOrder } from '@/lib/api';
import { OrderDetailView } from './order-detail-view';

export default async function OrderDetailPage({ params }: { params: { id: string } }) {
  try {
    const data = await fetchOrder(Number(params.id));
    if (!data || !data.data) return <div className="p-4 text-sm text-red-600">❌ Order #{params.id} not found</div>;
    return <OrderDetailView d={data.data || data} data={data} params={params} />;
  } catch (e: any) {
    return <div className="p-4 text-sm text-red-600">❌ Error loading order #{params.id}: {e.message || 'Unknown error'}</div>;
  }
}
