// View GỌN dùng chung: gom thùng theo mã SP, mỗi SP 1 dòng "Mã SP (N) : chip chip…".
// Chip = mã thùng (số gọi) đậm | tồn mờ, kẻ dọc ngăn, 5 chip/dòng. Bấm SP → chi tiết SP,
// bấm chip → chi tiết thùng. Dùng ở PlaceDetail + KhoBoxes.
import { soVN, type KhoBox } from "../api";
import { boxNumber } from "./BoxTile";

const remOf = (b: KhoBox) => Math.max(0, b.remaining ?? b.quantity ?? 0);
const num = (b: KhoBox) => boxNumber(b.box_code || "");
const sumRem = (bs: KhoBox[]) => bs.reduce((s, b) => s + remOf(b), 0);

function Chips({ bs }: { bs: KhoBox[] }) {
  return (
    <span class="pd-cboxes">
      {bs.slice().sort((a, b) => num(a).localeCompare(num(b))).map((b) => (
        <a class="pd-cbox" key={b.id} href={`#/thung/${b.id}`}
          title={`Thùng ${num(b)} · còn ${soVN(remOf(b))} ${b.product_unit || "cây"}`}>
          <span class="pd-cbn">{num(b)}</span><span class="pd-cq">{soVN(remOf(b))}</span>
        </a>
      ))}
    </span>
  );
}

// flat = chỉ chip (trang chi tiết 1 SP, khỏi header mã SP thừa); mặc định gom theo SP.
export function CompactBoxList({ boxes, flat }: { boxes: KhoBox[]; flat?: boolean }) {
  if (flat) return <div class="pd-compact"><Chips bs={boxes} /></div>;
  const g = new Map<string, KhoBox[]>();
  for (const b of boxes) { const a = g.get(b.product_code); if (a) a.push(b); else g.set(b.product_code, [b]); }
  const groups = [...g.entries()].sort((a, b) => sumRem(b[1]) - sumRem(a[1]) || a[0].localeCompare(b[0]));
  return (
    <div class="pd-compact">
      {groups.map(([pcode, bs]) => (
        <div class="pd-crow" key={pcode}>
          <a class="pd-csp" href={`#/kho/${encodeURIComponent(pcode)}`}>{pcode} <span class="pd-cn">({bs.length})</span></a>
          <Chips bs={bs} />
        </div>
      ))}
    </div>
  );
}
