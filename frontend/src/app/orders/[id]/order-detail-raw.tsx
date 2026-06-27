export function OrderDetailRaw({ json }: { json: unknown }) {
  return (
    <details className="border rounded-lg bg-card">
      <summary className="p-2 text-[10px] uppercase tracking-wide text-muted-foreground cursor-pointer select-none">Raw JSON</summary>
      <pre className="p-2 text-[11px] overflow-auto max-h-72 border-t">{JSON.stringify(json, null, 2)}</pre>
    </details>
  );
}
