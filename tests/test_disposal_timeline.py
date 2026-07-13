"""Xuất hủy phải đi vào timeline thùng, vị trí và sản phẩm với delta đúng."""
from __future__ import annotations

from unittest.mock import patch

from server_app import box_timeline, place_timeline, product_timeline
from server_app.inventory_audit import log_boxes_disposal_released, log_boxes_disposed


def test_disposal_delta_is_out_and_delete_is_in():
    payload = {"taken": 7}
    assert box_timeline._delta("box.disposed", payload) == -7
    assert place_timeline._delta("box.disposed", payload) == -7
    assert product_timeline._delta("box.disposed", payload) == -7
    assert box_timeline._delta("box.disposal_released", payload) == 7
    assert place_timeline._delta("box.disposal_released", payload) == 7
    assert product_timeline._delta("box.disposal_released", payload) == 7


def test_disposal_audit_is_written_for_box_and_place_with_link():
    snap = {
        "box_id": 12, "place_id": 3, "box_code": "042", "product_code": "K2L",
        "quantity": 50, "remaining": 43, "taken": 7,
    }
    with patch("server_app.inventory_audit._emit") as emit:
        log_boxes_disposed([snap], disposal_id=9, reason="Hàng lỗi", actor="Duy", actor_type="web_user")
        assert emit.call_count == 2
        for call in emit.call_args_list:
            assert call.args[0] == "box.disposed"
            assert call.args[-1]["disposal_id"] == 9
            assert call.args[-1]["taken"] == 7
            assert call.args[-1]["disposal_reason"] == "Hàng lỗi"

    restored = {**snap, "remaining": 50}
    with patch("server_app.inventory_audit._emit") as emit:
        log_boxes_disposal_released(
            [restored], disposal_id=9, reason="Hàng lỗi", actor="Duy", actor_type="web_user",
        )
        assert emit.call_count == 2
        assert all(c.args[0] == "box.disposal_released" for c in emit.call_args_list)

