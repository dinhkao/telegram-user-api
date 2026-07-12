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
