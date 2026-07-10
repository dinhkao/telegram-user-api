// Sơ đồ FLOW cho trang Cần làm hàng (#/nhu-cau, view "sơ đồ").
// Vẽ mũi tên NGUYÊN LIỆU → SẢN PHẨM cần làm (theo công thức/BOM, nhiều tầng). Mỗi mã
// 1 ô; NL nuôi nhiều SP hiện 1 ô có nhiều mũi tên ra. Cột trái = NL gốc, phải = SP.
// Chỉ đọc payload StockDemand có sẵn (ingredients đệ quy). Không gọi API riêng.
import { soVN, type StockDemandLine, type StockDemandIngredient } from "../api";

const enc = encodeURIComponent;

type FNode = { code: string; unit: string; kind: "product" | "material"; stock: number; need: number; shortfall: number; depth: number };
type FEdge = { from: string; to: string; need: number };

// Dựng đồ thị từ các SP THIẾU: node = SP + NL (gộp trùng mã), edge = NL → thứ dùng nó.
function buildGraph(products: StockDemandLine[]) {
  const nodes = new Map<string, FNode>();
  const edges: FEdge[] = [];
  const edgeIx = new Map<string, number>();   // "from>to" → index trong edges (gộp need)

  const ensure = (code: string, unit: string): FNode => {
    let n = nodes.get(code);
    if (!n) { n = { code, unit: unit || "", kind: "material", stock: 0, need: 0, shortfall: 0, depth: 0 }; nodes.set(code, n); }
    if (unit && !n.unit) n.unit = unit;
    return n;
  };

  const walk = (ings: StockDemandIngredient[] | undefined, parent: string, depth: number) => {
    for (const g of ings || []) {
      const gn = ensure(g.code, g.unit);
      if (gn.kind !== "product") { gn.stock = g.stock; }   // NL: tồn ổn định qua các lần
      gn.depth = Math.max(gn.depth, depth);
      const ek = `${g.code}>${parent}`;
      if (!edgeIx.has(ek)) { edgeIx.set(ek, edges.length); edges.push({ from: g.code, to: parent, need: g.need }); gn.need += g.need; }
      if (g.children && g.children.length) walk(g.children, g.code, depth + 1);
    }
  };

  for (const p of products) {
    const pn = ensure(p.code, p.unit);
    pn.kind = "product"; pn.stock = p.stock; pn.need = p.need; pn.shortfall = p.shortfall;
    walk(p.ingredients, p.code, 1);
  }
  return { nodes, edges };
}

// Layout theo CỘT: depth cao (NL gốc) bên TRÁI, SP (depth 0) bên PHẢI. Trong cột xếp
// dọc theo Σ thiếu giảm dần. Trả toạ độ mỗi node + kích thước canvas.
const NODE_W = 124, NODE_H = 48, COL_GAP = 52, ROW_GAP = 14, PAD = 6;
function layout(nodes: Map<string, FNode>) {
  let maxDepth = 0;
  for (const n of nodes.values()) maxDepth = Math.max(maxDepth, n.depth);
  const cols: FNode[][] = Array.from({ length: maxDepth + 1 }, () => []);
  for (const n of nodes.values()) cols[maxDepth - n.depth].push(n);   // col 0 = trái = NL gốc
  const pos = new Map<string, { x: number; y: number }>();
  let maxRows = 0;
  cols.forEach((list, ci) => {
    list.sort((a, b) => b.shortfall - a.shortfall || (b.need - b.stock) - (a.need - a.stock) || a.code.localeCompare(b.code));
    maxRows = Math.max(maxRows, list.length);
    list.forEach((n, ri) => pos.set(n.code, { x: PAD + ci * (NODE_W + COL_GAP), y: PAD + ri * (NODE_H + ROW_GAP) }));
  });
  const W = PAD * 2 + (maxDepth + 1) * NODE_W + maxDepth * COL_GAP;
  const H = PAD * 2 + Math.max(1, maxRows) * NODE_H + Math.max(0, maxRows - 1) * ROW_GAP;
  return { pos, W, H };
}

// đường cong bezier ngang từ mép PHẢI ô nguồn (NL) tới mép TRÁI ô đích (thứ dùng NL)
function edgePath(sx: number, sy: number, tx: number, ty: number): string {
  const dx = Math.max(24, (tx - sx) / 2);
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
}

export function StockFlow({ products }: { products: StockDemandLine[] }) {
  if (!products.length) return null;
  const { nodes, edges } = buildGraph(products);
  const { pos, W, H } = layout(nodes);
  const nodeList = Array.from(nodes.values());

  return (
    <div class="nd-flow">
      <div class="nd-flow-legend">
        <span><i class="nd-fdot mat" /> nguyên liệu</span>
        <span><i class="nd-fdot prod" /> sản phẩm cần</span>
        <span class="nd-flow-hint">mũi tên: nguyên liệu → sản phẩm</span>
      </div>
      <div class="nd-flow-scroll">
        <div class="nd-flow-canvas" style={{ width: `${W}px`, height: `${H}px` }}>
          <svg class="nd-flow-edges" width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
            <defs>
              <marker id="nd-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill="var(--muted-2)" />
              </marker>
            </defs>
            {edges.map((e) => {
              const s = pos.get(e.from), t = pos.get(e.to);
              if (!s || !t) return null;
              const sx = s.x + NODE_W, sy = s.y + NODE_H / 2, tx = t.x, ty = t.y + NODE_H / 2;
              return <path key={`${e.from}>${e.to}`} class="nd-fedge" d={edgePath(sx, sy, tx, ty)} marker-end="url(#nd-arrow)" />;
            })}
          </svg>
          {nodeList.map((n) => {
            const p = pos.get(n.code)!;
            const short = n.kind === "product" ? n.shortfall > 1e-9 : n.stock + 1e-9 < n.need;
            const cls = "nd-fnode " + n.kind + (short ? " short" : " ok");
            return (
              <a key={n.code} class={cls} href={`#/kho/${enc(n.code)}`} style={{ left: `${p.x}px`, top: `${p.y}px`, width: `${NODE_W}px`, height: `${NODE_H}px` }}>
                <span class="nd-fn-code">{n.code}</span>
                <span class="nd-fn-stat">
                  {n.kind === "product"
                    ? <>thiếu <b>{soVN(n.shortfall)}</b> {n.unit || "cây"}</>
                    : (short ? <>thiếu <b>{soVN(n.need - n.stock)}</b> {n.unit}</> : <>tồn <b>{soVN(n.stock)}</b> {n.unit}</>)}
                </span>
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
}
