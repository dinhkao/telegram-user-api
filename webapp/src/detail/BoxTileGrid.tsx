import { BoxTile, type BoxTileAction, type BoxTileData, type BoxTileMode, type BoxTileSize } from "./BoxTile";

export type ProductCodeMode = "auto" | "show" | "hide";

export type BoxTileGridProps<T extends BoxTileData = BoxTileData> = {
  boxes: T[];
  size?: BoxTileSize;
  mode?: BoxTileMode;
  productCodeMode?: ProductCodeMode;
  getAction?: (box: T) => BoxTileAction | undefined;
  getKey?: (box: T) => number | string;
  className?: string;
};

function hasStock(box: BoxTileData): number {
  return !box.disabled && (box.remaining ?? box.quantity) > 0 ? 1 : 0;
}

/** Auto chỉ hiện mã khi lưới có từ hai mã SP không rỗng khác nhau. */
export function shouldShowProductCode(boxes: BoxTileData[], mode: ProductCodeMode): boolean {
  if (mode === "show") return true;
  if (mode === "hide") return false;
  return new Set(boxes.map((box) => box.productCode.trim()).filter(Boolean)).size > 1;
}

export function BoxTileGrid<T extends BoxTileData>({
  boxes,
  size = "regular",
  mode = "remaining",
  productCodeMode = "auto",
  getAction,
  getKey = (box) => box.id,
  className,
}: BoxTileGridProps<T>) {
  if (!boxes.length) return null;

  const showProductCode = shouldShowProductCode(boxes, productCodeMode);
  const ordered = boxes.slice().sort((a, b) => hasStock(b) - hasStock(a));
  const gridClass = [
    "box-tile-grid",
    `box-tile-grid-${size}`,
    showProductCode ? "has-product-code" : "no-product-code",
    className,
  ].filter(Boolean).join(" ");

  return (
    <div class={gridClass}>
      {ordered.map((box) => (
        <BoxTile
          key={getKey(box)}
          box={box}
          size={size}
          mode={mode}
          showProductCode={showProductCode}
          action={getAction?.(box)}
        />
      ))}
    </div>
  );
}

export type { BoxTileAction, BoxTileData, BoxTileMode, BoxTileSize } from "./BoxTile";
