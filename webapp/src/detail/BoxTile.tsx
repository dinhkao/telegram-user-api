import type { ComponentChildren, JSX } from "preact";
import { soVN } from "../api";

export type BoxTileSize = "regular" | "dense" | "mini";
export type BoxTileMode = "remaining" | "produced" | "allocated";

/** Dữ liệu đã chuẩn hoá để mọi màn hình dùng cùng một renderer ô thùng. */
export type BoxTileData = {
  id: number | string;
  productCode: string;
  boxCode: string;
  quantity: number;
  remaining?: number | null;
  capacity?: number | null;
  allocated?: number | null;
  disabled?: boolean;
  note?: string | null;
  placeName?: string | null;
  productUnit?: string | null;
  /** Vai 👁 hiển thị: SỐ trên ô quy đổi sang đơn vị này (chia hết → nguyên,
   *  không → 1 số lẻ). CHỈ tầng hiển thị — fill/tooltip gốc giữ nguyên số thật. */
  displayUnitName?: string | null;
  displayUnitFactor?: number | null;
  href?: string;
  domId?: string;
  title?: string;
};

/** Shape dùng chung của các payload kho/timeline hiện vẫn đặt tên field dạng snake_case. */
export type InventoryBoxTileData = {
  id: number | string;
  product_code: string;
  box_code: string;
  quantity: number;
  remaining?: number | null;
  capacity?: number | null;
  allocated?: number | null;
  disabled?: boolean | number | null;
  note?: string | null;
  place_name?: string | null;
  product_unit?: string | null;
  display_unit_name?: string | null;
  display_unit_factor?: number | null;
};

export function inventoryBoxTile(box: InventoryBoxTileData, href = `#/thung/${box.id}`): BoxTileData {
  return {
    id: box.id,
    productCode: box.product_code || "",
    boxCode: box.box_code || "",
    quantity: box.quantity ?? 0,
    remaining: box.remaining,
    capacity: box.capacity,
    allocated: box.allocated,
    disabled: !!box.disabled,
    note: box.note,
    placeName: box.place_name,
    productUnit: box.product_unit,
    displayUnitName: box.display_unit_name,
    displayUnitFactor: box.display_unit_factor,
    href,
  };
}

