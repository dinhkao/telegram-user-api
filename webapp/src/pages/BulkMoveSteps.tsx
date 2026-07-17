import type { KhoBox, Place } from "../api";
import { soVN } from "../api";
import { foldVN } from "../format";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";

export type MoveSource = number | "unplaced";
export const movable = (box: KhoBox) => !box.disabled && (box.remaining ?? box.quantity ?? 0) > 0;

type SourceProps = {
  places: Place[]; boxes: KhoBox[]; value: MoveSource | null;
  query: string; onQuery: (value: string) => void; onPick: (value: MoveSource) => void;
};

export function MoveSourceStep({ places, boxes, value, query, onQuery, onPick }: SourceProps) {
  const normalized = foldVN(query.trim());
  const shown = normalized ? places.filter((place) => foldVN(place.name).includes(normalized)) : places;
  const showUnplaced = !normalized || foldVN("Ko có kho").includes(normalized);
  const countAt = (placeId: number | null) => boxes.filter((box) =>
    (placeId == null ? box.place_id == null : box.place_id === placeId) && movable(box)).length;

  return <div class="bm-step">
    <div class="bm-step-h"><b>1 · Kho nguồn</b></div>
    <SearchBar value={query} onInput={onQuery} placeholder="Tìm kho nguồn…" />
    <div class="bm-places">
      {showUnplaced && <button class={"chip" + (value === "unplaced" ? " active" : "")} onClick={() => onPick("unplaced")}>
        Ko có kho <span class="chip-n">{countAt(null)}</span>
      </button>}
      {shown.map((place) => <button key={place.id} class={"chip" + (value === place.id ? " active" : "")} onClick={() => onPick(place.id)}>
        {place.name} <span class="chip-n">{countAt(place.id)}</span>
      </button>)}
    </div>
  </div>;
}

type BoxesProps = {
  boxes: KhoBox[]; total: number; selected: Set<number>; query: string; allShown: boolean;
  onQuery: (value: string) => void; onToggle: (id: number) => void; onSelectAll: () => void;
};

export function MoveBoxesStep({ boxes, total, selected, query, allShown, onQuery, onToggle, onSelectAll }: BoxesProps) {
  return <div class="bm-step">
    <div class="bm-step-h">
      <b>2 · Chọn thùng</b> <span class="muted small">(chọn {selected.size}/{total})</span>
      {boxes.length > 0 && <button class="btn ghost small" onClick={onSelectAll}>{allShown ? "Bỏ chọn" : "Chọn tất cả"}</button>}
    </div>
    <SearchBar value={query} onInput={onQuery} placeholder="Tìm mã SP / số thùng…" />
    {boxes.length === 0 ? <p class="muted small">{total ? `Không có thùng khớp "${query}".` : "Kho này không có thùng chuyển được."}</p> : <div class="bm-boxes">
      {boxes.map((box) => {
        const number = (box.box_code || "").split("-").pop() || box.box_code;
        const on = selected.has(box.id);
        return <button key={box.id} class={"bm-box" + (on ? " on" : "")} onClick={() => onToggle(box.id)}>
          <span class="bm-box-chk">{on && <Icon name="check" size={13} />}</span>
          <span class="bm-box-code">{box.product_code}</span><span class="bm-box-num">{number}</span>
          <span class="bm-box-q muted small">{soVN(box.remaining ?? box.quantity)}{box.product_unit ? ` ${box.product_unit}` : ""}</span>
        </button>;
      })}
    </div>}
  </div>;
}

type DestinationProps = {
  places: Place[]; source: MoveSource; value: number | null; query: string;
  onQuery: (value: string) => void; onPick: (id: number) => void;
};

export function MoveDestinationStep({ places, source, value, query, onQuery, onPick }: DestinationProps) {
  const normalized = foldVN(query.trim());
  const shown = places.filter((place) => place.id !== source && (!normalized || foldVN(place.name).includes(normalized)));
  return <div class="bm-step">
    <div class="bm-step-h"><b>3 · Kho đích</b></div>
    <SearchBar value={query} onInput={onQuery} placeholder="Tìm kho đích…" />
    <div class="bm-places">
      {shown.map((place) => <button key={place.id} class={"chip" + (value === place.id ? " active" : "")} onClick={() => onPick(place.id)}>
        {place.name}
      </button>)}
    </div>
  </div>;
}
