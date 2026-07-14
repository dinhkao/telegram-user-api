"""Test SỐ GIỜ LÀM trong báo cáo thợ + tiền lương THEO GIỜ (2026-07-14).

Cột 12 layout `;` = số giờ làm; thợ có giờ → tiền = giờ × production_workers.
hourly_rate (đặt ở chi tiết thợ), THAY cho cây × đơn giá SP. Nối:
production_store/domain, report_rows, report_slips.compute_range_report,
worker_store.
"""
import sqlite3

from production_store.domain import compute_report, parse_report


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class ParseGioTests:
    def test_parse_reads_column_12(self):
        text = "thợ;gạch;trừ;lẻ;ghi chú\nKim;2;0;3;;33;;;;;;;4,5;KDX30;5/7/2026;;;10;;"
        p = parse_report(text)
        assert p["rows"][0]["so_gio"] == 4.5

    def test_blank_hours_stays_none(self):
        text = "thợ;gạch;trừ;lẻ;ghi chú\nKim;2;0;3;;33;;;;;;;;KDX30;5/7/2026"
        p = parse_report(text)
        assert p["rows"][0]["so_gio"] is None

    def test_compute_passes_gio_through(self):
        text = "thợ;gạch;trừ;lẻ;ghi chú\nKim;2;0;0;;;;;;;;;8;KDX30;5/7/2026"
        out = compute_report(parse_report(text), 3)
        assert out["rows"][0]["so_gio"] == 8.0