export type BoxTileAction = {
  label: string;
  content: ComponentChildren;
  onClick: (event: JSX.TargetedMouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  className?: string;
};

export type BoxTileProps = {
  box: BoxTileData;
  size?: BoxTileSize;
  mode?: BoxTileMode;
  showProductCode?: boolean;
  action?: BoxTileAction;
};

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function boxNumber(boxCode: string): string {
  return boxCode.split("-").pop() || boxCode;
}

function tileValues(box: BoxTileData, mode: BoxTileMode) {
  const remaining = box.remaining ?? box.quantity;
  const capacity = box.capacity ?? box.quantity;

  if (mode === "allocated") {
    const current = box.allocated ?? box.quantity;
    return {
      current,
      total: box.quantity > 0 ? box.quantity : null,
      fill: box.quantity > 0 ? clampPercent((current / box.quantity) * 100) : 100,
      remaining,
    };
  }

  return {
    current: mode === "produced" ? box.quantity : remaining,
    total: mode === "remaining" && (box.allocated ?? 0) > 0 ? box.quantity : null,
    fill: capacity > 0 ? clampPercent((remaining / capacity) * 100) : 100,
    remaining,
  };
}

/** Factor quy đổi hiển thị (vai 👁) — chỉ nhận khi > 0 và ≠ 1 (1 = như đơn vị gốc). */
function displayFactor(box: BoxTileData): number | null {
  const f = box.displayUnitFactor;
  return f && f > 0 && f !== 1 ? f : null;
}

/** Số theo đơn vị hiển thị: chia hết → nguyên; không → 1 chữ số lẻ. */
function displayQty(v: number, factor: number): string {
  const x = v / factor;
  const r = Math.round(x);
  return Math.abs(x - r) < 1e-6 ? soVN(r) : soVN(Math.round(x * 10) / 10);
}

function defaultTitle(box: BoxTileData, mode: BoxTileMode, current: number, total: number | null, remaining: number): string {
  const unit = box.productUnit || (mode === "remaining" ? "cây" : "");
  const df = displayFactor(box);
  const quantity = mode === "allocated"
    ? `lấy ${soVN(current)}${total !== null ? `/${soVN(total)}` : ""}`
    : mode === "produced"
      ? `còn ${soVN(remaining)}/${soVN(box.quantity)}`
      : `${soVN(current)} ${unit}`.trim()
        + (df ? ` = ${displayQty(current, df)} ${box.displayUnitName}` : "");
  const status = box.disabled
    ? "vô hiệu"
    : mode === "remaining" && (box.allocated ?? 0) > 0
      ? `đã xuất ${soVN(box.allocated ?? 0)}/${soVN(box.quantity)}`
      : mode === "remaining" ? "trong kho" : "";

  return [box.boxCode, quantity, status, box.placeName, box.note].filter(Boolean).join(" · ");
}

/**
 * Một ô thùng duy nhất. Wrapper giữ link và action là hai phần tử ngang hàng để
 * không tạo interactive element lồng nhau khi ô vừa mở chi tiết vừa có action.
 */
export function BoxTile({ box, size = "regular", mode = "remaining", showProductCode = true, action }: BoxTileProps) {
  const { current, total, fill, remaining } = tileValues(box, mode);
  // Vai 👁: SỐ trên ô quy đổi sang đơn vị hiển thị (fill vẫn tỉ lệ theo số gốc)
  const df = displayFactor(box);
  const currentText = df ? displayQty(current, df) : soVN(current);
  const totalText = total !== null ? (df ? displayQty(total, df) : soVN(total)) : "";
  // Mono font: ước lượng bề ngang theo số ký tự để tỷ lệ luôn phóng lớn nhất có thể
  // mà vẫn vừa ô. Phần tổng nhỏ hơn nên mỗi ký tự chỉ tính ~46% trọng số số chính.
  const ratioUnits = currentText.length * .6 + .45 + totalText.length * .27;
  const ratioNowCqw = total !== null ? Math.min(36, 92 / ratioUnits) : 0;
  const state = box.disabled ? "off" : "in";
  const drained = size === "mini" && !box.disabled && remaining <= 0;
  const tileClass = [
    "box-tile",
    `is-${state}`,
    size === "mini" ? "box-tile-mini" : "",
    drained ? "is-drained" : "",
  ].filter(Boolean).join(" ");
  const style = {
    "--fill": `${fill}%`,
    ...(total !== null ? {
      "--ratio-now": `${ratioNowCqw}cqw`,
      "--ratio-total": `${ratioNowCqw * .46}cqw`,
    } : {}),
  } as JSX.CSSProperties & Record<string, string>;
  const title = box.title || defaultTitle(box, mode, current, total, remaining);
  const content = (
    <>
      {box.note && <span class="bl-dot" />}
      {showProductCode && <span class="bl-code">{box.productCode}</span>}
      <span class={"bl-q" + (total !== null ? " has-total" : "")}>
        <span class="bl-q-now">{currentText}</span>
        {total !== null && <><span class="bl-q-sep">/</span><span class="bl-q-tot">{totalText}</span></>}
        {df && size !== "mini" && <span class="bl-unit">{box.displayUnitName}</span>}
      </span>
      <span class="bl-num">{boxNumber(box.boxCode)}</span>
    </>
  );

  return (
    <span class="box-tile-wrap">
      {box.href ? (
        <a id={box.domId} class={tileClass} href={box.href} style={style} title={title}>{content}</a>
      ) : (
        <span id={box.domId} class={tileClass} style={style} title={title}>{content}</span>
      )}
      {action && (
        <button
          type="button"
          class={["box-tile-action", action.className].filter(Boolean).join(" ")}
          disabled={action.disabled}
          title={action.label}
          aria-label={action.label}
          onClick={action.onClick}
        >
          {action.content}
        </button>
      )}
    </span>
  );
}
