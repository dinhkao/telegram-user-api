// Adapter mỏng giữ API caller cũ; toàn bộ DOM/logic nằm trong BoxTileGrid.
import { BoxTileGrid } from "./BoxTileGrid";
import { inventoryBoxTile, type InventoryBoxTileData } from "./BoxTile";

export function BoxLabelGrid({ boxes, dense }: { boxes: InventoryBoxTileData[]; dense?: boolean }) {
  return <BoxTileGrid boxes={boxes.map((box) => inventoryBoxTile(box))} size={dense ? "dense" : "regular"} />;
}
