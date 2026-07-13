// Adapter mini không tạo link vì bản thân card phiếu sản xuất đã là link.
import { BoxTileGrid } from "./BoxTileGrid";
import { inventoryBoxTile, type InventoryBoxTileData } from "./BoxTile";

export function BoxMiniGrid({ boxes }: { boxes: InventoryBoxTileData[] }) {
  return <BoxTileGrid boxes={boxes.map((box) => inventoryBoxTile(box, ""))} size="mini" mode="produced" />;
}
