import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export function OrderDetailHeader({ title }: { title: string }) {
  return (
    <div className="sticky top-0 z-10 border-b bg-card px-3 py-2 flex items-center gap-2">
      <Link href="/orders" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back
      </Link>
      <h1 className="text-sm font-semibold flex-1 truncate">{title}</h1>
    </div>
  );
}
