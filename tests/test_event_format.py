"""Test bảng tra event → nhãn/parts (server_app/event_format) — các ca từng nổ thật.

Bài học 2026-07-14: disposal.deleted payload ghi restored_allocations dạng INT,
event_format gọi len(int) → TypeError bị nuốt → feed #/lich-su TRẮNG từ trang 9
+ lịch sử phiếu hủy rỗng. event_entry giờ tuyệt đối không raise.
"""
from server_app.event_format import event_entry
from server_app.order_timeline import _clean_note


class EventEntryTests:
    def test_disposal_deleted_int_restored_allocations(self):
        # emitter thật ghi INT (rowcount) — từng làm len(int) nổ TypeError
        label, parts = event_entry("disposal.deleted", {"restored_allocations": 1, "items": [{}]}, None)
        assert label == "Xoá phiếu hủy (hoàn tồn)"
        assert parts and "hoàn 1 phần" in parts[0]["t"]

    def test_disposal_deleted_legacy_list_payload(self):
        label, parts = event_entry("disposal.deleted", {"restored_allocations": [1, 2]}, None)
        assert "hoàn 2 phần" in parts[0]["t"]

    def test_event_entry_never_raises_on_garbage(self):
        # payload rác bất kỳ → KHÔNG raise (None hoặc nhãn kèm text thô đều chấp nhận)
        assert event_entry("order.stock_allocated", {"boxes": "not-a-list"}, None) is None
        event_entry("quy.created", {"amount": object()}, None)   # chỉ cần không nổ
        event_entry("box.moved", {"from_place_id": {}, "quantity": []}, None)

    def test_stock_allocated_parts_detail(self):
        label, parts = event_entry("order.stock_allocated", {"boxes": [
            {"box_id": 7, "box_code": "322", "product_code": "KDX30", "taken": 5.0, "remaining": 15.0, "unit": "cây"},
        ]}, None)
        text = "".join(p["t"] for p in parts)
        assert label == "Xuất kho cho đơn"
        assert text == "lấy 5 cây KDX30 từ thùng 322 (thùng còn 15)"
        assert any(p.get("href") == "#/thung/7" for p in parts)


class CleanNoteTests:
    def test_multi_image_ids_stripped_entirely(self):
        # 'imgs:839,838,837,275' là 1 token NHIỀU id — phải gỡ nguyên cụm
        assert _clean_note("imgs:839,838,837,275") == ""

    def test_note_tokens_kept_and_translated(self):
        assert _clean_note("tra_tien_mat;imgs:875,874") == "trả tiền mặt"
