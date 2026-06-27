import type { ReactNode } from 'react';

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex py-0.5 text-xs">
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <span className="flex-1 break-words">{children}</span>
    </div>
  );
}

export function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border rounded-lg bg-card">
      <div className="p-3">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">{title}</div>
        {children}
      </div>
    </div>
  );
}
