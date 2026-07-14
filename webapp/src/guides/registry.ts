// Sổ đăng ký HƯỚNG DẪN — gom mọi bài từ các file mục, xuất GUIDES + tra theo key.
// Thêm bài: sửa file mục tương ứng (data_*.ts). Nối: pages/Guides.tsx, HelpFab.
import type { Guide } from "./types";
import { GUIDES_DON } from "./data_don";
import { GUIDES_KHACH } from "./data_khach";
import { GUIDES_KHO } from "./data_kho";
import { GUIDES_KHONHAP } from "./data_khonhap";
import { GUIDES_SANXUAT } from "./data_sanxuat";
import { GUIDES_TAICHINH } from "./data_taichinh";
import { GUIDES_KHAC } from "./data_khac";

export const GUIDES: Guide[] = [
  ...GUIDES_DON,
  ...GUIDES_KHACH,
  ...GUIDES_KHO,
  ...GUIDES_KHONHAP,
  ...GUIDES_SANXUAT,
  ...GUIDES_TAICHINH,
  ...GUIDES_KHAC,
];

export function guideByKey(key: string): Guide | undefined {
  return GUIDES.find((g) => g.key === key);
}
