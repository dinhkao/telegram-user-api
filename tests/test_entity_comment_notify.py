"""Push bình luận thực thể (server_app.entity_comment_notify) + lọc thông báo văn phòng."""
import sqlite3

from notif_store import add_notification, create_notif_table, latest_id, list_notifications
from server_app.entity_comment_notify import OFFICE_SCOPES, describe


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE inventory_boxes (id INTEGER, box_code TEXT, product_code TEXT);
    INSERT INTO inventory_boxes VALUES (5, '347', 'K2L');
    CREATE TABLE production_workers (id INTEGER, name TEXT);
    INSERT INTO production_workers VALUES (9, 'Bảo Xuyên');
    CREATE TABLE workshop_areas (id INTEGER, name TEXT);
    INSERT INTO workshop_areas VALUES (2, 'Khu nấu');
    CREATE TABLE area_hygiene_reports (id INTEGER, area_id INTEGER);
    INSERT INTO area_hygiene_reports VALUES (40, 2);
    CREATE TABLE entity_images (id INTEGER, entity_id INTEGER);
    INSERT INTO entity_images VALUES (700, 40);
    """)
    return c


def test_box_route_and_name():
    assert describe(_db(), "box", 5) == ("Thùng 347 · K2L", "#/thung/5")


def test_area_image_resolves_to_area_page():
    t, r = describe(_db(), "area_image", 700)
    assert r == "#/khu-vuc/2" and "Khu nấu" in t


def test_payroll_scope_is_office_and_names_worker():
    t, r = describe(_db(), "worker_ung", 9)
    assert "worker_ung" in OFFICE_SCOPES and r == "#/luong-thang/9" and "Bảo Xuyên" in t


def test_missing_tables_never_raise():
    c = sqlite3.connect(":memory:")
    assert describe(c, "purchase", 3) == ("Phiếu nhập #3", "#/nhap-hang/3")


def test_office_notifications_hidden_from_staff():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_notif_table(c)
    add_notification(c, type="comment", title="chung", body="x")
    o = add_notification(c, type="comment", title="lương", body="y", audience="office")
    assert "push_payload" not in o
    assert [n["title"] for n in list_notifications(c, office=False)] == ["chung"]
    assert [n["title"] for n in list_notifications(c, office=True)] == ["lương", "chung"]
    assert latest_id(c, office=False) < latest_id(c, office=True)