class HourlyMoneyTests:
    def _seed(self, conn):
        from product_store import create_products_table
        from production_store.report_rows import ensure_report_rows_schema, replace_report_rows
        from worker_store import ensure_table, add_worker, update_worker
        create_products_table(conn)   # schema products ĐẦY ĐỦ (resolve_code cần cost_price…)
        ensure_report_rows_schema(conn)
        ensure_table(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS production_slips (
            thread_id INTEGER PRIMARY KEY, sp_name TEXT, luong_1sp REAL, kind TEXT, bang TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS production_allowances (
            thread_id INTEGER, worker_name TEXT, amount REAL)""")
        kim = add_worker(conn, "Kim")
        update_worker(conn, kim["id"], hourly_rate=50_000)
        lan = add_worker(conn, "Lan")   # không đặt tiền giờ
        conn.execute("INSERT INTO production_slips (thread_id, sp_name, luong_1sp) VALUES (9, 'KDX30', 100)")
        # Kim: 8 giờ (không tính cây) · Lan: 200 cây (tính theo SP)
        replace_report_rows(conn, 9, {
            "product_code": "KDX30", "date": "5/7/2026",
            "rows": [
                {"name": "Kim", "so_gach": 0, "so_tru": 0, "so_cay_le": 0, "so_mam": 0,
                 "tong_calc": 0, "note": "", "so_gio": 8},
                {"name": "Lan", "so_gach": 10, "so_tru": 0, "so_cay_le": 0, "so_mam": 50,
                 "tong_calc": 200, "note": ""},
            ],
        })
        return kim, lan

    def test_hourly_worker_paid_gio_x_rate(self):
        from production_store.report_slips import compute_range_report
        conn = _conn()
        self._seed(conn)
        rep = compute_range_report(conn, "2026-07-01", "2026-07-31")
        by_name = {w["name"]: w for w in rep["workers"]}
        assert by_name["Kim"]["money"] == 8 * 50_000          # giờ × tiền 1 giờ
        assert by_name["Lan"]["money"] == 200 * 100           # cây × đơn giá chốt phiếu
        kim_hr = [it for it in by_name["Kim"]["items"] if it["gio"] > 0][0]
        assert kim_hr["gio"] == 8 and kim_hr["hourly_rate"] == 50_000

    def test_piece_and_hours_both_paid_same_slip(self):
        # Review 2026-07-14: thợ vừa có dòng CÂY vừa có dòng GIỜ trong 1 phiếu —
        # GROUP BY từng nuốt tiền cây. Phải nhận CẢ HAI: cây×đơn giá + giờ×rate.
        from production_store.report_rows import replace_report_rows
        from production_store.report_slips import compute_range_report
        conn = _conn()
        self._seed(conn)
        replace_report_rows(conn, 9, {
            "product_code": "KDX30", "date": "5/7/2026",
            "rows": [
                {"name": "Kim", "so_gach": 10, "so_tru": 0, "so_cay_le": 0, "so_mam": 50,
                 "tong_calc": 100, "note": ""},                      # dòng cây
                {"name": "Kim", "so_gach": 0, "so_tru": 0, "so_cay_le": 0, "so_mam": 0,
                 "tong_calc": 0, "note": "", "so_gio": 8},           # dòng giờ
            ],
        })
        rep = compute_range_report(conn, "2026-07-01", "2026-07-31")
        kim = {w["name"]: w for w in rep["workers"]}["Kim"]
        assert kim["money"] == 100 * 100 + 8 * 50_000   # 10.000 + 400.000

    def test_dong_goi_slip_ignores_hours(self):
        # Giờ chỉ áp dụng phiếu SẢN XUẤT — phiếu đóng gói dính cột giờ (paste
        # Telegram) không được lật sang tính giờ.
        from production_store.report_slips import compute_range_report
        conn = _conn()
        self._seed(conn)
        conn.execute("UPDATE production_slips SET kind = 'dong_goi' WHERE thread_id = 9")
        rep = compute_range_report(conn, "2026-07-01", "2026-07-31")
        kim = {w["name"]: w for w in rep["workers"]}.get("Kim")
        assert kim is None or all((it["gio"] or 0) == 0 or it["money"] == 0 for it in kim["items"])

    def test_worker_registered_after_report_claims_rows(self):
        # Báo cáo lưu TRƯỚC khi đăng ký thợ → worker_id NULL; add_worker phải
        # nhận lại các dòng đó (không thì lương giờ = 0 mãi).
        from production_store.report_rows import replace_report_rows
        from production_store.report_slips import compute_range_report
        from worker_store import add_worker, update_worker
        conn = _conn()
        self._seed(conn)
        replace_report_rows(conn, 9, {
            "product_code": "KDX30", "date": "5/7/2026",
            "rows": [{"name": "Mai", "so_gach": 0, "so_tru": 0, "so_cay_le": 0,
                      "so_mam": 0, "tong_calc": 0, "note": "", "so_gio": 6}],
        })
        mai = add_worker(conn, "mai")   # đăng ký SAU, lệch hoa/thường
        update_worker(conn, mai["id"], hourly_rate=40_000)
        rep = compute_range_report(conn, "2026-07-01", "2026-07-31")
        by = {w["name"]: w for w in rep["workers"]}
        assert by["mai"]["money"] == 6 * 40_000

    def test_hours_without_rate_flagged_missing(self):
        from production_store.report_slips import compute_range_report
        conn = _conn()
        self._seed(conn)
        # Lan cũng nhập giờ nhưng CHƯA đặt tiền 1 giờ → tiền 0 + cảnh báo
        from production_store.report_rows import replace_report_rows
        replace_report_rows(conn, 9, {
            "product_code": "KDX30", "date": "5/7/2026",
            "rows": [{"name": "Lan", "so_gach": 0, "so_tru": 0, "so_cay_le": 0,
                      "so_mam": 0, "tong_calc": 0, "note": "", "so_gio": 5}],
        })
        rep = compute_range_report(conn, "2026-07-01", "2026-07-31")
        by_name = {w["name"]: w for w in rep["workers"]}
        assert by_name["Lan"]["money"] == 0
        assert any("Lan" in m for m in rep["missing_wage"])

    def test_worker_detail_rows_carry_so_gio(self):
        from production_store.report_rows import worker_detail
        conn = _conn()
        self._seed(conn)
        d = worker_detail(conn, "Kim")
        assert d["rows"][0]["so_gio"] == 8.0
