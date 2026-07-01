"""Header schema and static config constants (order matters — from bot.js)."""

from __future__ import annotations

HEADERS = [
    "Tên",
    "Số gạch",
    "Số trừ",
    "Số cây lẻ",
    "Ghi chú",
    "Tổng số SP",
    "Số giờ TL",
    "Lương 1 SP",
    "Lương 1 giờ TL",
    "Tổng lương SP",
    "Tổng lương TL",
    "Phụ cấp",
    "Tổng lương phiếu",
    "Sản phẩm",
    "Ngày",
    "STT",
    "Số chảo",
    "Số mâm",
    "Giờ vào",
    "Giờ ra",
    "Lương trên 1 giờ",
    "Link",
    "Cập nhật lần cuối",
]
DATE_HEADER = "Ngày"
NEW_COLUMNS_BEFORE_LINK = ["Số mâm", "Giờ vào", "Giờ ra", "Lương trên 1 giờ"]
MANAGED_HEADER_MARKERS = [
    "Tên",
    "Số gạch",
    "Tổng số SP",
    "Sản phẩm",
    "Ngày",
    "STT",
    "Link",
    "Cập nhật lần cuối",
]
HIDDEN_EXPORT_HEADERS = {
    "Lương 1 SP",
    "Lương 1 giờ TL",
    "Tổng lương SP",
    "Tổng lương TL",
    "Phụ cấp",
    "Tổng lương phiếu",
    "Lương trên 1 giờ",
}

# Array formulas re-applied on each managed sheet (verbatim from bot.js).
ARRAY_FORMULAS = [
    {"range": "H1", "formula": '={"Lương 1 SP";ARRAYFORMULA(IF(N2:N="";"";VLOOKUP(N2:N;\'Sản phẩm\'!A2:D;4;FALSE)))}'},
    {"range": "I1", "formula": '={"Lương 1 giờ TL";ARRAYFORMULA(IF(A2:A="";"";VLOOKUP(A2:A;\'Nhân viên\'!A2:B;2;FALSE)))}'},
    {"range": "J1", "formula": '={"Tổng lương SP";ARRAYFORMULA(IF(A2:A = ""; ""; F2:F * H2:H))}'},
    {"range": "K1", "formula": '={"Tổng lương TL";ARRAYFORMULA(IF(A2:A = ""; ""; G2:G * I2:I))}'},
    {"range": "M1", "formula": '={"Tổng lương phiếu";ARRAYFORMULA(IF(A2:A = ""; ""; J2:J+K2:K+L2:L))}'},
    {"range": "U1", "formula": '={"Lương trên 1 giờ";ARRAYFORMULA(IF(A2:A = ""; ""; IFERROR(IF((VALUE(T2:T)-VALUE(S2:S))<=0; ""; M2:M/((VALUE(T2:T)-VALUE(S2:S))*IF((VALUE(T2:T)-VALUE(S2:S))<1;24;1))); "")))}'},
]
