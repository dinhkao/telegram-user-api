from renderers.order_parts import status_icons


def _status(note=None, *, skip=False):
    nop = {"done": True}
    if note is not None:
        nop["note"] = note
    if skip:
        nop["skip"] = True
    return {"nop_tien": nop}


def test_nop_tien_paid_in_full_keeps_check_icon():
    assert status_icons(_status("tra_tien_mat"))[3] == "✅"
    assert status_icons(_status("tra_tien_mat;img:123"))[3] == "✅"


def test_nop_tien_done_by_other_paths_uses_document_icon():
    assert status_icons(_status("co_ky_toa"))[3] == "📄"
    assert status_icons(_status("khong_ky_toa"))[3] == "📄"
    assert status_icons(_status())[3] == "📄"


def test_nop_tien_skip_keeps_skip_icon():
    assert status_icons(_status(skip=True))[3] == "🔘"


def test_soan_hang_pending_after_stock_confirmed_uses_box_icon():
    assert status_icons({}, stock_confirmed=True)[1] == "📦"
    assert status_icons({}, stock_confirmed=False)[1] == "❌"


def test_soan_hang_done_keeps_check_icon_after_stock_confirmed():
    task_status = {"soan_hang": {"done": True}}
    assert status_icons(task_status, stock_confirmed=True)[1] == "✅"
